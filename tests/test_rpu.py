import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from dvhdr import convert, rpu  # noqa: E402

TESTDATA = os.path.join(os.path.dirname(__file__), 'testdata')


def _load_frame(name):
    with open(os.path.join(TESTDATA, name + '.rpu'), 'rb') as f:
        raw = f.read()
    with open(os.path.join(TESTDATA, name + '.json'), encoding='utf-8') as f:
        truth = json.load(f)
    return raw, truth


def _truth_blocks(truth):
    vdr = truth['vdr_dm_data']
    blocks = {}
    for group in ('cmv29_metadata', 'cmv40_metadata'):
        for entry in vdr[group]['ext_metadata_blocks']:
            (level_name, fields), = entry.items()
            level = int(level_name.replace('Level', ''))
            blocks.setdefault(level, []).append(fields)
    return blocks


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


if __name__ == '__main__':
    unittest.main()
