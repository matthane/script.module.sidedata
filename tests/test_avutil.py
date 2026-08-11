import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import avutil  # noqa: E402


def _reset_avutil_cache():
    avutil._lib = None
    avutil._load_attempted = False


class TestAvutilLoader(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.get('SIDEDATA_LIBAVUTIL_PATH')

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop('SIDEDATA_LIBAVUTIL_PATH', None)
        else:
            os.environ['SIDEDATA_LIBAVUTIL_PATH'] = self._old_env
        _reset_avutil_cache()

    def test_bogus_override_path_never_raises(self):
        os.environ['SIDEDATA_LIBAVUTIL_PATH'] = '/nonexistent/path/to/libavutil.so'
        _reset_avutil_cache()
        try:
            avutil.available()
        except Exception as exc:  # noqa: BLE001
            self.fail('avutil.available() raised: %r' % exc)

    def test_parse_t35_never_raises_when_unavailable(self):
        os.environ['SIDEDATA_LIBAVUTIL_PATH'] = '/nonexistent/path/to/libavutil.so'
        _reset_avutil_cache()
        self.assertIsNone(avutil.parse_t35(b'not a t35 payload'))


class TestAvutilVersionGate(unittest.TestCase):
    """This host's own libavutil (via ctypes.util.find_library('avutil'), or
    the CE-22 libavutil.so.60 build if SIDEDATA_LIBAVUTIL_PATH points at
    one) is only usable when its major matches the pinned struct layout.
    On a typical dev host the system ffmpeg is a different major, so this
    documents the mismatch being rejected rather than silently trusted.
    """

    def setUp(self):
        self._old_env = os.environ.pop('SIDEDATA_LIBAVUTIL_PATH', None)

    def tearDown(self):
        if self._old_env is not None:
            os.environ['SIDEDATA_LIBAVUTIL_PATH'] = self._old_env
        _reset_avutil_cache()

    def test_mismatched_major_is_treated_as_unavailable(self):
        import ctypes.util
        found = ctypes.util.find_library('avutil')
        if not found:
            self.skipTest('no system libavutil found via find_library')

        import ctypes
        lib = ctypes.CDLL(found)
        major = lib.avutil_version() >> 16
        if major == avutil._LIBAVUTIL_VERSION_MAJOR:
            self.skipTest('system libavutil happens to be major %d already' % major)

        _reset_avutil_cache()
        self.assertFalse(avutil.available())


class TestParseT35NeverRaises(unittest.TestCase):
    """Holds regardless of whether a matching libavutil is available."""

    def test_malformed_payloads_return_none(self):
        self.assertIsNone(avutil.parse_t35(b''))
        self.assertIsNone(avutil.parse_t35(os.urandom(4)))

    def test_negative_control_not_hdr10plus(self):
        bogus = bytes((0xB5, 0x00, 0x31, 0x47, 0x41, 0x39, 0x34, 0x00, 0x00))
        self.assertIsNone(avutil.parse_t35(bogus))


if __name__ == '__main__':
    unittest.main()
