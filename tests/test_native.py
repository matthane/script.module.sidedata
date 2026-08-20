import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import convert, native, rpu  # noqa: E402

# Golden fixtures are RPU payloads extracted from real commercial titles
# and are kept out of this public repo; they live on disk outside it
# instead (see .github/UPDATING.md). SIDEDATA_FIXTURES_DIR overrides the default
# location.
_FIXTURES_DIR = os.environ.get(
    'SIDEDATA_FIXTURES_DIR',
    os.path.expanduser('~/ce/dvhdr-testdata/module-fixtures'),
)
_FIXTURES_AVAILABLE = os.path.isdir(_FIXTURES_DIR) and bool(os.listdir(_FIXTURES_DIR))
_FIXTURES_SKIP_REASON = (
    'no fixture directory found - place the golden fixtures at ' +
    _FIXTURES_DIR + ' or point SIDEDATA_FIXTURES_DIR at them; see .github/UPDATING.md'
)
TESTDATA = _FIXTURES_DIR

# host-test libdovi build, outside the repo (see tools/build-libdovi.sh and
# .github/UPDATING.md) - wired in automatically so the golden fixtures below run
# through the real bindings on this host, not only on-device
_HOST_LIBDOVI = os.path.expanduser('~/ce/dvhdr-testdata/libdovi.so.3.4.0.x86_64')
if 'SIDEDATA_LIBDOVI_PATH' not in os.environ and os.path.isfile(_HOST_LIBDOVI):
    os.environ['SIDEDATA_LIBDOVI_PATH'] = _HOST_LIBDOVI


def _reset_native_cache():
    native._lib = None
    native._load_attempted = False
    native._last_error = None


_reset_native_cache()
_NATIVE_AVAILABLE = native.available()
_SKIP_REASON = (
    "no native libdovi found (SIDEDATA_LIBDOVI_PATH unset, "
    "~/ce/dvhdr-testdata/libdovi.so.3.4.0.x86_64 missing, and "
    "ctypes.util.find_library('dovi') found nothing) - tools/build-libdovi.sh "
    "documents building a host build the same way, see .github/UPDATING.md"
)


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


# shared by both golden fixture classes below: the vdr_dm_data scalar fields
# and header fields don't vary between the HEVC and AV1 T.35 delivery paths
def _assert_common_vdr_fields(tc, parsed, vdr):
    tc.assertEqual(parsed['source']['diagonal'], vdr['source_diagonal'])
    tc.assertEqual(parsed['affected_dm_metadata_id'], vdr['affected_dm_metadata_id'])
    tc.assertEqual(parsed['current_dm_metadata_id'], vdr['current_dm_metadata_id'])
    tc.assertEqual(parsed['scene_refresh_flag'], vdr['scene_refresh_flag'])

    colorimetry = parsed['colorimetry']
    tc.assertIsNotNone(colorimetry)
    tc.assertEqual(colorimetry['ycc_to_rgb_coef'], [vdr['ycc_to_rgb_coef%d' % i] for i in range(9)])
    tc.assertEqual(colorimetry['ycc_to_rgb_offset'], [vdr['ycc_to_rgb_offset%d' % i] for i in range(3)])
    tc.assertEqual(colorimetry['rgb_to_lms_coef'], [vdr['rgb_to_lms_coef%d' % i] for i in range(9)])
    tc.assertEqual(colorimetry['signal_eotf'], vdr['signal_eotf'])
    tc.assertEqual(colorimetry['signal_eotf_param0'], vdr['signal_eotf_param0'])
    tc.assertEqual(colorimetry['signal_eotf_param1'], vdr['signal_eotf_param1'])
    tc.assertEqual(colorimetry['signal_eotf_param2'], vdr['signal_eotf_param2'])
    tc.assertEqual(colorimetry['signal_bit_depth'], vdr['signal_bit_depth'])
    tc.assertEqual(colorimetry['signal_color_space'], vdr['signal_color_space'])
    tc.assertEqual(colorimetry['signal_chroma_format'], vdr['signal_chroma_format'])
    tc.assertEqual(colorimetry['signal_full_range_flag'], vdr['signal_full_range_flag'])


def _assert_common_header_fields(tc, parsed, header_truth):
    for key in ('chroma_resampling_explicit_filter_flag', 'coefficient_data_type',
                'coefficient_log2_denom', 'vdr_rpu_normalized_idc', 'bl_video_full_range_flag',
                'spatial_resampling_filter_flag', 'use_prev_vdr_rpu_flag', 'prev_vdr_rpu_id'):
        tc.assertEqual(parsed['header'][key], header_truth[key])


class TestGoldenHevcFixtures(unittest.TestCase):
    """Every golden HEVC RPU fixture this addon carries, run through the
    real libdovi bindings (rpu.parse_hevc_nal62, which dispatches straight
    to native.py), checked field-by-field against dovi_tool's own JSON dump
    of the same frame - this is the conformance proof for native.py's ctypes
    struct layouts, now that there's no pure-Python parser to cross-check
    against instead.
    """

    def _check_frame(self, name):
        raw, truth = _load_frame(name)
        nal62 = b'\x7c\x01' + raw
        parsed = rpu.parse_hevc_nal62(nal62)
        self.assertIsNotNone(parsed, 'parse failed for ' + name)

        vdr = truth['vdr_dm_data']
        blocks = _truth_blocks(truth)

        self.assertEqual(parsed['compressed'], vdr['compressed'])
        self.assertIsNotNone(parsed['source'])
        self.assertEqual(parsed['source']['min_pq'], vdr['source_min_pq'])
        self.assertEqual(parsed['source']['max_pq'], vdr['source_max_pq'])
        _assert_common_vdr_fields(self, parsed, vdr)

        l1_truth = blocks[1][0]
        self.assertIsNotNone(parsed['l1'])
        self.assertEqual(parsed['l1']['min_pq'], l1_truth['min_pq'])
        self.assertEqual(parsed['l1']['max_pq'], l1_truth['max_pq'])
        self.assertEqual(parsed['l1']['avg_pq'], l1_truth['avg_pq'])

        l2_truth_by_pq = {b['target_max_pq']: b for b in blocks.get(2, [])}
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

        if 3 in blocks:
            l3_truth = blocks[3][0]
            self.assertEqual(parsed['l3']['min_pq_offset'], l3_truth['min_pq_offset'])
            self.assertEqual(parsed['l3']['max_pq_offset'], l3_truth['max_pq_offset'])
            self.assertEqual(parsed['l3']['avg_pq_offset'], l3_truth['avg_pq_offset'])

        if 8 in blocks:
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

        if 9 in blocks:
            l9_truth = blocks[9][0]
            self.assertEqual(parsed['l9']['index'], l9_truth['source_primary_index'])
            self.assertEqual(parsed['l9']['has_coords'], l9_truth['length'] >= 17)
        else:
            self.assertIsNone(parsed['l9'])

        if 10 in blocks:
            l10_by_index = {e['target_display_index']: e for e in parsed['l10']}
            self.assertEqual(len(parsed['l10']), len(blocks[10]))
            for b in blocks[10]:
                entry = l10_by_index[b['target_display_index']]
                self.assertEqual(entry['target_max_pq'], b['target_max_pq'])
                self.assertEqual(entry['primary_index'], b['target_primary_index'])
        else:
            self.assertEqual(parsed['l10'], [])

        header_truth = truth['header']
        self.assertEqual(parsed['header']['el_spatial_resampling_filter_flag'],
                          header_truth['el_spatial_resampling_filter_flag'])
        self.assertEqual(parsed['header']['disable_residual_flag'],
                          header_truth['disable_residual_flag'])
        _assert_common_header_fields(self, parsed, header_truth)

        if 254 in blocks:
            self.assertEqual(parsed['cm_version'], '4.0')

        return parsed

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_signs_frame0(self):
        # Signs 2002 is profile 8.1, single layer - no L11, no enhancement
        # layer at all
        parsed = self._check_frame('signs_frame0')
        self.assertIsNone(parsed['l11'])
        self.assertIsNone(parsed['header']['el_type'])

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_signs_frame500_l8_l10(self):
        parsed = self._check_frame('signs_frame500')
        l10_by_index = {e['target_display_index']: e for e in parsed['l10']}
        self.assertIn(24, l10_by_index)
        self.assertIn(25, l10_by_index)
        self.assertEqual(l10_by_index[24]['target_max_pq'], 2547)
        self.assertEqual(l10_by_index[24]['nits'], 300)
        self.assertEqual(l10_by_index[24]['primary_index'], 0)
        self.assertEqual(l10_by_index[25]['target_max_pq'], 2547)
        self.assertEqual(l10_by_index[25]['nits'], 300)
        self.assertEqual(l10_by_index[25]['primary_index'], 2)

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv7fel_frame0_is_fel(self):
        parsed = self._check_frame('dv7fel_frame0')
        self.assertEqual(parsed['header']['el_type'], 'FEL')

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv7mel_frame0_is_mel(self):
        parsed = self._check_frame('dv7mel_frame0')
        self.assertEqual(parsed['header']['el_type'], 'MEL')


class TestGoldenAv1Fixtures(unittest.TestCase):
    """Golden-tested against real AV1+DV content, through rpu.parse_av1_t35:
    the dv10_av1_frame{0,700}.t35 fixtures (see .github/UPDATING.md for where they
    live) were walked out of a real AV1 elementary stream, checked against
    dovi_tool's own JSON dump of the same title's separately-extracted
    regular-RPU form at the matching frame index (see the git history for
    the full verification story - every one of the title's 1450 frames was
    cross-checked field-for-field during development).
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
        _assert_common_vdr_fields(self, parsed, vdr)

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
        _assert_common_header_fields(self, parsed, header_truth)

        return parsed

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_frame0(self):
        self._check_av1_frame('dv10_av1_frame0')

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_frame700(self):
        self._check_av1_frame('dv10_av1_frame700')


class TestNeverRaise(unittest.TestCase):
    """The never-raise contract, now exercised through the native paths:
    a missing library, a garbled payload, or a truncation/bit-flip must
    always degrade to None, whether or not a real libdovi is loaded.
    """

    def test_hevc_malformed_payloads_return_none(self):
        self.assertIsNone(rpu.parse_hevc_nal62(b''))
        self.assertIsNone(rpu.parse_hevc_nal62(b'\x00\x01\x02'))
        self.assertIsNone(rpu.parse_hevc_nal62(os.urandom(64)))
        self.assertIsNone(rpu.parse_hevc_nal62(b'not a nal'))

    def test_av1_malformed_payload_returns_none(self):
        self.assertIsNone(rpu.parse_av1_t35(b'not an obu'))

    def test_av1_gate_rejects_hevc_and_hdr10plus_payloads(self):
        hevc_style = b'\x7c\x01' + bytes(30)
        self.assertIsNone(rpu.parse_av1_t35(hevc_style))

        hdr10plus_style = bytes((0xB5, 0x00, 0x3C, 0x00, 0x01, 0x04)) + bytes(30)
        self.assertIsNone(rpu.parse_av1_t35(hdr10plus_style))

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    def test_av1_truncations_never_raise(self):
        payload, _truth = _load_av1_t35_frame('dv10_av1_frame0')
        for length in range(len(payload) + 1):
            try:
                rpu.parse_av1_t35(payload[:length])
            except Exception as exc:  # noqa: BLE001
                self.fail('parse_av1_t35 raised on truncation to %d bytes: %r' % (length, exc))

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    def test_av1_bit_flips_never_raise(self):
        payload, _truth = _load_av1_t35_frame('dv10_av1_frame0')
        header_region = min(24, len(payload))
        for i in range(header_region):
            for bit in range(8):
                corrupted = bytearray(payload)
                corrupted[i] ^= (1 << bit)
                try:
                    rpu.parse_av1_t35(bytes(corrupted))
                except Exception as exc:  # noqa: BLE001
                    self.fail('parse_av1_t35 raised on bit flip at byte %d bit %d: %r' % (i, bit, exc))

    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    def test_hevc_truncations_never_raise(self):
        raw, _truth = _load_frame('signs_frame0')
        nal62 = b'\x7c\x01' + raw
        for length in range(len(nal62) + 1):
            try:
                rpu.parse_hevc_nal62(nal62[:length])
            except Exception as exc:  # noqa: BLE001
                self.fail('parse_hevc_nal62 raised on truncation to %d bytes: %r' % (length, exc))


class TestNativeLoader(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.get('SIDEDATA_LIBDOVI_PATH')

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop('SIDEDATA_LIBDOVI_PATH', None)
        else:
            os.environ['SIDEDATA_LIBDOVI_PATH'] = self._old_env
        _reset_native_cache()

    def test_bogus_override_path_never_raises(self):
        os.environ['SIDEDATA_LIBDOVI_PATH'] = '/nonexistent/path/to/libdovi.so'
        _reset_native_cache()
        try:
            native.available()
        except Exception as exc:  # noqa: BLE001
            self.fail('native.available() raised: %r' % exc)

    def test_parse_functions_never_raise_when_unavailable(self):
        os.environ['SIDEDATA_LIBDOVI_PATH'] = '/nonexistent/path/to/libdovi.so'
        _reset_native_cache()
        self.assertIsNone(native.native_parse_hevc_nal62(b'not a nal'))
        self.assertIsNone(native.native_parse_av1_t35(b'not an obu'))


class TestNativeBundledArchFallback(unittest.TestCase):
    """The bundled aarch64 libdovi.so ships in this repo but can't load on
    this host's real architecture - platform.machine() is faked to
    'aarch64' so the bundled path resolves and CDLL genuinely attempts it,
    proving a wrong-arch load failure falls through the remaining
    candidates instead of raising.
    """

    def setUp(self):
        self._old_env = os.environ.pop('SIDEDATA_LIBDOVI_PATH', None)

    def tearDown(self):
        if self._old_env is not None:
            os.environ['SIDEDATA_LIBDOVI_PATH'] = self._old_env
        _reset_native_cache()

    def test_bundled_path_attempted_and_load_failure_falls_through(self):
        bundled_path = os.path.join(native._NATIVE_LIBS_DIR, 'aarch64', 'libdovi.so')
        self.assertTrue(os.path.isfile(bundled_path))

        attempted = []
        real_cdll = native.ctypes.CDLL

        def _spy_cdll(name, *args, **kwargs):
            attempted.append(name)
            return real_cdll(name, *args, **kwargs)

        with mock.patch.object(native.platform, 'machine', return_value='aarch64'), \
                mock.patch.object(native.ctypes, 'CDLL', side_effect=_spy_cdll):
            _reset_native_cache()
            try:
                native.available()
            except Exception as exc:  # noqa: BLE001
                self.fail('native.available() raised: %r' % exc)

        self.assertIn(bundled_path, attempted)


if __name__ == '__main__':
    unittest.main()
