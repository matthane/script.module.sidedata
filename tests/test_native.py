import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from sidedata import native, rpu  # noqa: E402
from test_rpu import _load_av1_t35_frame, _load_frame  # noqa: E402


def _reset_native_cache():
    native._lib = None
    native._load_attempted = False
    native._last_error = None


_reset_native_cache()
_NATIVE_AVAILABLE = native.available()
_SKIP_REASON = (
    "no native libdovi found (SIDEDATA_LIBDOVI_PATH unset and "
    "ctypes.util.find_library('dovi') found nothing) - build libdovi-3.3.1's "
    "cdylib for this host with cargo cbuild and point SIDEDATA_LIBDOVI_PATH "
    "at it to run the native/pure conformance check"
)


class TestNativeConformance(unittest.TestCase):
    """The key test: every golden RPU fixture this addon carries, run
    through both backends, must produce the identical result dict. This is
    what actually proves the ctypes struct layouts in native.py are correct
    - a field slip would silently corrupt values rather than crash, so
    dict equality against the already dovi_tool-validated pure parser is
    the only thing that catches it.
    """

    def _assert_hevc_matches(self, name):
        raw, _truth = _load_frame(name)
        nal62 = b'\x7c\x01' + raw
        native_result = native.native_parse_hevc_nal62(nal62)
        pure_result = rpu._pure_parse_hevc_nal62(nal62)
        self.assertIsNotNone(native_result, 'native parse failed for ' + name)
        self.assertIsNotNone(pure_result, 'pure parse failed for ' + name)
        self.assertEqual(native_result, pure_result)

    def _assert_av1_matches(self, name):
        payload, _truth = _load_av1_t35_frame(name)
        native_result = native.native_parse_av1_t35(payload)
        pure_result = rpu._pure_parse_av1_t35(payload)
        self.assertIsNotNone(native_result, 'native parse failed for ' + name)
        self.assertIsNotNone(pure_result, 'pure parse failed for ' + name)
        self.assertEqual(native_result, pure_result)

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_signs_frame0(self):
        self._assert_hevc_matches('signs_frame0')

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_signs_frame500(self):
        self._assert_hevc_matches('signs_frame500')

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv7fel_frame0(self):
        self._assert_hevc_matches('dv7fel_frame0')

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv7mel_frame0(self):
        self._assert_hevc_matches('dv7mel_frame0')

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv10_av1_frame0(self):
        self._assert_av1_matches('dv10_av1_frame0')

    @unittest.skipUnless(_NATIVE_AVAILABLE, _SKIP_REASON)
    def test_dv10_av1_frame700(self):
        self._assert_av1_matches('dv10_av1_frame700')


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


class TestRpuDispatchFallback(unittest.TestCase):
    """rpu.py's dispatch logic, exercised without needing a real libdovi.so
    by swapping in fake native.available/native_parse_hevc_nal62 - the
    per-payload fallback and the log-once gate are backend-independent
    behavior that must hold whether or not this host can build libdovi.
    """

    def setUp(self):
        self._orig_available = native.available
        self._orig_hevc = native.native_parse_hevc_nal62
        rpu._fallback_logged = False

    def tearDown(self):
        native.available = self._orig_available
        native.native_parse_hevc_nal62 = self._orig_hevc

    def test_native_exception_falls_back_to_pure_for_this_payload(self):
        native.available = lambda: True

        def _boom(nal):
            raise RuntimeError('boom')

        native.native_parse_hevc_nal62 = _boom

        raw, _truth = _load_frame('signs_frame0')
        nal62 = b'\x7c\x01' + raw
        result = rpu.parse_hevc_nal62(nal62)
        self.assertEqual(result, rpu._pure_parse_hevc_nal62(nal62))

    def test_native_none_on_real_rpu_falls_back_and_logs_once(self):
        native.available = lambda: True
        native.native_parse_hevc_nal62 = lambda nal: None

        raw, _truth = _load_frame('signs_frame0')
        nal62 = b'\x7c\x01' + raw
        result = rpu.parse_hevc_nal62(nal62)
        self.assertEqual(result, rpu._pure_parse_hevc_nal62(nal62))
        self.assertTrue(rpu._fallback_logged)

    def test_native_none_on_non_rpu_input_does_not_log(self):
        native.available = lambda: True
        native.native_parse_hevc_nal62 = lambda nal: None

        result = rpu.parse_hevc_nal62(b'not a nal')
        self.assertIsNone(result)
        self.assertFalse(rpu._fallback_logged)


class TestParserBackend(unittest.TestCase):
    def setUp(self):
        self._orig_available = native.available

    def tearDown(self):
        native.available = self._orig_available

    def test_reports_builtin_without_native(self):
        native.available = lambda: False
        self.assertEqual(rpu.parser_backend(), 'builtin')

    def test_reports_libdovi_when_native_available(self):
        native.available = lambda: True
        self.assertEqual(rpu.parser_backend(), 'libdovi')


if __name__ == '__main__':
    unittest.main()
