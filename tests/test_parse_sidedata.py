import base64
import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

import sidedata  # noqa: E402
from test_hdr10plus import _find_first_hdr10plus_sei  # noqa: E402

TESTDATA = os.path.join(os.path.dirname(__file__), 'testdata')


def _b64(raw):
    return base64.b64encode(raw).decode('ascii')


def _build_sidedata_json():
    with open(os.path.join(TESTDATA, 'signs_frame0.rpu'), 'rb') as f:
        raw_rpu = f.read()
    nal62 = b'\x7c\x01' + raw_rpu

    with open(os.path.join(TESTDATA, 'lake10_prefix.hevc'), 'rb') as f:
        hevc = f.read()
    hdr10plus_payload = _find_first_hdr10plus_sei(hevc)

    config = bytes.fromhex('01000e3760') + bytes(19)

    mdcv = struct.pack(
        '>8HII',
        8500, 39850,  # green x,y
        6550, 2300,  # blue x,y
        35400, 14600,  # red x,y
        15635, 16450,  # white x,y
        10000000, 1,  # max/min luminance
    )

    cll = bytes.fromhex('03e80190')

    payload = {
        'dovi.flags': 'converted rpu-removed',
        'dovi.config': _b64(config),
        'dovi.rpu': _b64(nal62),
        'hdr10plus': _b64(hdr10plus_payload),
        'mdcv': _b64(mdcv),
        'cll': _b64(cll),
    }
    return json.dumps(payload)


class TestParseSidedata(unittest.TestCase):
    def test_all_sections_present(self):
        result = sidedata.parse_sidedata(_build_sidedata_json())

        self.assertEqual(result['flags'], ['converted', 'rpu-removed'])
        self.assertIsNotNone(result['config'])
        self.assertEqual(result['config']['profile'], 7)
        self.assertIsNotNone(result['rpu'])
        self.assertIsNotNone(result['rpu']['l1'])
        self.assertIsNotNone(result['hdr10plus'])
        self.assertEqual(result['hdr10plus']['application_version'], 1)
        self.assertIsNotNone(result['mdcv'])
        self.assertIsNotNone(result['mdcv']['primaries'])
        self.assertIsNotNone(result['cll'])
        self.assertEqual(result['cll']['max_cll'], 1000)
        self.assertEqual(result['cll']['max_fall'], 400)

    def test_empty_string(self):
        result = sidedata.parse_sidedata('')
        self.assertEqual(result, {
            'flags': [], 'config': None, 'rpu': None,
            'hdr10plus': None, 'mdcv': None, 'cll': None,
        })

    def test_empty_object(self):
        result = sidedata.parse_sidedata('{}')
        self.assertEqual(result, {
            'flags': [], 'config': None, 'rpu': None,
            'hdr10plus': None, 'mdcv': None, 'cll': None,
        })

    def test_none_input(self):
        result = sidedata.parse_sidedata(None)
        self.assertEqual(result['flags'], [])
        self.assertIsNone(result['rpu'])

    def test_garbage_json_does_not_raise(self):
        result = sidedata.parse_sidedata('{not valid json')
        self.assertEqual(result['flags'], [])
        self.assertIsNone(result['config'])

    def test_garbage_base64_does_not_raise(self):
        result = sidedata.parse_sidedata(json.dumps({'dovi.config': 'not-base64!!'}))
        self.assertIsNone(result['config'])


if __name__ == '__main__':
    unittest.main()
