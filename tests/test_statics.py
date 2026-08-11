import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import statics  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_dvcc_vector(self):
        # version 1.0, profile 7, level 6, rpu/el/bl all present, compat_id 6, compression 0
        data = bytes.fromhex('01000e3760') + bytes(19)
        cfg = statics.parse_config(data)
        self.assertEqual(cfg['version_major'], 1)
        self.assertEqual(cfg['version_minor'], 0)
        self.assertEqual(cfg['profile'], 7)
        self.assertEqual(cfg['level'], 6)
        self.assertTrue(cfg['rpu_present'])
        self.assertTrue(cfg['el_present'])
        self.assertTrue(cfg['bl_present'])
        self.assertEqual(cfg['compat_id'], 6)
        self.assertEqual(cfg['md_compression'], 0)

    def test_short_payload_is_none(self):
        self.assertIsNone(statics.parse_config(b'\x01\x00'))


class TestMdcv(unittest.TestCase):
    def test_round_trip(self):
        green = (0.170, 0.797)
        blue = (0.131, 0.046)
        red = (0.708, 0.292)
        white = (0.3127, 0.3290)
        max_lum = 1000.0
        min_lum = 0.0001

        payload = struct.pack(
            '>8HII',
            round(green[0] * 50000), round(green[1] * 50000),
            round(blue[0] * 50000), round(blue[1] * 50000),
            round(red[0] * 50000), round(red[1] * 50000),
            round(white[0] * 50000), round(white[1] * 50000),
            round(max_lum * 10000), round(min_lum * 10000),
        )
        mdcv = statics.parse_mdcv(payload)
        self.assertIsNotNone(mdcv['primaries'])
        self.assertAlmostEqual(mdcv['primaries']['green'][0], green[0], places=4)
        self.assertAlmostEqual(mdcv['primaries']['green'][1], green[1], places=4)
        self.assertAlmostEqual(mdcv['primaries']['blue'][0], blue[0], places=4)
        self.assertAlmostEqual(mdcv['primaries']['red'][1], red[1], places=4)
        self.assertAlmostEqual(mdcv['white_point'][0], white[0], places=4)
        self.assertAlmostEqual(mdcv['max_luminance'], max_lum, places=2)
        self.assertAlmostEqual(mdcv['min_luminance'], min_lum, places=4)

    def test_all_zero_primaries_is_unknown(self):
        payload = struct.pack('>8HII', 0, 0, 0, 0, 0, 0, 15635, 16450, 10000000, 1)
        mdcv = statics.parse_mdcv(payload)
        self.assertIsNone(mdcv['primaries'])
        self.assertAlmostEqual(mdcv['white_point'][0], 0.3127, places=4)


class TestCll(unittest.TestCase):
    def test_vector(self):
        cll = statics.parse_cll(bytes.fromhex('03e80190'))
        self.assertEqual(cll['max_cll'], 1000)
        self.assertEqual(cll['max_fall'], 400)


if __name__ == '__main__':
    unittest.main()
