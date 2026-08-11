import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import hdr10plus  # noqa: E402

TESTDATA = os.path.join(os.path.dirname(__file__), 'testdata')

_SIGNATURE = bytes((0xB5, 0x00, 0x3C, 0x00, 0x01, 0x04))


def _nals(buf):
    start = None
    i = 0
    while i + 2 < len(buf):
        if buf[i] == 0 and buf[i + 1] == 0 and buf[i + 2] == 1:
            if start is not None:
                end = i
                while end > start and buf[end - 1] == 0:
                    end -= 1
                yield buf[start:end]
            start = i + 3
            i += 3
        else:
            i += 1
    if start is not None:
        yield buf[start:]


def _unescape(nal):
    out = bytearray()
    i = 0
    while i < len(nal):
        if i + 2 < len(nal) and nal[i] == 0 and nal[i + 1] == 0 and nal[i + 2] == 3:
            out += b'\x00\x00'
            i += 3
        else:
            out.append(nal[i])
            i += 1
    return bytes(out)


def _find_first_hdr10plus_sei(data):
    """Small SEI walk: HEVC NAL type 39 (PREFIX_SEI), payload type 4
    (user_data_registered_itu_t_t35), ST 2094-40 signature."""
    for nal in _nals(data):
        if len(nal) < 3 or ((nal[0] >> 1) & 0x3F) != 39:
            continue
        rbsp = _unescape(nal[2:])
        p = 0
        while p + 2 < len(rbsp):
            t = 0
            while p < len(rbsp) and rbsp[p] == 0xFF:
                t += 255
                p += 1
            if p >= len(rbsp):
                break
            t += rbsp[p]
            p += 1

            sz = 0
            while p < len(rbsp) and rbsp[p] == 0xFF:
                sz += 255
                p += 1
            if p >= len(rbsp):
                break
            sz += rbsp[p]
            p += 1

            if sz > len(rbsp) - p:
                break
            payload = rbsp[p:p + sz]
            p += sz

            if t == 4 and len(payload) >= 6 and payload[:6] == _SIGNATURE:
                return payload
    return None


class TestHdr10Plus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(TESTDATA, 'lake10_prefix.hevc'), 'rb') as f:
            data = f.read()
        cls.payload = _find_first_hdr10plus_sei(data)

    def test_sei_found(self):
        self.assertIsNotNone(self.payload)

    def test_lake_known_values(self):
        result = hdr10plus.parse_t35(self.payload)
        self.assertIsNotNone(result)
        self.assertEqual(result['application_version'], 1)
        self.assertEqual(result['num_windows'], 1)
        self.assertEqual(result['targeted_system_display_maximum_luminance'], 300)
        self.assertEqual(result['profile'], 'B')
        self.assertEqual(len(result['bezier_anchors']), 9)
        self.assertEqual(result['knee_point_x'], 0.0)
        self.assertEqual(result['knee_point_y'], 0.0)

        # codes cross-checked against the device host test (hdr10p_test.cpp)
        # that fed this same sample through ffmpeg's own T.35 decoder
        self.assertAlmostEqual(result['maxscl'][0], 395.6, places=4)
        self.assertAlmostEqual(result['maxscl'][1], 206.3, places=4)
        self.assertAlmostEqual(result['maxscl'][2], 204.7, places=4)
        self.assertAlmostEqual(result['average_maxrgb'], 9.3, places=4)
        self.assertAlmostEqual(result['fraction_bright_pixels'], 0.0, places=4)

        self.assertEqual(len(result['distribution']), 9)
        self.assertAlmostEqual(result['distribution'][1]['nits'], 209.4, places=4)
        self.assertAlmostEqual(result['distribution'][8]['nits'], 288.8, places=4)
        self.assertEqual(
            [d['percentage'] for d in result['distribution']],
            [1, 5, 10, 25, 50, 75, 90, 95, 99],
        )

    def test_negative_control_not_hdr10plus(self):
        bogus = bytes((0xB5, 0x00, 0x31, 0x47, 0x41, 0x39, 0x34, 0x00, 0x00))
        self.assertIsNone(hdr10plus.parse_t35(bogus))

    def test_malformed_returns_none(self):
        self.assertIsNone(hdr10plus.parse_t35(b''))
        self.assertIsNone(hdr10plus.parse_t35(os.urandom(4)))


if __name__ == '__main__':
    unittest.main()
