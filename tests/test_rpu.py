import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import convert, rpu  # noqa: E402

TESTDATA = os.path.join(os.path.dirname(__file__), 'testdata')


def _load_frame(name):
    with open(os.path.join(TESTDATA, name + '.rpu'), 'rb') as f:
        raw = f.read()
    with open(os.path.join(TESTDATA, name + '.json'), encoding='utf-8') as f:
        truth = json.load(f)
    return raw, truth


def _load_av1_t35_frame(name):
    with open(os.path.join(TESTDATA, name + '.t35'), 'rb') as f:
        payload = f.read()
    with open(os.path.join(TESTDATA, name + '.json'), encoding='utf-8') as f:
        truth = json.load(f)
    return payload, truth


def _truth_blocks(truth):
    vdr = truth['vdr_dm_data']
    blocks = {}
    for group in ('cmv29_metadata', 'cmv40_metadata'):
        if group not in vdr:
            continue  # a CM v2.9-only RPU (real AV1 fixtures) has no v4.0 group
        for entry in vdr[group]['ext_metadata_blocks']:
            (level_name, fields), = entry.items()
            level = int(level_name.replace('Level', ''))
            blocks.setdefault(level, []).append(fields)
    return blocks


class _BitWriter:
    """MSB-first bit writer, the inverse of sidedata._bits.BitReader, used
    only by the AV1 T.35 wrapper writer below.
    """

    def __init__(self):
        self._bits = []

    def write_bits(self, value, n):
        for i in range(n - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def write_bit(self, value):
        self._bits.append(1 if value else 0)

    def align(self, fill_bit=1):
        while len(self._bits) % 8 != 0:
            self._bits.append(fill_bit)

    def to_bytes(self):
        out = bytearray()
        for i in range(0, len(self._bits), 8):
            byte = 0
            for b in self._bits[i:i + 8]:
                byte = (byte << 1) | b
            out.append(byte)
        return bytes(out)


def _write_variable_bits(bw, value, n):
    # Inverse of rpu._parse_variable_bits / dovi_tool's write_variable_bits
    # (dolby_vision/src/av1/emdf.rs, tag libdovi-3.3.1). Only the
    # single-chunk path is exercised by these tests (real emdf_payload_id_ext
    # is 225 with n=5, and RPU sizes here are well under 256 with n=8), but
    # the multi-chunk path is implemented to match the source exactly.
    max_val = 1 << n
    if value > max_val:
        remaining = value
        while True:
            tmp = remaining >> n
            clipped = tmp << n
            remaining -= clipped
            byte = (clipped - max_val) >> n
            bw.write_bits(byte, n)
            bw.write_bit(1)  # read_more
            if remaining <= max_val:
                break
        bw.write_bits(remaining, n)
    else:
        bw.write_bits(value, n)
    bw.write_bit(0)  # read_more


def _write_av1_t35_payload(clean_rpu_bytes):
    """Test-side writer: wraps an already-unescaped regular RPU (starting
    with the 0x19 rpu_nal_prefix byte) into a synthetic AV1 Dolby Vision
    ITU-T T.35 metadata OBU payload, per dovi_tool's
    convert_regular_rpu_to_av1_payload + write_emdf_container_with_dovi_rpu_payload
    (dolby_vision/src/av1/{mod,emdf}.rs, tag libdovi-3.3.1) - the exact
    inverse of rpu.parse_av1_t35. Real AV1 payloads are never escaped with
    start-code emulation prevention, so the input here must already be
    clean (see rpu._clear_emulation_prevention).
    """
    assert clean_rpu_bytes[0] == rpu._RPU_PREFIX
    rpu_body = clean_rpu_bytes[1:]

    bw = _BitWriter()
    bw.write_bits(0x3B, 16)   # itu_t_t35_terminal_provider_code
    bw.write_bits(0x800, 32)  # itu_t_t35_terminal_provider_oriented_code

    bw.write_bits(0, 2)   # emdf_version
    bw.write_bits(6, 3)   # key_id
    bw.write_bits(31, 5)  # emdf_payload_id
    _write_variable_bits(bw, 225, 5)  # emdf_payload_id_ext

    bw.write_bit(0)  # smploffste
    bw.write_bit(0)  # duratione
    bw.write_bit(0)  # groupide
    bw.write_bit(0)  # codecdatae
    bw.write_bit(1)  # discard_unknown_payload

    _write_variable_bits(bw, len(rpu_body), 8)  # emdf_payload_size

    for b in rpu_body:
        bw.write_bits(b, 8)

    # emdf_payload_id / emdf_protection trailer: not read by the parser
    # (it stops once emdf_payload_size bytes are consumed), included only
    # so the synthetic payload is a faithful full wrapper.
    bw.write_bits(0, 5)
    bw.write_bits(1, 2)
    bw.write_bits(0, 2)
    bw.write_bits(0, 8)

    bw.align(fill_bit=1)

    return bytes((0xB5,)) + bw.to_bytes()


class TestRpuAgainstDoviTool(unittest.TestCase):
    def _check_frame(self, name):
        raw, truth = _load_frame(name)
        parsed = rpu.parse_rpu_payload(raw)
        self.assertIsNotNone(parsed, 'parse failed for ' + name)

        vdr = truth['vdr_dm_data']
        blocks = _truth_blocks(truth)

        self.assertEqual(parsed['compressed'], vdr['compressed'])
        self.assertIsNotNone(parsed['source'])
        self.assertEqual(parsed['source']['min_pq'], vdr['source_min_pq'])
        self.assertEqual(parsed['source']['max_pq'], vdr['source_max_pq'])

        # L1
        l1_truth = blocks[1][0]
        self.assertIsNotNone(parsed['l1'])
        self.assertEqual(parsed['l1']['min_pq'], l1_truth['min_pq'])
        self.assertEqual(parsed['l1']['max_pq'], l1_truth['max_pq'])
        self.assertEqual(parsed['l1']['avg_pq'], l1_truth['avg_pq'])

        # L2: every raw trim code, matched up by target_max_pq
        l2_truth_by_pq = {b['target_max_pq']: b for b in blocks[2]}
        self.assertEqual(len(parsed['l2']), len(l2_truth_by_pq))
        for pq, b in l2_truth_by_pq.items():
            nits = convert.snap_target_nits(convert.pq_to_nits(pq))
            matches = [e for e in parsed['l2'] if e['nits'] == nits and e['slope'] == b['trim_slope']]
            self.assertEqual(len(matches), 1, 'no unique L2 match for pq %d' % pq)
            entry = matches[0]
            self.assertEqual(entry['slope'], b['trim_slope'])
            self.assertEqual(entry['offset'], b['trim_offset'])
            self.assertEqual(entry['power'], b['trim_power'])
            self.assertEqual(entry['chromaweight'], b['trim_chroma_weight'])
            self.assertEqual(entry['saturation'], b['trim_saturation_gain'])
            self.assertEqual(entry['tonedetail'], b['ms_weight'])

        # L5
        l5_truth = blocks[5][0]
        self.assertEqual(parsed['l5']['left'], l5_truth['active_area_left_offset'])
        self.assertEqual(parsed['l5']['right'], l5_truth['active_area_right_offset'])
        self.assertEqual(parsed['l5']['top'], l5_truth['active_area_top_offset'])
        self.assertEqual(parsed['l5']['bottom'], l5_truth['active_area_bottom_offset'])

        # L6
        l6_truth = blocks[6][0]
        self.assertEqual(parsed['l6']['max_cll'], l6_truth['max_content_light_level'])
        self.assertEqual(parsed['l6']['max_fall'], l6_truth['max_frame_average_light_level'])
        self.assertEqual(parsed['l6']['min_lum_raw'], l6_truth['min_display_mastering_luminance'])
        self.assertEqual(parsed['l6']['max_lum_raw'], l6_truth['max_display_mastering_luminance'])

        # L3
        l3_truth = blocks[3][0]
        self.assertEqual(parsed['l3']['min_pq_offset'], l3_truth['min_pq_offset'])
        self.assertEqual(parsed['l3']['max_pq_offset'], l3_truth['max_pq_offset'])
        self.assertEqual(parsed['l3']['avg_pq_offset'], l3_truth['avg_pq_offset'])

        # L8: raw trim fields, target resolved via L10 (index 1 has no L10
        # definition here so it falls back to the 100 nit preset table)
        l8_truth = blocks[8][0]
        self.assertEqual(len(parsed['l8']), len(blocks[8]))
        l8_entry = next(e for e in parsed['l8']
                         if e['target_display_index'] == l8_truth['target_display_index'])
        self.assertEqual(l8_entry['slope'], l8_truth['trim_slope'])
        self.assertEqual(l8_entry['offset'], l8_truth['trim_offset'])
        self.assertEqual(l8_entry['power'], l8_truth['trim_power'])
        self.assertEqual(l8_entry['chromaweight'], l8_truth['trim_chroma_weight'])
        self.assertEqual(l8_entry['saturation'], l8_truth['trim_saturation_gain'])
        self.assertEqual(l8_entry['tonedetail'], l8_truth['ms_weight'])
        if l8_truth['target_display_index'] == 1:
            self.assertEqual(l8_entry['nits'], 100)

        # L9
        l9_truth = blocks[9][0]
        self.assertEqual(parsed['l9']['index'], l9_truth['source_primary_index'])
        self.assertEqual(parsed['l9']['has_coords'], l9_truth['length'] >= 17)

        # L10: the two named entries the task pins exactly
        l10_by_index = {e['target_display_index']: e for e in parsed['l10']}
        self.assertEqual(len(parsed['l10']), len(blocks[10]))
        for b in blocks[10]:
            entry = l10_by_index[b['target_display_index']]
            self.assertEqual(entry['target_max_pq'], b['target_max_pq'])
            self.assertEqual(entry['primary_index'], b['target_primary_index'])
        self.assertIn(24, l10_by_index)
        self.assertIn(25, l10_by_index)
        self.assertEqual(l10_by_index[24]['target_max_pq'], 2547)
        self.assertEqual(l10_by_index[24]['nits'], 300)
        self.assertEqual(l10_by_index[24]['primary_index'], 0)
        self.assertEqual(l10_by_index[25]['target_max_pq'], 2547)
        self.assertEqual(l10_by_index[25]['nits'], 300)
        self.assertEqual(l10_by_index[25]['primary_index'], 2)

        # L11: absent from this file in both ground truth and our parse
        self.assertNotIn(11, blocks)
        self.assertIsNone(parsed['l11'])

        # cm_version: L254 is present in every frame of this file (CM v4.0)
        if 254 in blocks:
            self.assertEqual(parsed['cm_version'], '4.0')

        # el_type: Signs 2002 is profile 8.1, single layer - no enhancement
        # layer at all, cross-checked against the header truth fields too
        header_truth = truth['header']
        self.assertEqual(parsed['header']['el_spatial_resampling_filter_flag'],
                          header_truth['el_spatial_resampling_filter_flag'])
        self.assertEqual(parsed['header']['disable_residual_flag'],
                          header_truth['disable_residual_flag'])
        self.assertIsNone(parsed['header']['el_type'])

        return parsed

    def test_frame0(self):
        self._check_frame('signs_frame0')

    def test_frame500_l8_l10(self):
        self._check_frame('signs_frame500')

    def test_hevc_nal62_synthetic_wrap_matches_raw_path(self):
        raw, _truth = _load_frame('signs_frame0')
        direct = rpu.parse_rpu_payload(raw)

        synthetic_nal = b'\x7c\x01' + raw
        via_hevc = rpu.parse_hevc_nal62(synthetic_nal)

        self.assertIsNotNone(via_hevc)
        self.assertEqual(via_hevc, direct)

    def test_malformed_payload_returns_none_not_exception(self):
        self.assertIsNone(rpu.parse_rpu_payload(b''))
        self.assertIsNone(rpu.parse_rpu_payload(b'\x00\x01\x02'))
        self.assertIsNone(rpu.parse_rpu_payload(os.urandom(64)))
        self.assertIsNone(rpu.parse_hevc_nal62(b'not a nal'))
        self.assertIsNone(rpu.parse_av1_t35(b'not an obu'))

    def test_av1_t35_synthetic_wrap_matches_hevc_path(self):
        raw, _truth = _load_frame('signs_frame0')
        direct = rpu.parse_rpu_payload(raw)

        clean = rpu._clear_emulation_prevention(raw)
        synthetic = _write_av1_t35_payload(clean)
        via_av1 = rpu.parse_av1_t35(synthetic)

        self.assertIsNotNone(via_av1)
        self.assertEqual(via_av1, direct)

    def test_av1_t35_synthetic_wrap_matches_hevc_path_frame500(self):
        raw, _truth = _load_frame('signs_frame500')
        direct = rpu.parse_rpu_payload(raw)

        clean = rpu._clear_emulation_prevention(raw)
        synthetic = _write_av1_t35_payload(clean)
        via_av1 = rpu.parse_av1_t35(synthetic)

        self.assertIsNotNone(via_av1)
        self.assertEqual(via_av1, direct)

    def test_av1_malformed_truncations_never_raise(self):
        raw, _truth = _load_frame('signs_frame0')
        clean = rpu._clear_emulation_prevention(raw)
        synthetic = _write_av1_t35_payload(clean)

        for length in range(len(synthetic) + 1):
            try:
                rpu.parse_av1_t35(synthetic[:length])
            except Exception as exc:  # noqa: BLE001
                self.fail('parse_av1_t35 raised on truncation to %d bytes: %r' % (length, exc))

    def test_av1_malformed_bit_flips_never_raise(self):
        raw, _truth = _load_frame('signs_frame0')
        clean = rpu._clear_emulation_prevention(raw)
        synthetic = _write_av1_t35_payload(clean)

        # flip every bit of the wrapper header region (country code through
        # a few bytes into the RPU payload) - each flip must degrade to
        # None (rejected gate, bad CRC, EOF, ...), never raise
        header_region = min(24, len(synthetic))
        for i in range(header_region):
            for bit in range(8):
                corrupted = bytearray(synthetic)
                corrupted[i] ^= (1 << bit)
                try:
                    rpu.parse_av1_t35(bytes(corrupted))
                except Exception as exc:  # noqa: BLE001
                    self.fail('parse_av1_t35 raised on bit flip at byte %d bit %d: %r' % (i, bit, exc))

    def test_av1_gate_rejects_hevc_and_hdr10plus_payloads(self):
        hevc_style = b'\x7c\x01' + bytes(30)
        self.assertIsNone(rpu.parse_av1_t35(hevc_style))

        hdr10plus_style = bytes((0xB5, 0x00, 0x3C, 0x00, 0x01, 0x04)) + bytes(30)
        self.assertIsNone(rpu.parse_av1_t35(hdr10plus_style))


class TestAv1RealFixtures(unittest.TestCase):
    """Golden-tested against real AV1+DV content, the same way the HEVC
    fixtures above are: the ITU-T T.35 metadata OBU payloads in
    tests/testdata/dv10_av1_frame{0,700}.t35 were walked out of a real AV1
    elementary stream (frames 0 and 700 of a title muxed with in-band DV
    RPUs, one metadata OBU per frame; found via an OBU walker matching
    AMLLatchAv1DoviRpu's - leb128 sizes, type 5 = OBU_METADATA,
    metadata_type 4 = ITUT_T35, ~/ce/xbmc AMLFrameMetadata.h,
    ce-raw-metadata branch), and the .json ground truth is dovi_tool's own
    `info` dump of the same title's separately-extracted regular-RPU form
    at the matching frame index (decode order lines up 1:1. verified
    against all 1450 frames of the title, not just these two - see the
    task report, no fixture committed for that full-stream check since it
    needs the 37MB source file this repo doesn't carry).
    """

    def _check_av1_frame(self, name):
        payload, truth = _load_av1_t35_frame(name)
        parsed = rpu.parse_av1_t35(payload)
        self.assertIsNotNone(parsed, 'parse failed for ' + name)

        vdr = truth['vdr_dm_data']
        blocks = _truth_blocks(truth)

        self.assertEqual(parsed['profile'], truth['dovi_profile'])
        self.assertEqual(parsed['compressed'], vdr['compressed'])
        self.assertIsNotNone(parsed['source'])
        self.assertEqual(parsed['source']['min_pq'], vdr['source_min_pq'])
        self.assertEqual(parsed['source']['max_pq'], vdr['source_max_pq'])

        l1_truth = blocks[1][0]
        self.assertIsNotNone(parsed['l1'])
        self.assertEqual(parsed['l1']['min_pq'], l1_truth['min_pq'])
        self.assertEqual(parsed['l1']['max_pq'], l1_truth['max_pq'])
        self.assertEqual(parsed['l1']['avg_pq'], l1_truth['avg_pq'])

        l2_truth_by_pq = {b['target_max_pq']: b for b in blocks[2]}
        self.assertEqual(len(parsed['l2']), len(l2_truth_by_pq))
        for pq, b in l2_truth_by_pq.items():
            nits = convert.snap_target_nits(convert.pq_to_nits(pq))
            matches = [e for e in parsed['l2'] if e['nits'] == nits and e['slope'] == b['trim_slope']]
            self.assertEqual(len(matches), 1, 'no unique L2 match for pq %d' % pq)
            entry = matches[0]
            self.assertEqual(entry['offset'], b['trim_offset'])
            self.assertEqual(entry['power'], b['trim_power'])
            self.assertEqual(entry['chromaweight'], b['trim_chroma_weight'])
            self.assertEqual(entry['saturation'], b['trim_saturation_gain'])
            self.assertEqual(entry['tonedetail'], b['ms_weight'])

        l5_truth = blocks[5][0]
        self.assertEqual(parsed['l5']['left'], l5_truth['active_area_left_offset'])
        self.assertEqual(parsed['l5']['right'], l5_truth['active_area_right_offset'])
        self.assertEqual(parsed['l5']['top'], l5_truth['active_area_top_offset'])
        self.assertEqual(parsed['l5']['bottom'], l5_truth['active_area_bottom_offset'])

        l6_truth = blocks[6][0]
        self.assertEqual(parsed['l6']['max_cll'], l6_truth['max_content_light_level'])
        self.assertEqual(parsed['l6']['max_fall'], l6_truth['max_frame_average_light_level'])
        self.assertEqual(parsed['l6']['min_lum_raw'], l6_truth['min_display_mastering_luminance'])
        self.assertEqual(parsed['l6']['max_lum_raw'], l6_truth['max_display_mastering_luminance'])

        # this title's RPUs carry no CM v4.0 block group at all
        self.assertNotIn('cmv40_metadata', vdr)
        self.assertEqual(parsed['l8'], [])
        self.assertIsNone(parsed['l9'])
        self.assertEqual(parsed['l10'], [])
        self.assertIsNone(parsed['l11'])
        self.assertEqual(parsed['cm_version'], '2.9')

        header_truth = truth['header']
        self.assertEqual(parsed['header']['el_spatial_resampling_filter_flag'],
                          header_truth['el_spatial_resampling_filter_flag'])
        self.assertEqual(parsed['header']['disable_residual_flag'],
                          header_truth['disable_residual_flag'])

        return parsed

    def test_frame0(self):
        self._check_av1_frame('dv10_av1_frame0')

    def test_frame700(self):
        self._check_av1_frame('dv10_av1_frame700')


class TestElTypeRealFixtures(unittest.TestCase):
    """Golden-tested against real dual-layer profile 7 content: frame 0 of
    a real FEL title and frame 0 of a real MEL title (both CM v2.9, 3840x2160
    HEVC captures), RPUs walked out with dovi_tool extract-rpu and ground
    truth taken from dovi_tool's own `info` JSON dump of the same frame.
    dovi_tool's summary reports the FEL title as "Profile: 7 (FEL)" and the
    MEL title as "Profile: 7 (MEL)"; its per-frame JSON carries a top-level
    el_type field agreeing with that verdict. The FEL fixture's frame 0 has
    a non-default NLQ residual (nlq_offset 512, not the 0 default), so it
    exercises the actual FEL-vs-MEL branch of _decide_el_type rather than
    just the flag condition TestDecideElType covers synthetically.
    """

    def _check_frame(self, name):
        raw, truth = _load_frame(name)
        parsed = rpu.parse_rpu_payload(raw)
        self.assertIsNotNone(parsed, 'parse failed for ' + name)

        vdr = truth['vdr_dm_data']
        blocks = _truth_blocks(truth)

        self.assertEqual(parsed['profile'], truth['dovi_profile'])
        self.assertEqual(parsed['compressed'], vdr['compressed'])
        self.assertIsNotNone(parsed['source'])
        self.assertEqual(parsed['source']['min_pq'], vdr['source_min_pq'])
        self.assertEqual(parsed['source']['max_pq'], vdr['source_max_pq'])

        l1_truth = blocks[1][0]
        self.assertIsNotNone(parsed['l1'])
        self.assertEqual(parsed['l1']['min_pq'], l1_truth['min_pq'])
        self.assertEqual(parsed['l1']['max_pq'], l1_truth['max_pq'])
        self.assertEqual(parsed['l1']['avg_pq'], l1_truth['avg_pq'])

        l2_truth_by_pq = {b['target_max_pq']: b for b in blocks[2]}
        self.assertEqual(len(parsed['l2']), len(l2_truth_by_pq))
        for pq, b in l2_truth_by_pq.items():
            nits = convert.snap_target_nits(convert.pq_to_nits(pq))
            matches = [e for e in parsed['l2'] if e['nits'] == nits and e['slope'] == b['trim_slope']]
            self.assertEqual(len(matches), 1, 'no unique L2 match for pq %d' % pq)
            entry = matches[0]
            self.assertEqual(entry['offset'], b['trim_offset'])
            self.assertEqual(entry['power'], b['trim_power'])
            self.assertEqual(entry['chromaweight'], b['trim_chroma_weight'])
            self.assertEqual(entry['saturation'], b['trim_saturation_gain'])
            self.assertEqual(entry['tonedetail'], b['ms_weight'])

        l5_truth = blocks[5][0]
        self.assertEqual(parsed['l5']['left'], l5_truth['active_area_left_offset'])
        self.assertEqual(parsed['l5']['right'], l5_truth['active_area_right_offset'])
        self.assertEqual(parsed['l5']['top'], l5_truth['active_area_top_offset'])
        self.assertEqual(parsed['l5']['bottom'], l5_truth['active_area_bottom_offset'])

        l6_truth = blocks[6][0]
        self.assertEqual(parsed['l6']['max_cll'], l6_truth['max_content_light_level'])
        self.assertEqual(parsed['l6']['max_fall'], l6_truth['max_frame_average_light_level'])
        self.assertEqual(parsed['l6']['min_lum_raw'], l6_truth['min_display_mastering_luminance'])
        self.assertEqual(parsed['l6']['max_lum_raw'], l6_truth['max_display_mastering_luminance'])

        # this title's RPUs carry no CM v4.0 block group at all
        self.assertNotIn('cmv40_metadata', vdr)
        self.assertEqual(parsed['l8'], [])
        self.assertIsNone(parsed['l9'])
        self.assertEqual(parsed['l10'], [])
        self.assertIsNone(parsed['l11'])
        self.assertEqual(parsed['cm_version'], '2.9')

        header_truth = truth['header']
        self.assertEqual(parsed['header']['el_spatial_resampling_filter_flag'],
                          header_truth['el_spatial_resampling_filter_flag'])
        self.assertEqual(parsed['header']['disable_residual_flag'],
                          header_truth['disable_residual_flag'])

        return parsed

    def test_fel_frame0_is_fel(self):
        parsed = self._check_frame('dv7fel_frame0')
        self.assertEqual(parsed['header']['el_type'], 'FEL')

    def test_mel_frame0_is_mel(self):
        parsed = self._check_frame('dv7mel_frame0')
        self.assertEqual(parsed['header']['el_type'], 'MEL')


_MEL_DEFAULT_COMPONENT = {
    'nlq_offset': 0,
    'vdr_in_max': 8388608,  # 1 << 23, ffmpeg's literal "no residual" constant
    'linear_deadzone_slope': 0,
    'linear_deadzone_threshold': 0,
}


def _mel_default_components():
    return [dict(_MEL_DEFAULT_COMPONENT) for _ in range(3)]


class TestDecideElType(unittest.TestCase):
    """Synthetic-input coverage for rpu._decide_el_type, the MEL/FEL
    decision ported from Kodi's DVDVideoCodecFFmpeg.cpp. TestElTypeRealFixtures
    above covers the decision against real dual-layer content; this exercises
    the decision function's individual boundary conditions directly, which a
    single real fixture frame can't isolate one at a time.
    """

    def test_flag_condition_false_is_none(self):
        components = _mel_default_components()
        components[0]['nlq_offset'] = 5  # would be FEL if the flag condition held
        self.assertIsNone(rpu._decide_el_type(False, components))
        self.assertIsNone(rpu._decide_el_type(False, None))

    def test_condition_true_all_default_is_mel(self):
        self.assertEqual(rpu._decide_el_type(True, _mel_default_components()), 'MEL')

    def test_condition_true_missing_components_is_none(self):
        # the flag condition and NLQ-block presence should never disagree in
        # a valid stream, but never guess if they do
        self.assertIsNone(rpu._decide_el_type(True, None))
        self.assertIsNone(rpu._decide_el_type(True, []))

    def test_condition_true_nonzero_nlq_offset_is_fel(self):
        components = _mel_default_components()
        components[1]['nlq_offset'] = 3
        self.assertEqual(rpu._decide_el_type(True, components), 'FEL')

    def test_condition_true_nondefault_vdr_in_max_is_fel(self):
        components = _mel_default_components()
        components[0]['vdr_in_max'] = 8388609
        self.assertEqual(rpu._decide_el_type(True, components), 'FEL')

    def test_condition_true_nonzero_linear_deadzone_slope_is_fel(self):
        components = _mel_default_components()
        components[2]['linear_deadzone_slope'] = 1
        self.assertEqual(rpu._decide_el_type(True, components), 'FEL')

    def test_condition_true_nonzero_linear_deadzone_threshold_is_fel(self):
        components = _mel_default_components()
        components[0]['linear_deadzone_threshold'] = 1
        self.assertEqual(rpu._decide_el_type(True, components), 'FEL')


class TestCombineCoef(unittest.TestCase):
    def test_fixed_point_combines_int_and_fraction(self):
        # int part 1, fraction 0, 23-bit denom -> 1 << 23, ffmpeg's constant
        self.assertEqual(rpu._combine_coef(1, 0, 0, 23), 8388608)
        self.assertEqual(rpu._combine_coef(0, 5, 0, 23), 5)

    def test_float_coded_reinterprets_bits(self):
        import struct as _struct
        frac = int.from_bytes(_struct.pack('>f', 1.0), 'big')
        self.assertEqual(rpu._combine_coef(0, frac, 1, 23), 1 << 23)


if __name__ == '__main__':
    unittest.main()
