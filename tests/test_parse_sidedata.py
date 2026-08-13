import base64
import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

import sidedata  # noqa: E402
from sidedata import avutil, native  # noqa: E402
from test_hdr10plus import _find_first_hdr10plus_sei  # noqa: E402

# see test_native.py for why this is wired here too: this file must be
# runnable standalone, not only via `discover`'s alphabetical module order.
# Golden fixtures live outside this public repo (see .github/UPDATING.md);
# SIDEDATA_FIXTURES_DIR overrides the default location.
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
_HOST_LIBDOVI = os.path.expanduser('~/ce/dvhdr-testdata/libdovi.so.3.3.1.x86_64')
if 'SIDEDATA_LIBDOVI_PATH' not in os.environ and os.path.isfile(_HOST_LIBDOVI):
    os.environ['SIDEDATA_LIBDOVI_PATH'] = _HOST_LIBDOVI
_NATIVE_AVAILABLE = native.available()
_AVUTIL_AVAILABLE = avutil.available()


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
        'flags': 'converted rpu-removed',
        'dovi.config': _b64(config),
        'dovi.rpu': _b64(nal62),
        'hdr10plus': _b64(hdr10plus_payload),
        'mdcv': _b64(mdcv),
        'cll': _b64(cll),
    }
    return json.dumps(payload)


class TestParseSidedata(unittest.TestCase):
    @unittest.skipUnless(_FIXTURES_AVAILABLE, _FIXTURES_SKIP_REASON)
    def test_all_sections_present(self):
        result = sidedata.parse_sidedata(_build_sidedata_json())

        self.assertEqual(result['flags'], ['converted', 'rpu-removed'])
        self.assertIsNotNone(result['config'])
        self.assertEqual(result['config']['profile'], 7)
        self.assertIsNotNone(result['mdcv'])
        self.assertIsNotNone(result['mdcv']['primaries'])
        self.assertIsNotNone(result['cll'])
        self.assertEqual(result['cll']['max_cll'], 1000)
        self.assertEqual(result['cll']['max_fall'], 400)

        if _NATIVE_AVAILABLE:
            self.assertIsNotNone(result['rpu'])
            self.assertIsNotNone(result['rpu']['l1'])
        else:
            self.assertIsNone(result['rpu'])

        if _AVUTIL_AVAILABLE:
            self.assertIsNotNone(result['hdr10plus'])
            self.assertEqual(result['hdr10plus']['application_version'], 1)
        else:
            self.assertIsNone(result['hdr10plus'])

    def test_structure_present(self):
        result = sidedata.parse_sidedata(json.dumps({'structure': 'st-dl'}))
        self.assertEqual(result['structure'], 'st-dl')

    def test_structure_absent(self):
        result = sidedata.parse_sidedata(json.dumps({'flags': 'converted'}))
        self.assertIsNone(result['structure'])

    def test_structure_wrong_type_is_none(self):
        result = sidedata.parse_sidedata(json.dumps({'structure': 7}))
        self.assertIsNone(result['structure'])

    def test_empty_string(self):
        result = sidedata.parse_sidedata('')
        self.assertEqual(result, {
            'flags': [], 'structure': None, 'config': None, 'rpu': None,
            'hdr10plus': None, 'mdcv': None, 'cll': None,
        })

    def test_empty_object(self):
        result = sidedata.parse_sidedata('{}')
        self.assertEqual(result, {
            'flags': [], 'structure': None, 'config': None, 'rpu': None,
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
