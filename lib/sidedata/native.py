# ctypes bindings to the platform libdovi (quietvoid/dovi_tool), the sole
# RPU parsing engine; see rpu.py, which just dispatches here. Struct
# layouts mirror libdovi-3.3.1's rpu_parser.h field-for-field (see
# README.md); a layout slip here is silent corruption, not a crash.
#
# native_parse_hevc_nal62(nal) / native_parse_av1_t35(payload) take the
# escaped-NAL / T.35-from-country-code shapes unwrapped (both libdovi entry
# points accept these directly, per dovi_rpu.rs validated_trimmed_data/
# av1_validated_trimmed_data) and return the resolved result dict, or None.
#
# The loader tries four candidates in order: SIDEDATA_LIBDOVI_PATH, this
# addon's own bundled build for the running platform.machine()
# (native_libs/<arch>/libdovi.so, resolved relative to this file's own path
# so it works regardless of Kodi's cwd), a bare libdovi.so soname left to
# the dynamic linker, then whatever find_library('dovi') resolves, which is
# the versioned soname a bare dlopen misses. No bundled dir for the current
# arch just falls through to the last two.
#
# available() never raises regardless of what's installed. Both parse
# functions return None on any failure, whether a missing library, a bad
# payload, or anything else; that is never raised to the caller. That
# guarantee is this Python layer only: libdovi itself can panic and abort
# the process on malformed input, uncatchable from here. See README.md's
# Known limitations.

import ctypes
import ctypes.util
import os
import platform

from .convert import (
    content_type_name,
    pq_to_nits,
    primaries_name,
    snap_target_nits,
    target_index_nits,
    trim_ui_values,
    whitepoint_kelvin,
    whitepoint_name,
)

__all__ = ['available', 'last_error', 'native_parse_hevc_nal62', 'native_parse_av1_t35']


class _DoviRpuDataHeader(ctypes.Structure):
    _fields_ = [
        ('guessed_profile', ctypes.c_uint8),
        ('el_type', ctypes.c_char_p),
        ('rpu_nal_prefix', ctypes.c_uint8),
        ('rpu_type', ctypes.c_uint8),
        ('rpu_format', ctypes.c_uint16),
        ('vdr_rpu_profile', ctypes.c_uint8),
        ('vdr_rpu_level', ctypes.c_uint8),
        ('vdr_seq_info_present_flag', ctypes.c_bool),
        ('chroma_resampling_explicit_filter_flag', ctypes.c_bool),
        ('coefficient_data_type', ctypes.c_uint8),
        ('coefficient_log2_denom', ctypes.c_uint64),
        ('vdr_rpu_normalized_idc', ctypes.c_uint8),
        ('bl_video_full_range_flag', ctypes.c_bool),
        ('bl_bit_depth_minus8', ctypes.c_uint64),
        ('el_bit_depth_minus8', ctypes.c_uint64),
        ('vdr_bit_depth_minus8', ctypes.c_uint64),
        ('spatial_resampling_filter_flag', ctypes.c_bool),
        ('reserved_zero_3bits', ctypes.c_uint8),
        ('el_spatial_resampling_filter_flag', ctypes.c_bool),
        ('disable_residual_flag', ctypes.c_bool),
        ('vdr_dm_metadata_present_flag', ctypes.c_bool),
        ('use_prev_vdr_rpu_flag', ctypes.c_bool),
        ('prev_vdr_rpu_id', ctypes.c_uint64),
    ]


class _DoviExtMetadataBlockLevel1(ctypes.Structure):
    _fields_ = [
        ('min_pq', ctypes.c_uint16),
        ('max_pq', ctypes.c_uint16),
        ('avg_pq', ctypes.c_uint16),
    ]


class _DoviExtMetadataBlockLevel2(ctypes.Structure):
    _fields_ = [
        ('target_max_pq', ctypes.c_uint16),
        ('trim_slope', ctypes.c_uint16),
        ('trim_offset', ctypes.c_uint16),
        ('trim_power', ctypes.c_uint16),
        ('trim_chroma_weight', ctypes.c_uint16),
        ('trim_saturation_gain', ctypes.c_uint16),
        ('ms_weight', ctypes.c_int16),
    ]


class _DoviLevel2BlockList(ctypes.Structure):
    _fields_ = [
        ('list', ctypes.POINTER(ctypes.POINTER(_DoviExtMetadataBlockLevel2))),
        ('len', ctypes.c_size_t),
    ]


class _DoviExtMetadataBlockLevel3(ctypes.Structure):
    _fields_ = [
        ('min_pq_offset', ctypes.c_uint16),
        ('max_pq_offset', ctypes.c_uint16),
        ('avg_pq_offset', ctypes.c_uint16),
    ]


class _DoviExtMetadataBlockLevel5(ctypes.Structure):
    _fields_ = [
        ('active_area_left_offset', ctypes.c_uint16),
        ('active_area_right_offset', ctypes.c_uint16),
        ('active_area_top_offset', ctypes.c_uint16),
        ('active_area_bottom_offset', ctypes.c_uint16),
    ]


class _DoviExtMetadataBlockLevel6(ctypes.Structure):
    _fields_ = [
        ('max_display_mastering_luminance', ctypes.c_uint16),
        ('min_display_mastering_luminance', ctypes.c_uint16),
        ('max_content_light_level', ctypes.c_uint16),
        ('max_frame_average_light_level', ctypes.c_uint16),
    ]


class _DoviExtMetadataBlockLevel8(ctypes.Structure):
    _fields_ = [
        ('length', ctypes.c_uint64),
        ('target_display_index', ctypes.c_uint8),
        ('trim_slope', ctypes.c_uint16),
        ('trim_offset', ctypes.c_uint16),
        ('trim_power', ctypes.c_uint16),
        ('trim_chroma_weight', ctypes.c_uint16),
        ('trim_saturation_gain', ctypes.c_uint16),
        ('ms_weight', ctypes.c_uint16),
        ('target_mid_contrast', ctypes.c_uint16),
        ('clip_trim', ctypes.c_uint16),
        ('saturation_vector_field0', ctypes.c_uint8),
        ('saturation_vector_field1', ctypes.c_uint8),
        ('saturation_vector_field2', ctypes.c_uint8),
        ('saturation_vector_field3', ctypes.c_uint8),
        ('saturation_vector_field4', ctypes.c_uint8),
        ('saturation_vector_field5', ctypes.c_uint8),
        ('hue_vector_field0', ctypes.c_uint8),
        ('hue_vector_field1', ctypes.c_uint8),
        ('hue_vector_field2', ctypes.c_uint8),
        ('hue_vector_field3', ctypes.c_uint8),
        ('hue_vector_field4', ctypes.c_uint8),
        ('hue_vector_field5', ctypes.c_uint8),
    ]


class _DoviLevel8BlockList(ctypes.Structure):
    _fields_ = [
        ('list', ctypes.POINTER(ctypes.POINTER(_DoviExtMetadataBlockLevel8))),
        ('len', ctypes.c_size_t),
    ]


class _DoviExtMetadataBlockLevel9(ctypes.Structure):
    _fields_ = [
        ('length', ctypes.c_uint64),
        ('source_primary_index', ctypes.c_uint8),
        ('source_primary_red_x', ctypes.c_uint16),
        ('source_primary_red_y', ctypes.c_uint16),
        ('source_primary_green_x', ctypes.c_uint16),
        ('source_primary_green_y', ctypes.c_uint16),
        ('source_primary_blue_x', ctypes.c_uint16),
        ('source_primary_blue_y', ctypes.c_uint16),
        ('source_primary_white_x', ctypes.c_uint16),
        ('source_primary_white_y', ctypes.c_uint16),
    ]


class _DoviExtMetadataBlockLevel10(ctypes.Structure):
    _fields_ = [
        ('length', ctypes.c_uint64),
        ('target_display_index', ctypes.c_uint8),
        ('target_max_pq', ctypes.c_uint16),
        ('target_min_pq', ctypes.c_uint16),
        ('target_primary_index', ctypes.c_uint8),
        ('target_primary_red_x', ctypes.c_uint16),
        ('target_primary_red_y', ctypes.c_uint16),
        ('target_primary_green_x', ctypes.c_uint16),
        ('target_primary_green_y', ctypes.c_uint16),
        ('target_primary_blue_x', ctypes.c_uint16),
        ('target_primary_blue_y', ctypes.c_uint16),
        ('target_primary_white_x', ctypes.c_uint16),
        ('target_primary_white_y', ctypes.c_uint16),
    ]


class _DoviLevel10BlockList(ctypes.Structure):
    _fields_ = [
        ('list', ctypes.POINTER(ctypes.POINTER(_DoviExtMetadataBlockLevel10))),
        ('len', ctypes.c_size_t),
    ]


class _DoviExtMetadataBlockLevel11(ctypes.Structure):
    _fields_ = [
        ('content_type', ctypes.c_uint8),
        ('whitepoint', ctypes.c_uint8),
        ('reference_mode_flag', ctypes.c_bool),
        ('reserved_byte2', ctypes.c_uint8),
        ('reserved_byte3', ctypes.c_uint8),
    ]


class _DoviExtMetadataBlockLevel254(ctypes.Structure):
    _fields_ = [
        ('dm_mode', ctypes.c_uint8),
        ('dm_version_index', ctypes.c_uint8),
    ]


# level4 (anamorphic) and level255 (debug run modes) are declared as opaque
# pointers: this addon never reads them, and a void* is layout-identical to
# a typed pointer for struct purposes
class _DoviDmData(ctypes.Structure):
    _fields_ = [
        ('num_ext_blocks', ctypes.c_uint64),
        ('level1', ctypes.POINTER(_DoviExtMetadataBlockLevel1)),
        ('level2', _DoviLevel2BlockList),
        ('level3', ctypes.POINTER(_DoviExtMetadataBlockLevel3)),
        ('level4', ctypes.c_void_p),
        ('level5', ctypes.POINTER(_DoviExtMetadataBlockLevel5)),
        ('level6', ctypes.POINTER(_DoviExtMetadataBlockLevel6)),
        ('level8', _DoviLevel8BlockList),
        ('level9', ctypes.POINTER(_DoviExtMetadataBlockLevel9)),
        ('level10', _DoviLevel10BlockList),
        ('level11', ctypes.POINTER(_DoviExtMetadataBlockLevel11)),
        ('level254', ctypes.POINTER(_DoviExtMetadataBlockLevel254)),
        ('level255', ctypes.c_void_p),
    ]


class _DoviVdrDmData(ctypes.Structure):
    _fields_ = [
        ('compressed', ctypes.c_bool),
        ('affected_dm_metadata_id', ctypes.c_uint64),
        ('current_dm_metadata_id', ctypes.c_uint64),
        ('scene_refresh_flag', ctypes.c_uint64),
        ('ycc_to_rgb_coef0', ctypes.c_int16),
        ('ycc_to_rgb_coef1', ctypes.c_int16),
        ('ycc_to_rgb_coef2', ctypes.c_int16),
        ('ycc_to_rgb_coef3', ctypes.c_int16),
        ('ycc_to_rgb_coef4', ctypes.c_int16),
        ('ycc_to_rgb_coef5', ctypes.c_int16),
        ('ycc_to_rgb_coef6', ctypes.c_int16),
        ('ycc_to_rgb_coef7', ctypes.c_int16),
        ('ycc_to_rgb_coef8', ctypes.c_int16),
        ('ycc_to_rgb_offset0', ctypes.c_uint32),
        ('ycc_to_rgb_offset1', ctypes.c_uint32),
        ('ycc_to_rgb_offset2', ctypes.c_uint32),
        ('rgb_to_lms_coef0', ctypes.c_int16),
        ('rgb_to_lms_coef1', ctypes.c_int16),
        ('rgb_to_lms_coef2', ctypes.c_int16),
        ('rgb_to_lms_coef3', ctypes.c_int16),
        ('rgb_to_lms_coef4', ctypes.c_int16),
        ('rgb_to_lms_coef5', ctypes.c_int16),
        ('rgb_to_lms_coef6', ctypes.c_int16),
        ('rgb_to_lms_coef7', ctypes.c_int16),
        ('rgb_to_lms_coef8', ctypes.c_int16),
        ('signal_eotf', ctypes.c_uint16),
        ('signal_eotf_param0', ctypes.c_uint16),
        ('signal_eotf_param1', ctypes.c_uint16),
        ('signal_eotf_param2', ctypes.c_uint32),
        ('signal_bit_depth', ctypes.c_uint8),
        ('signal_color_space', ctypes.c_uint8),
        ('signal_chroma_format', ctypes.c_uint8),
        ('signal_full_range_flag', ctypes.c_uint8),
        ('source_min_pq', ctypes.c_uint16),
        ('source_max_pq', ctypes.c_uint16),
        ('source_diagonal', ctypes.c_uint16),
        ('dm_data', _DoviDmData),
    ]


def _configure(lib):
    lib.dovi_parse_unspec62_nalu.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.dovi_parse_unspec62_nalu.restype = ctypes.c_void_p
    lib.dovi_parse_itu_t35_dovi_metadata_obu.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.dovi_parse_itu_t35_dovi_metadata_obu.restype = ctypes.c_void_p
    lib.dovi_rpu_free.argtypes = [ctypes.c_void_p]
    lib.dovi_rpu_free.restype = None
    lib.dovi_rpu_get_error.argtypes = [ctypes.c_void_p]
    lib.dovi_rpu_get_error.restype = ctypes.c_char_p
    lib.dovi_rpu_get_header.argtypes = [ctypes.c_void_p]
    lib.dovi_rpu_get_header.restype = ctypes.POINTER(_DoviRpuDataHeader)
    lib.dovi_rpu_free_header.argtypes = [ctypes.POINTER(_DoviRpuDataHeader)]
    lib.dovi_rpu_free_header.restype = None
    lib.dovi_rpu_get_vdr_dm_data.argtypes = [ctypes.c_void_p]
    lib.dovi_rpu_get_vdr_dm_data.restype = ctypes.POINTER(_DoviVdrDmData)
    lib.dovi_rpu_free_vdr_dm_data.argtypes = [ctypes.POINTER(_DoviVdrDmData)]
    lib.dovi_rpu_free_vdr_dm_data.restype = None


_lib = None
_load_attempted = False
_last_error = None
_NATIVE_LIBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'native_libs')


def _bundled_lib_path():
    path = os.path.join(_NATIVE_LIBS_DIR, platform.machine(), 'libdovi.so')
    return path if os.path.isfile(path) else None


def _candidates():
    # yielded lazily: find_library shells out to ldconfig and friends, which a
    # minimal image may not carry, so it only runs once the rest have failed
    override = os.environ.get('SIDEDATA_LIBDOVI_PATH')
    if override:
        yield override
    bundled = _bundled_lib_path()
    if bundled:
        yield bundled
    yield 'libdovi.so'
    found = ctypes.util.find_library('dovi')
    if found:
        yield found


def _load():
    global _lib, _load_attempted
    if _load_attempted:
        return _lib
    _load_attempted = True

    for name in _candidates():
        try:
            lib = ctypes.CDLL(name)
            _configure(lib)
        except (OSError, AttributeError):
            continue
        _lib = lib
        break
    return _lib


def available():
    return _load() is not None


def last_error():
    # best-effort diagnostic only (dovi_rpu_get_error's text from the most
    # recent failed parse on any thread), never authoritative, since Kodi
    # calls into this module from more than one thread
    return _last_error


def _primaries_coords(red_x, red_y, green_x, green_y, blue_x, blue_y, white_x, white_y):
    return {
        'red': (red_x, red_y),
        'green': (green_x, green_y),
        'blue': (blue_x, blue_y),
        'white': (white_x, white_y),
    }


def _build_trim(nits, block, ms_weight, ms_can_disable, target_display_index=None):
    slope = block.trim_slope
    offset = block.trim_offset
    power = block.trim_power
    chroma_weight = block.trim_chroma_weight
    saturation_gain = block.trim_saturation_gain
    ms_disabled = ms_can_disable and ms_weight == -1

    trim = {
        'nits': nits,
        'slope': slope,
        'offset': offset,
        'power': power,
        'chromaweight': chroma_weight,
        'saturation': saturation_gain,
        'tonedetail': None if ms_disabled else ms_weight,
        'ui': trim_ui_values(slope, offset, power, chroma_weight, saturation_gain, ms_weight,
                              ms_disabled),
    }
    if target_display_index is not None:
        trim['target_display_index'] = target_display_index
    return trim


def _build_header(header):
    has_seq_info = bool(header.vdr_seq_info_present_flag)
    el_type = header.el_type.decode('ascii') if header.el_type else None

    return {
        'profile': header.guessed_profile,
        'header': {
            'rpu_type': header.rpu_type,
            'rpu_format': header.rpu_format,
            'vdr_rpu_profile': header.vdr_rpu_profile,
            'vdr_rpu_level': header.vdr_rpu_level,
            'bl_bit_depth': 8 + header.bl_bit_depth_minus8 if has_seq_info else None,
            'el_bit_depth': 8 + header.el_bit_depth_minus8 if has_seq_info else None,
            'vdr_bit_depth': 8 + header.vdr_bit_depth_minus8 if has_seq_info else None,
            'el_spatial_resampling_filter_flag': bool(header.el_spatial_resampling_filter_flag),
            'disable_residual_flag': bool(header.disable_residual_flag),
            'el_type': el_type,
        },
        'compressed': False,
        'cm_version': None,
        'source': None,
        'l1': None,
        'l2': [],
        'l3': None,
        'l5': None,
        'l6': None,
        'l8': [],
        'l9': None,
        'l10': [],
        'l11': None,
    }


def _apply_vdr(result, vdr):
    dm = vdr.dm_data
    result['compressed'] = bool(vdr.compressed)
    if not vdr.compressed:
        result['source'] = {
            'min_pq': vdr.source_min_pq,
            'min_nits': pq_to_nits(vdr.source_min_pq),
            'max_pq': vdr.source_max_pq,
            'max_nits': pq_to_nits(vdr.source_max_pq),
        }

    has_known_block = bool(dm.level1 or dm.level2.len or dm.level3 or dm.level5 or dm.level6 or
                            dm.level8.len or dm.level9 or dm.level10.len or dm.level11 or
                            dm.level254)
    result['cm_version'] = '4.0' if dm.level254 else ('2.9' if has_known_block else None)

    if dm.level1:
        b = dm.level1.contents
        result['l1'] = {
            'min_pq': b.min_pq, 'min_nits': pq_to_nits(b.min_pq),
            'max_pq': b.max_pq, 'max_nits': pq_to_nits(b.max_pq),
            'avg_pq': b.avg_pq, 'avg_nits': pq_to_nits(b.avg_pq),
        }

    if dm.level3:
        b = dm.level3.contents
        result['l3'] = {
            'min_pq_offset': b.min_pq_offset,
            'max_pq_offset': b.max_pq_offset,
            'avg_pq_offset': b.avg_pq_offset,
        }

    if dm.level5:
        b = dm.level5.contents
        result['l5'] = {
            'left': b.active_area_left_offset, 'right': b.active_area_right_offset,
            'top': b.active_area_top_offset, 'bottom': b.active_area_bottom_offset,
        }

    if dm.level6:
        b = dm.level6.contents
        result['l6'] = {
            'max_cll': b.max_content_light_level,
            'max_fall': b.max_frame_average_light_level,
            'min_lum_raw': b.min_display_mastering_luminance,
            'min_lum_nits': b.min_display_mastering_luminance * 0.0001,
            'max_lum_raw': b.max_display_mastering_luminance,
            'max_lum_nits': b.max_display_mastering_luminance,
        }

    if dm.level9:
        b = dm.level9.contents
        has_coords = b.length >= 17
        l9 = {
            'index': b.source_primary_index,
            'has_coords': has_coords,
            'name': primaries_name(b.source_primary_index, has_coords),
        }
        if has_coords:
            l9['coords'] = _primaries_coords(
                b.source_primary_red_x, b.source_primary_red_y,
                b.source_primary_green_x, b.source_primary_green_y,
                b.source_primary_blue_x, b.source_primary_blue_y,
                b.source_primary_white_x, b.source_primary_white_y)
        result['l9'] = l9

    if dm.level11:
        b = dm.level11.contents
        result['l11'] = {
            'content_type': b.content_type,
            'content_type_name': content_type_name(b.content_type),
            'whitepoint': b.whitepoint,
            'whitepoint_kelvin': whitepoint_kelvin(b.whitepoint),
            'whitepoint_name': whitepoint_name(b.whitepoint),
            'reference_mode': bool(b.reference_mode_flag),
        }

    l2_list = []
    for i in range(dm.level2.len):
        b = dm.level2.list[i].contents
        nits = snap_target_nits(pq_to_nits(b.target_max_pq))
        l2_list.append(_build_trim(nits, b, b.ms_weight, ms_can_disable=True))
    l2_list.sort(key=lambda t: t['nits'])
    result['l2'] = l2_list

    # L10 definitions resolve first for L8 targets since they may override a
    # preset index
    l10_index_to_nits = {}
    l10_list = []
    for i in range(dm.level10.len):
        b = dm.level10.list[i].contents
        nits = snap_target_nits(pq_to_nits(b.target_max_pq))
        if nits <= 0:
            continue
        has_coords = b.length >= 21
        entry = {
            'target_display_index': b.target_display_index,
            'nits': nits,
            'target_max_pq': b.target_max_pq,
            'target_min_pq': b.target_min_pq,
            'primary_index': b.target_primary_index,
            'primary_name': primaries_name(b.target_primary_index, has_coords),
            'has_coords': has_coords,
        }
        if has_coords:
            entry['coords'] = _primaries_coords(
                b.target_primary_red_x, b.target_primary_red_y,
                b.target_primary_green_x, b.target_primary_green_y,
                b.target_primary_blue_x, b.target_primary_blue_y,
                b.target_primary_white_x, b.target_primary_white_y)
        l10_list.append(entry)
        l10_index_to_nits[b.target_display_index] = nits
    l10_list.sort(key=lambda t: (t['nits'], t['primary_index']))
    result['l10'] = l10_list

    l8_list = []
    for i in range(dm.level8.len):
        b = dm.level8.list[i].contents
        idx = b.target_display_index
        nits = l10_index_to_nits.get(idx, 0) or target_index_nits(idx)
        if nits == 0:
            continue
        trim = _build_trim(nits, b, b.ms_weight, ms_can_disable=False, target_display_index=idx)
        if b.length > 10:
            trim['mid_contrast'] = b.target_mid_contrast
        if b.length > 12:
            trim['clip_trim'] = b.clip_trim
        l8_list.append(trim)
    l8_list.sort(key=lambda t: t['nits'])
    result['l8'] = l8_list


def _resolve(lib, rpu):
    global _last_error
    if not rpu:
        return None
    try:
        header_ptr = lib.dovi_rpu_get_header(rpu)
        if not header_ptr:
            error = lib.dovi_rpu_get_error(rpu)
            _last_error = error.decode('utf-8', 'replace') if error else None
            return None
        try:
            result = _build_header(header_ptr.contents)
            vdr_ptr = lib.dovi_rpu_get_vdr_dm_data(rpu)
            if vdr_ptr:
                try:
                    _apply_vdr(result, vdr_ptr.contents)
                finally:
                    lib.dovi_rpu_free_vdr_dm_data(vdr_ptr)
            _last_error = None
            return result
        finally:
            lib.dovi_rpu_free_header(header_ptr)
    finally:
        lib.dovi_rpu_free(rpu)


def native_parse_hevc_nal62(nal):
    lib = _load()
    if lib is None:
        return None
    try:
        data = bytes(nal)
        rpu = lib.dovi_parse_unspec62_nalu(data, len(data))
        return _resolve(lib, rpu)
    except Exception:
        return None


def native_parse_av1_t35(payload):
    lib = _load()
    if lib is None:
        return None
    try:
        data = bytes(payload)
        rpu = lib.dovi_parse_itu_t35_dovi_metadata_obu(data, len(data))
        return _resolve(lib, rpu)
    except Exception:
        return None
