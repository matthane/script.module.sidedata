import os
import sys
import types
import unittest
from unittest import mock

# service.py is a Kodi service script, so xbmc/xbmcgui must exist in
# sys.modules before it can be imported at all; stub the pieces the module
# touches at import time and at call time.
_fake_xbmc = types.ModuleType('xbmc')
_fake_xbmc.LOGDEBUG = 0
_fake_xbmc.LOGINFO = 1
_fake_xbmc.LOGWARNING = 3
_fake_xbmc.LOGERROR = 4
_fake_xbmc.log_calls = []
_fake_xbmc.info_label = ''


def _fake_log(msg, level=_fake_xbmc.LOGDEBUG):
    _fake_xbmc.log_calls.append((msg, level))


def _fake_get_info_label(label):
    return _fake_xbmc.info_label


class _FakeMonitor(object):
    def __init__(self):
        self.abort = False

    def abortRequested(self):
        return self.abort

    def waitForAbort(self, timeout):
        return self.abort


class _FakePlayer(object):
    def __init__(self, playing=False):
        self.playing = playing
        self.fail = False

    def isPlayingVideo(self):
        if self.fail:
            raise RuntimeError('player is unavailable')
        return self.playing


_fake_xbmc.Monitor = _FakeMonitor
_fake_xbmc.Player = _FakePlayer
_fake_xbmc.log = _fake_log
_fake_xbmc.getInfoLabel = _fake_get_info_label
sys.modules['xbmc'] = _fake_xbmc


class _FakeWindow(object):
    def __init__(self, window_id):
        self.window_id = window_id
        self.properties = {}
        # keys in these sets raise instead of taking effect, so tests can
        # force _publish/_clear to fail partway through
        self.fail_set_keys = set()
        self.fail_clear_keys = set()

    def setProperty(self, key, value):
        if key in self.fail_set_keys:
            raise RuntimeError('setProperty failed for ' + key)
        self.properties[key] = value

    def clearProperty(self, key):
        if key in self.fail_clear_keys:
            raise RuntimeError('clearProperty failed for ' + key)
        self.properties.pop(key, None)

    def getProperty(self, key):
        return self.properties.get(key, '')


_fake_xbmcgui = types.ModuleType('xbmcgui')
_fake_xbmcgui.Window = _FakeWindow
sys.modules['xbmcgui'] = _fake_xbmcgui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import service  # noqa: E402


def _sample_parsed():
    return {
        'flags': ['converted', 'rpu-removed'],
        'structure': 'st-dl',
        'config': {
            'version_major': 1, 'version_minor': 0, 'profile': 7, 'level': 6,
            'rpu_present': True, 'el_present': True, 'bl_present': True,
            'compat_id': 6, 'md_compression': 2,
        },
        'rpu': {
            'profile': 7,
            'header': {
                'rpu_type': 2, 'rpu_format': 18,
                'vdr_rpu_profile': 1, 'vdr_rpu_level': 0,
                'bl_bit_depth': 10, 'el_bit_depth': 10, 'vdr_bit_depth': 12,
                'el_spatial_resampling_filter_flag': True,
                'disable_residual_flag': False,
                'el_type': 'FEL',
            },
            'compressed': False,
            'cm_version': '2.9',
            'source': {
                'min_pq': 0, 'min_nits': 0.0001, 'max_pq': 3079, 'max_nits': 1000.0,
            },
            'l1': {
                'min_pq': 0, 'min_nits': 0.0, 'max_pq': 2500, 'max_nits': 480.0,
                'avg_pq': 800, 'avg_nits': 30.5,
            },
            'l2': [
                {
                    'nits': 100, 'slope': 2048, 'offset': 2048, 'power': 2048,
                    'chromaweight': 2048, 'saturation': 2048, 'tonedetail': None,
                    'ui': {'gain': 0.0, 'lift': 0.0, 'gamma': 0.0, 'chromaweight': 0.0,
                           'saturation': 0.0, 'tonedetail': None},
                },
                {
                    'nits': 600, 'slope': 2100, 'offset': 2000, 'power': 2200,
                    'chromaweight': 2100, 'saturation': 1900, 'tonedetail': 512,
                    'ui': {'gain': 0.025390625, 'lift': -0.1, 'gamma': 0.05,
                           'chromaweight': 0.025390625, 'saturation': -0.09765625,
                           'tonedetail': -0.75},
                },
            ],
            'l3': None,
            'l5': None,
            'l6': {
                'max_cll': 1000, 'max_fall': 400, 'min_lum_raw': 1, 'min_lum_nits': 0.0001,
                'max_lum_raw': 1000, 'max_lum_nits': 1000,
            },
            'l8': [
                {
                    'nits': 300, 'target_display_index': 1, 'slope': 2048, 'offset': 2048,
                    'power': 2048, 'chromaweight': 2048, 'saturation': 2048, 'tonedetail': 512,
                    'ui': {'gain': 0.0, 'lift': 0.0, 'gamma': 0.0, 'chromaweight': 0.0,
                           'saturation': 0.0, 'tonedetail': 0.0},
                    'mid_contrast': 2048, 'clip_trim': 0,
                },
            ],
            'l9': None,
            'l10': [
                {
                    'target_display_index': 1, 'nits': 300, 'target_max_pq': 2081,
                    'target_min_pq': 0, 'primary_index': 0, 'primary_name': 'DCI-P3 D65',
                    'has_coords': False,
                },
            ],
            'l11': {
                'content_type': 1, 'content_type_name': 'Movies', 'whitepoint': 0,
                'whitepoint_kelvin': 6504, 'whitepoint_name': '6504K (D65)',
                'reference_mode': False,
            },
        },
        'hdr10plus': {
            'application_version': 1, 'num_windows': 1,
            'targeted_system_display_maximum_luminance': 1000,
            'maxscl': [800.0, 850.5, 900.0],
            'average_maxrgb': 500.25,
            'distribution': [
                {'percentage': 1, 'nits': 10.0},
                {'percentage': 50, 'nits': 200.5},
                {'percentage': 99, 'nits': 900.0},
            ],
            'fraction_bright_pixels': 5.5,
            'profile': 'B',
            'knee_point_x': 0.5, 'knee_point_y': 0.6,
            'bezier_anchors': [100, 200, 300],
        },
        'mdcv': {
            'primaries': {
                'red': (0.68, 0.32), 'green': (0.265, 0.69), 'blue': (0.15, 0.06),
            },
            'white_point': (0.3127, 0.329),
            'max_luminance': 1000.0, 'min_luminance': 0.0001,
        },
        'cll': {'max_cll': 1000, 'max_fall': 400},
    }


def _empty_parsed():
    return {
        'flags': [],
        'structure': None,
        'config': None,
        'rpu': None,
        'hdr10plus': None,
        'mdcv': None,
        'cll': None,
    }


class TestFormatScalar(unittest.TestCase):
    def test_bool_renders_lowercase(self):
        self.assertEqual(service._format_scalar(True), 'true')
        self.assertEqual(service._format_scalar(False), 'false')

    def test_int_passthrough(self):
        self.assertEqual(service._format_scalar(300), '300')

    def test_string_passthrough(self):
        self.assertEqual(service._format_scalar('FEL'), 'FEL')

    def test_float_trims_trailing_zeros(self):
        self.assertEqual(service._format_scalar(1000.0), '1000')
        self.assertEqual(service._format_scalar(30.5), '30.5')

    def test_float_keeps_small_value_precision(self):
        self.assertEqual(service._format_scalar(0.0001), '0.0001')

    def test_float_keeps_exact_binary_fraction(self):
        self.assertEqual(service._format_scalar(0.025390625), '0.025390625')

    def test_nonfinite_floats_produce_no_value(self):
        self.assertIsNone(service._format_scalar(float('inf')))
        self.assertIsNone(service._format_scalar(float('-inf')))
        self.assertIsNone(service._format_scalar(float('nan')))


class TestFlattenSidedata(unittest.TestCase):
    def setUp(self):
        self.flat = service.flatten_sidedata(_sample_parsed())

    def test_top_level_scalars(self):
        self.assertEqual(self.flat['sidedata.flags'], 'converted rpu-removed')
        self.assertEqual(self.flat['sidedata.structure'], 'st-dl')

    def test_config_nested_dict(self):
        self.assertEqual(self.flat['sidedata.config.profile'], '7')
        self.assertEqual(self.flat['sidedata.config.rpu_present'], 'true')
        self.assertEqual(self.flat['sidedata.config.bl_present'], 'true')

    def test_rpu_header_nested_path(self):
        self.assertEqual(self.flat['sidedata.rpu.header.el_type'], 'FEL')
        self.assertEqual(self.flat['sidedata.rpu.header.bl_bit_depth'], '10')
        self.assertEqual(
            self.flat['sidedata.rpu.header.el_spatial_resampling_filter_flag'], 'true')

    def test_rpu_source_and_l1(self):
        self.assertEqual(self.flat['sidedata.rpu.source.min_nits'], '0.0001')
        self.assertEqual(self.flat['sidedata.rpu.l1.avg_nits'], '30.5')

    def test_rpu_l6_underscored_leaf(self):
        self.assertEqual(self.flat['sidedata.rpu.l6.max_cll'], '1000')
        self.assertEqual(self.flat['sidedata.rpu.l6.min_lum_nits'], '0.0001')

    def test_rpu_l2_keyed_by_nits(self):
        self.assertEqual(self.flat['sidedata.rpu.l2.600.slope'], '2100')
        self.assertEqual(self.flat['sidedata.rpu.l2.600.ui.gain'], '0.025390625')
        self.assertEqual(self.flat['sidedata.rpu.l2.100.ui.gain'], '0')
        self.assertEqual(self.flat['sidedata.rpu.l2.nits'], '100 600')
        self.assertNotIn('sidedata.rpu.l2.100.tonedetail', self.flat)
        self.assertNotIn('sidedata.rpu.l2.100.ui.tonedetail', self.flat)

    def test_rpu_l8_keyed_by_nits(self):
        self.assertEqual(self.flat['sidedata.rpu.l8.300.target_display_index'], '1')
        self.assertEqual(self.flat['sidedata.rpu.l8.300.mid_contrast'], '2048')
        self.assertEqual(self.flat['sidedata.rpu.l8.nits'], '300')

    def test_rpu_l10_keyed_by_target_display_index(self):
        self.assertEqual(self.flat['sidedata.rpu.l10.1.nits'], '300')
        self.assertEqual(self.flat['sidedata.rpu.l10.1.primary_name'], 'DCI-P3 D65')
        self.assertEqual(self.flat['sidedata.rpu.l10.indexes'], '1')

    def test_rpu_l9_absent_produces_no_property(self):
        for key in self.flat:
            self.assertFalse(key.startswith('sidedata.rpu.l9'))

    def test_hdr10plus_maxscl_and_bezier_anchors_space_joined(self):
        self.assertEqual(self.flat['sidedata.hdr10plus.maxscl'], '800 850.5 900')
        self.assertEqual(self.flat['sidedata.hdr10plus.bezier_anchors'], '100 200 300')

    def test_hdr10plus_distribution_keyed_by_percentile(self):
        self.assertEqual(self.flat['sidedata.hdr10plus.distribution.1'], '10')
        self.assertEqual(self.flat['sidedata.hdr10plus.distribution.50'], '200.5')
        self.assertEqual(self.flat['sidedata.hdr10plus.distribution.percentages'], '1 50 99')

    def test_mdcv_primaries_tuple_split(self):
        self.assertEqual(self.flat['sidedata.mdcv.primaries.red.x'], '0.68')
        self.assertEqual(self.flat['sidedata.mdcv.primaries.red.y'], '0.32')
        self.assertEqual(self.flat['sidedata.mdcv.white_point.x'], '0.3127')
        self.assertEqual(self.flat['sidedata.mdcv.white_point.y'], '0.329')

    def test_cll(self):
        self.assertEqual(self.flat['sidedata.cll.max_cll'], '1000')
        self.assertEqual(self.flat['sidedata.cll.max_fall'], '400')

    def test_none_sections_produce_no_properties(self):
        parsed = _sample_parsed()
        parsed['rpu'] = None
        parsed['hdr10plus'] = None
        parsed['mdcv'] = None
        flat = service.flatten_sidedata(parsed)
        for key in flat:
            self.assertFalse(key.startswith('sidedata.rpu'))
            self.assertFalse(key.startswith('sidedata.hdr10plus'))
            self.assertFalse(key.startswith('sidedata.mdcv'))

    def test_empty_flags_list_produces_no_property(self):
        parsed = _sample_parsed()
        parsed['flags'] = []
        flat = service.flatten_sidedata(parsed)
        self.assertNotIn('sidedata.flags', flat)

    def test_non_dict_input_returns_empty(self):
        self.assertEqual(service.flatten_sidedata(None), {})
        self.assertEqual(service.flatten_sidedata('not a dict'), {})


class TestFlattenCollisions(unittest.TestCase):
    """snap_target_nits (convert.py) buckets distinct blocks onto the same
    nits value, and duplicate target_display_index blocks are possible too
    (see FIELDS.md's l8/l10 sections); the flattener must keep both entries
    rather than letting the second overwrite the first under one key.
    """

    def test_l2_duplicate_nits_get_ordinal_suffix(self):
        entries = [
            {'nits': 300, 'slope': 2048},
            {'nits': 300, 'slope': 2200},
            {'nits': 100, 'slope': 1900},
        ]
        out = {}
        service._flatten_trim_list('sidedata.rpu.l2', entries, 'sidedata.rpu.l2.nits', out)

        self.assertEqual(out['sidedata.rpu.l2.300.slope'], '2048')
        self.assertEqual(out['sidedata.rpu.l2.300-2.slope'], '2200')
        self.assertEqual(out['sidedata.rpu.l2.100.slope'], '1900')
        self.assertEqual(out['sidedata.rpu.l2.nits'], '300 300-2 100')

    def test_l10_duplicate_target_display_index_get_ordinal_suffix(self):
        entries = [
            {'target_display_index': 24, 'nits': 300, 'primary_index': 0},
            {'target_display_index': 24, 'nits': 300, 'primary_index': 2},
        ]
        out = {}
        service._flatten_l10('sidedata.rpu.l10', entries, 'sidedata.rpu.l10.indexes', out)

        self.assertEqual(out['sidedata.rpu.l10.24.primary_index'], '0')
        self.assertEqual(out['sidedata.rpu.l10.24-2.primary_index'], '2')
        self.assertEqual(out['sidedata.rpu.l10.indexes'], '24 24-2')

    def test_distribution_duplicate_percentage_get_ordinal_suffix(self):
        entries = [
            {'percentage': 50, 'nits': 200.0},
            {'percentage': 50, 'nits': 210.0},
        ]
        out = {}
        service._flatten_distribution('sidedata.hdr10plus.distribution', entries, out)

        self.assertEqual(out['sidedata.hdr10plus.distribution.50'], '200')
        self.assertEqual(out['sidedata.hdr10plus.distribution.50-2'], '210')
        self.assertEqual(out['sidedata.hdr10plus.distribution.percentages'], '50 50-2')


class TestFlattenCounts(unittest.TestCase):
    def test_l2_count(self):
        flat = service.flatten_sidedata(_sample_parsed())
        self.assertEqual(flat['sidedata.rpu.l2.count'], '2')

    def test_l8_count(self):
        flat = service.flatten_sidedata(_sample_parsed())
        self.assertEqual(flat['sidedata.rpu.l8.count'], '1')

    def test_l10_count(self):
        flat = service.flatten_sidedata(_sample_parsed())
        self.assertEqual(flat['sidedata.rpu.l10.count'], '1')

    def test_hdr10plus_distribution_count(self):
        flat = service.flatten_sidedata(_sample_parsed())
        self.assertEqual(flat['sidedata.hdr10plus.distribution.count'], '3')

    def test_counts_absent_on_empty_lists(self):
        parsed = _sample_parsed()
        parsed['rpu']['l2'] = []
        parsed['rpu']['l8'] = []
        parsed['rpu']['l10'] = []
        parsed['hdr10plus']['distribution'] = []
        flat = service.flatten_sidedata(parsed)

        self.assertNotIn('sidedata.rpu.l2.count', flat)
        self.assertNotIn('sidedata.rpu.l8.count', flat)
        self.assertNotIn('sidedata.rpu.l10.count', flat)
        self.assertNotIn('sidedata.hdr10plus.distribution.count', flat)


class TestFlattenPresence(unittest.TestCase):
    def test_present_flags_on_full_sample(self):
        flat = service.flatten_sidedata(_sample_parsed())
        self.assertEqual(flat['sidedata.present'], 'true')
        self.assertEqual(flat['sidedata.dovi.present'], 'true')
        self.assertEqual(flat['sidedata.hdr10plus.present'], 'true')
        self.assertEqual(flat['sidedata.mdcv.present'], 'true')
        self.assertEqual(flat['sidedata.cll.present'], 'true')

    def test_nothing_published_on_all_none_shape(self):
        flat = service.flatten_sidedata(_empty_parsed())
        self.assertEqual(flat, {})
        self.assertNotIn('sidedata.present', flat)

    def test_dovi_present_true_from_config_alone(self):
        parsed = _empty_parsed()
        parsed['config'] = {'profile': 7}
        flat = service.flatten_sidedata(parsed)
        self.assertEqual(flat['sidedata.dovi.present'], 'true')
        self.assertEqual(flat['sidedata.present'], 'true')

    def test_dovi_present_true_from_rpu_alone(self):
        parsed = _empty_parsed()
        parsed['rpu'] = _sample_parsed()['rpu']
        flat = service.flatten_sidedata(parsed)
        self.assertEqual(flat['sidedata.dovi.present'], 'true')

    def test_dovi_present_absent_when_both_none(self):
        flat = service.flatten_sidedata(_empty_parsed())
        self.assertNotIn('sidedata.dovi.present', flat)

    def test_presence_never_publishes_false(self):
        parsed = _empty_parsed()
        parsed['config'] = {'profile': 7}
        flat = service.flatten_sidedata(parsed)
        self.assertTrue(flat)
        self.assertNotIn('false', flat.values())
        self.assertNotIn('sidedata.hdr10plus.present', flat)
        self.assertNotIn('sidedata.mdcv.present', flat)
        self.assertNotIn('sidedata.cll.present', flat)


class TestFlattenTrimAliases(unittest.TestCase):
    def setUp(self):
        self.flat = service.flatten_sidedata(_sample_parsed())

    def test_l2_first_is_lowest_nits_entry(self):
        self.assertEqual(self.flat['sidedata.rpu.l2.first.nits'], '100')
        self.assertEqual(self.flat['sidedata.rpu.l2.first.slope'], '2048')

    def test_l2_last_is_highest_nits_entry(self):
        self.assertEqual(self.flat['sidedata.rpu.l2.last.nits'], '600')
        self.assertEqual(self.flat['sidedata.rpu.l2.last.slope'], '2100')

    def test_l8_first_equals_last_for_single_entry(self):
        first_keys = {k: v for k, v in self.flat.items() if k.startswith('sidedata.rpu.l8.first.')}
        last_keys = {k.replace('.first.', '.last.'): v for k, v in first_keys.items()}
        expected_last = {k: v for k, v in self.flat.items() if k.startswith('sidedata.rpu.l8.last.')}
        self.assertEqual(last_keys, expected_last)
        self.assertEqual(self.flat['sidedata.rpu.l8.first.nits'], '300')
        self.assertEqual(self.flat['sidedata.rpu.l8.last.nits'], '300')

    def test_l10_has_no_first_last_alias(self):
        for key in self.flat:
            self.assertFalse(key.startswith('sidedata.rpu.l10.first'))
            self.assertFalse(key.startswith('sidedata.rpu.l10.last'))


class TestTrimAliasPublishCycle(unittest.TestCase):
    def test_l2_aliases_update_through_diff_publish_cycle(self):
        window = _FakeWindow(10000)
        published = {}

        flat1 = service.flatten_sidedata(_sample_parsed())
        service._publish(window, published, flat1)
        self.assertEqual(window.properties['sidedata.rpu.l2.first.nits'], '100')
        self.assertEqual(window.properties['sidedata.rpu.l2.last.nits'], '600')

        parsed2 = _sample_parsed()
        parsed2['rpu']['l2'] = [
            {'nits': 200, 'slope': 1800, 'offset': 2048, 'power': 2048,
             'chromaweight': 2048, 'saturation': 2048, 'tonedetail': None,
             'ui': {'gain': 0.0, 'lift': 0.0, 'gamma': 0.0, 'chromaweight': 0.0,
                    'saturation': 0.0, 'tonedetail': None}},
        ]
        flat2 = service.flatten_sidedata(parsed2)
        service._publish(window, published, flat2)

        self.assertEqual(window.properties['sidedata.rpu.l2.first.nits'], '200')
        self.assertEqual(window.properties['sidedata.rpu.l2.last.nits'], '200')
        self.assertEqual(window.properties['sidedata.rpu.l2.first.slope'], '1800')
        self.assertEqual(window.properties['sidedata.rpu.l2.count'], '1')
        self.assertNotIn('sidedata.rpu.l2.600.slope', window.properties)
        self.assertNotIn('sidedata.rpu.l2.600.slope', published)


class TestPublishAndClear(unittest.TestCase):
    def setUp(self):
        self.window = _FakeWindow(10000)

    def test_initial_publish_sets_all(self):
        published = {}
        flat = {'sidedata.rpu.profile': '7', 'sidedata.structure': 'st-dl'}
        service._publish(self.window, published, flat)
        self.assertEqual(self.window.properties, flat)
        self.assertEqual(published, flat)

    def test_changed_dict_only_touches_deltas(self):
        published = {'sidedata.rpu.profile': '7', 'sidedata.structure': 'st-dl'}
        self.window.properties = dict(published)

        flat = {'sidedata.rpu.profile': '8', 'sidedata.structure': 'st-dl'}
        service._publish(self.window, published, flat)

        self.assertEqual(self.window.properties['sidedata.rpu.profile'], '8')
        self.assertEqual(self.window.properties['sidedata.structure'], 'st-dl')

    def test_removed_key_is_cleared(self):
        published = {'sidedata.rpu.profile': '7', 'sidedata.structure': 'st-dl'}
        self.window.properties = dict(published)

        flat = {'sidedata.rpu.profile': '7'}
        service._publish(self.window, published, flat)

        self.assertNotIn('sidedata.structure', self.window.properties)
        self.assertNotIn('sidedata.structure', published)

    def test_clear_removes_everything_and_resets_state(self):
        published = {'sidedata.rpu.profile': '7', 'sidedata.structure': 'st-dl'}
        self.window.properties = dict(published)

        service._clear(self.window, published)

        self.assertEqual(self.window.properties, {})
        self.assertEqual(published, {})

    def test_setproperty_failure_leaves_published_matching_reality(self):
        published = {}
        flat = {'a': '1', 'b': '2', 'c': '3'}
        self.window.fail_set_keys = {'b'}

        with self.assertRaises(RuntimeError):
            service._publish(self.window, published, flat)

        # 'a' was written before 'b' raised; 'c' was never attempted
        self.assertEqual(published, {'a': '1'})
        self.assertEqual(self.window.properties, {'a': '1'})

        # a later cleanup call still clears exactly what's really published
        self.window.fail_set_keys = set()
        service._clear(self.window, published)
        self.assertEqual(self.window.properties, {})
        self.assertEqual(published, {})

    def test_clearproperty_failure_is_best_effort_and_continues(self):
        published = {'a': '1', 'b': '2'}
        self.window.properties = dict(published)
        self.window.fail_clear_keys = {'a'}

        service._clear(self.window, published)

        # 'a' failed to clear so it's still tracked as published (matching
        # that it's still really on the window); 'b' cleared normally
        self.assertEqual(published, {'a': '1'})
        self.assertEqual(self.window.properties, {'a': '1'})


class TestTick(unittest.TestCase):
    def setUp(self):
        self.window = _FakeWindow(10000)
        self.player = _FakePlayer(playing=False)
        self.state = {'label': None, 'published': {}}
        _fake_xbmc.info_label = ''
        _fake_xbmc.log_calls = []

    def test_no_video_playing_leaves_properties_untouched(self):
        service._tick(self.player, self.window, self.state)
        self.assertEqual(self.window.properties, {})

    def test_empty_label_clears_published_properties(self):
        self.state['published'] = {'sidedata.structure': 'st-dl'}
        self.window.properties = {'sidedata.structure': 'st-dl'}
        self.player.playing = True
        _fake_xbmc.info_label = ''

        service._tick(self.player, self.window, self.state)

        self.assertEqual(self.window.properties, {})
        self.assertEqual(self.state['published'], {})

    def test_unchanged_label_does_nothing(self):
        self.player.playing = True
        _fake_xbmc.info_label = '{"structure": "st-dl"}'

        service._tick(self.player, self.window, self.state)
        first_properties = dict(self.window.properties)

        service._tick(self.player, self.window, self.state)

        self.assertEqual(self.window.properties, first_properties)

    def test_new_label_publishes_parsed_fields(self):
        self.player.playing = True
        _fake_xbmc.info_label = '{"structure": "st-dl", "flags": ["converted"]}'

        service._tick(self.player, self.window, self.state)

        self.assertEqual(self.window.properties['sidedata.structure'], 'st-dl')
        self.assertEqual(self.window.properties['sidedata.flags'], 'converted')

    def test_parse_sidedata_called_with_include_mapping_false(self):
        # the service never publishes rpu.data_mapping as a window property,
        # so it must opt out of the cost of building it in the first place
        self.player.playing = True
        _fake_xbmc.info_label = '{"structure": "st-dl"}'

        with mock.patch.object(service.sidedata, 'parse_sidedata',
                                wraps=service.sidedata.parse_sidedata) as mock_parse:
            service._tick(self.player, self.window, self.state)

        mock_parse.assert_called_once_with('{"structure": "st-dl"}', include_mapping=False)

    def test_malformed_label_never_raises_and_clears(self):
        self.state['published'] = {'sidedata.structure': 'st-dl'}
        self.window.properties = {'sidedata.structure': 'st-dl'}
        self.player.playing = True
        _fake_xbmc.info_label = 'not valid json'

        try:
            service._tick(self.player, self.window, self.state)
        except Exception as exc:  # noqa: BLE001
            self.fail('_tick raised: %r' % exc)

        # parse_sidedata degrades malformed json to the empty shape rather
        # than raising, so this exercises the normal empty-result publish
        # path, not the except branch
        self.assertNotIn('sidedata.structure', self.window.properties)

    def test_publish_failure_exercises_except_branch(self):
        # forces a real exception out of _publish (not out of parse_sidedata,
        # which never raises) so this actually drives _tick's except branch,
        # unlike test_malformed_label_never_raises_and_clears above
        self.player.playing = True
        _fake_xbmc.info_label = '{"structure": "st-dl"}'
        self.window.fail_set_keys = {'sidedata.structure'}

        with self.assertRaises(RuntimeError):
            service._tick(self.player, self.window, self.state)

        # the except branch's own cleanup ran: nothing was left published,
        # and the label was reset so the next tick reprocesses instead of
        # treating this as an unchanged label
        self.assertEqual(self.state['published'], {})
        self.assertEqual(self.window.properties, {})
        self.assertIsNone(self.state['label'])

        # recovery: a subsequent tick with a working window succeeds
        self.window.fail_set_keys = set()
        service._tick(self.player, self.window, self.state)
        self.assertEqual(self.window.properties['sidedata.structure'], 'st-dl')


class TestPollInterval(unittest.TestCase):
    def test_poll_interval_is_one_tenth_of_a_second(self):
        self.assertEqual(service._POLL_INTERVAL, 0.1)


class _AbortingMonitor(object):
    """aborts once waitForAbort has been called `abort_after` times, so a
    run() test can exercise a bounded number of loop iterations."""

    def __init__(self, abort_after=3):
        self.abort_after = abort_after
        self.calls = 0

    def abortRequested(self):
        return self.calls >= self.abort_after

    def waitForAbort(self, timeout):
        self.calls += 1
        return self.calls >= self.abort_after


class _AlwaysFailingPlayer(object):
    def isPlayingVideo(self):
        raise RuntimeError('boom')


class TestRunLogging(unittest.TestCase):
    def test_run_logs_failure_once_across_repeated_ticks(self):
        _fake_xbmc.log_calls = []
        window = _FakeWindow(10000)

        with mock.patch.object(_fake_xbmc, 'Monitor', lambda: _AbortingMonitor(3)), \
                mock.patch.object(_fake_xbmc, 'Player', _AlwaysFailingPlayer), \
                mock.patch.object(_fake_xbmcgui, 'Window', lambda window_id: window):
            service.run()

        warnings = [call for call in _fake_xbmc.log_calls if call[1] == _fake_xbmc.LOGWARNING]
        self.assertEqual(len(warnings), 1)


if __name__ == '__main__':
    unittest.main()
