# ctypes binding to CoreELEC's own libavutil (FFmpeg), used for HDR10+
# (ST 2094-40) T.35 parsing via av_dynamic_hdr_plus_from_t35. Struct layouts
# mirror libavutil/hdr_dynamic_metadata.h field-for-field, pinned to the
# header shared unchanged by ffmpeg 8.1.2 and 9.0 (libavutil 60 and 61,
# CoreELEC 22's ffmpeg builds so far), since av_dynamic_hdr_plus_from_t35
# fills a plain stack struct, not an opaque allocation, so a layout slip
# here is silent stack corruption, not a crash. Never bundled: the CE
# image's own libavutil.so is loaded at runtime, same as any other Kodi
# codec lib.
#
# Field extraction (which struct fields feed which output keys, the 6-byte
# T.35 header, the num_windows >= 1 gate) follows ffmpeg's AVDynamicHDRPlus
# semantics. Only window 0 is exposed; real content is essentially always
# num_windows == 1.
#
# The loader tries, in order: SIDEDATA_LIBAVUTIL_PATH, 'libavutil.so.61',
# 'libavutil.so.60', then ctypes.util.find_library('avutil'). A loaded
# library is only kept if avutil_version()'s major matches one of
# _LIBAVUTIL_VERSION_MAJORS below. The struct layout above is pinned to
# that ABI, so a mismatched major is treated as unavailable rather than
# risking silent corruption.
#
# available() never raises. parse_t35() returns None on any failure,
# whether a missing library, a version mismatch, a bad payload, or
# anything else.

import ctypes
import ctypes.util
import os

from .convert import hdr10plus_fraction_bright_percent, hdr10plus_knee_point, hdr10plus_rgb_nits

__all__ = ['available', 'parse_t35']

_LIBAVUTIL_VERSION_MAJORS = (61, 60)

_SIGNATURE = bytes((0xB5, 0x00, 0x3C, 0x00, 0x01, 0x04))
_NUM_WINDOWS = 3
_MAX_PERCENTILES = 15
_MAX_BEZIER_ANCHORS = 15
_PEAK_LUM_DIM = 25


class _AVRational(ctypes.Structure):
    _fields_ = [
        ('num', ctypes.c_int),
        ('den', ctypes.c_int),
    ]


class _AVHDRPlusPercentile(ctypes.Structure):
    _fields_ = [
        ('percentage', ctypes.c_uint8),
        ('percentile', _AVRational),
    ]


class _AVHDRPlusColorTransformParams(ctypes.Structure):
    _fields_ = [
        ('window_upper_left_corner_x', _AVRational),
        ('window_upper_left_corner_y', _AVRational),
        ('window_lower_right_corner_x', _AVRational),
        ('window_lower_right_corner_y', _AVRational),
        ('center_of_ellipse_x', ctypes.c_uint16),
        ('center_of_ellipse_y', ctypes.c_uint16),
        ('rotation_angle', ctypes.c_uint8),
        ('semimajor_axis_internal_ellipse', ctypes.c_uint16),
        ('semimajor_axis_external_ellipse', ctypes.c_uint16),
        ('semiminor_axis_external_ellipse', ctypes.c_uint16),
        ('overlap_process_option', ctypes.c_int),
        ('maxscl', _AVRational * 3),
        ('average_maxrgb', _AVRational),
        ('num_distribution_maxrgb_percentiles', ctypes.c_uint8),
        ('distribution_maxrgb', _AVHDRPlusPercentile * _MAX_PERCENTILES),
        ('fraction_bright_pixels', _AVRational),
        ('tone_mapping_flag', ctypes.c_uint8),
        ('knee_point_x', _AVRational),
        ('knee_point_y', _AVRational),
        ('num_bezier_curve_anchors', ctypes.c_uint8),
        ('bezier_curve_anchors', _AVRational * _MAX_BEZIER_ANCHORS),
        ('color_saturation_mapping_flag', ctypes.c_uint8),
        ('color_saturation_weight', _AVRational),
    ]


class _AVDynamicHDRPlus(ctypes.Structure):
    _fields_ = [
        ('itu_t_t35_country_code', ctypes.c_uint8),
        ('application_version', ctypes.c_uint8),
        ('num_windows', ctypes.c_uint8),
        ('params', _AVHDRPlusColorTransformParams * _NUM_WINDOWS),
        ('targeted_system_display_maximum_luminance', _AVRational),
        ('targeted_system_display_actual_peak_luminance_flag', ctypes.c_uint8),
        ('num_rows_targeted_system_display_actual_peak_luminance', ctypes.c_uint8),
        ('num_cols_targeted_system_display_actual_peak_luminance', ctypes.c_uint8),
        ('targeted_system_display_actual_peak_luminance',
         (_AVRational * _PEAK_LUM_DIM) * _PEAK_LUM_DIM),
        ('mastering_display_actual_peak_luminance_flag', ctypes.c_uint8),
        ('num_rows_mastering_display_actual_peak_luminance', ctypes.c_uint8),
        ('num_cols_mastering_display_actual_peak_luminance', ctypes.c_uint8),
        ('mastering_display_actual_peak_luminance',
         (_AVRational * _PEAK_LUM_DIM) * _PEAK_LUM_DIM),
    ]


def _configure(lib):
    lib.avutil_version.argtypes = []
    lib.avutil_version.restype = ctypes.c_uint
    lib.av_dynamic_hdr_plus_from_t35.argtypes = [
        ctypes.POINTER(_AVDynamicHDRPlus), ctypes.c_char_p, ctypes.c_size_t]
    lib.av_dynamic_hdr_plus_from_t35.restype = ctypes.c_int


_lib = None
_load_attempted = False


def _load():
    global _lib, _load_attempted
    if _load_attempted:
        return _lib
    _load_attempted = True

    candidates = []
    override = os.environ.get('SIDEDATA_LIBAVUTIL_PATH')
    if override:
        candidates.append(override)
    candidates.append('libavutil.so.61')
    candidates.append('libavutil.so.60')
    found = ctypes.util.find_library('avutil')
    if found:
        candidates.append(found)

    for name in candidates:
        try:
            lib = ctypes.CDLL(name)
            _configure(lib)
            major = lib.avutil_version() >> 16
        except (OSError, AttributeError):
            continue
        if major not in _LIBAVUTIL_VERSION_MAJORS:
            continue
        _lib = lib
        break
    return _lib


def available():
    return _load() is not None


def parse_t35(data):
    lib = _load()
    if lib is None:
        return None
    try:
        data = bytes(data)
        if len(data) < 8 or data[:6] != _SIGNATURE:
            return None

        hdr = _AVDynamicHDRPlus()
        ret = lib.av_dynamic_hdr_plus_from_t35(ctypes.byref(hdr), data[6:], len(data) - 6)
        if ret < 0 or hdr.num_windows < 1:
            return None

        window = hdr.params[0]
        distribution = [
            {
                'percentage': window.distribution_maxrgb[i].percentage,
                'nits': hdr10plus_rgb_nits(window.distribution_maxrgb[i].percentile.num),
            }
            for i in range(window.num_distribution_maxrgb_percentiles)
        ]
        bezier_anchors = [window.bezier_curve_anchors[i].num
                           for i in range(window.num_bezier_curve_anchors)]

        return {
            'application_version': hdr.application_version,
            'num_windows': hdr.num_windows,
            'targeted_system_display_maximum_luminance':
                hdr.targeted_system_display_maximum_luminance.num,
            'maxscl': [hdr10plus_rgb_nits(window.maxscl[i].num) for i in range(3)],
            'average_maxrgb': hdr10plus_rgb_nits(window.average_maxrgb.num),
            'distribution': distribution,
            'fraction_bright_pixels':
                hdr10plus_fraction_bright_percent(window.fraction_bright_pixels.num),
            'profile': 'B' if window.tone_mapping_flag else 'A',
            'knee_point_x': hdr10plus_knee_point(window.knee_point_x.num),
            'knee_point_y': hdr10plus_knee_point(window.knee_point_y.num),
            'bezier_anchors': bezier_anchors,
        }
    except Exception:
        return None
