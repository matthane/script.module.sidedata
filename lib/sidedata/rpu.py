# Dolby Vision RPU parser. Bit layout follows the parsing logic of dovi_tool /
# libdovi (quietvoid, MIT license, https://github.com/quietvoid/dovi_tool),
# and this parser's output is validated against dovi_tool's own JSON dump
# (see tests/test_rpu.py). Field resolution (nits snapping, L10-first target
# lookup, name tables) mirrors AMLFrameMetadata.h's AMLFillFromDoviRpu, the
# device-tested reference this addon's diagnostic counterpart reads from.

import struct

from ._bits import BitReader
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

_NUM_COMPONENTS = 3
_NLQ_NUM_PIVOTS = 2
_MMR_MAX_COEFFS = 7
_MULTI_LEVELS = (2, 8, 10)

_RPU_PREFIX = 25


def _clear_emulation_prevention(data):
    n = len(data)
    if n <= 2:
        return data
    out = bytearray(data[:2])
    for i in range(2, n):
        if data[i - 2] == 0 and data[i - 1] == 0 and data[i] == 3:
            continue
        out.append(data[i])
    return bytes(out)


def _parse_header(br):
    h = {
        'rpu_type': br.read_bits(6),
        'rpu_format': br.read_bits(11),
        'vdr_rpu_profile': br.read_bits(4),
        'vdr_rpu_level': br.read_bits(4),
    }
    h['vdr_seq_info_present_flag'] = bool(br.read_bit())

    h['bl_bit_depth_minus8'] = 0
    h['el_bit_depth_minus8'] = 0
    h['vdr_bit_depth_minus8'] = 0
    h['reserved_zero_3bits'] = 0
    h['el_spatial_resampling_filter_flag'] = False
    h['disable_residual_flag'] = False
    h['coefficient_data_type'] = 0
    h['coefficient_log2_denom_length'] = 0
    h['bl_video_full_range_flag'] = False

    if h['vdr_seq_info_present_flag']:
        br.read_bit()  # chroma_resampling_explicit_filter_flag
        h['coefficient_data_type'] = br.read_bits(2)
        coefficient_log2_denom = 0
        if h['coefficient_data_type'] == 0:
            coefficient_log2_denom = br.read_ue()

        br.read_bits(2)  # vdr_rpu_normalized_idc
        h['bl_video_full_range_flag'] = bool(br.read_bit())

        if h['rpu_format'] & 0x700 == 0:
            h['bl_bit_depth_minus8'] = br.read_ue()

            el_bit_depth_full = br.read_ue()
            h['el_bit_depth_minus8'] = el_bit_depth_full & 0xFF

            h['vdr_bit_depth_minus8'] = br.read_ue()
            br.read_bit()  # spatial_resampling_filter_flag
            h['reserved_zero_3bits'] = br.read_bits(3)
            h['el_spatial_resampling_filter_flag'] = bool(br.read_bit())
            h['disable_residual_flag'] = bool(br.read_bit())

        if h['coefficient_data_type'] == 0:
            h['coefficient_log2_denom_length'] = coefficient_log2_denom
        elif h['coefficient_data_type'] == 1:
            h['coefficient_log2_denom_length'] = 32
        else:
            raise ValueError('invalid coefficient_data_type')

    h['vdr_dm_metadata_present_flag'] = bool(br.read_bit())
    h['use_prev_vdr_rpu_flag'] = bool(br.read_bit())
    if h['use_prev_vdr_rpu_flag']:
        br.read_ue()  # prev_vdr_rpu_id

    return h


# MEL vs FEL, per Kodi's own ffmpeg codepath (DVDVideoCodecFFmpeg.cpp,
# ce-label-registry branch): condition_met is
# el_spatial_resampling_filter_flag == 1 and disable_residual_flag == 0;
# false means there is no enhancement layer type at all. When met, any
# component carrying a non-default NLQ residual coefficient makes it FEL,
# otherwise MEL. 8388608 (1 << 23) is ffmpeg's own literal "no residual"
# constant for vdr_in_max, not derived, since real content's
# coefficient_log2_denom is always 23.
def _decide_el_type(condition_met, nlq_components):
    if not condition_met or not nlq_components:
        return None
    for c in nlq_components:
        if (c['nlq_offset'] != 0 or c['vdr_in_max'] != 8388608 or
                c['linear_deadzone_slope'] != 0 or c['linear_deadzone_threshold'] != 0):
            return 'FEL'
    return 'MEL'


def _guessed_profile(header):
    if header['vdr_rpu_profile'] == 0:
        return 5 if header['bl_video_full_range_flag'] else 0
    if header['vdr_rpu_profile'] == 1:
        if header['el_spatial_resampling_filter_flag'] and not header['disable_residual_flag']:
            return 7 if header['vdr_bit_depth_minus8'] == 4 else 4
        return 8
    return 0


# exp-golomb "coef" value: an fixed(0)/float(1) coded value combined with its
# fractional bits into one comparable magnitude, matching ffmpeg's
# get_ue_coef() (libavcodec/dovi_rpudec.c) - the reference the el_type
# decision below is ported from
def _combine_coef(int_part, frac_bits, coeff_data_type, log2_denom):
    if coeff_data_type == 0:
        return (int_part << log2_denom) | frac_bits
    (value,) = struct.unpack('>f', frac_bits.to_bytes(4, 'big'))
    return int(value * (1 << log2_denom))


# reshaping curves are walked but not exposed; the NLQ residual parameters
# (profile 7 only) are returned per component since they decide MEL vs FEL
def _parse_rpu_data_mapping(br, header):
    br.read_ue()  # vdr_rpu_id
    br.read_ue()  # mapping_color_space
    br.read_ue()  # mapping_chroma_format_idc

    bl_bit_depth = header['bl_bit_depth_minus8'] + 8
    num_pivots_minus2 = [0] * _NUM_COMPONENTS
    for cmp in range(_NUM_COMPONENTS):
        npm2 = br.read_ue()
        num_pivots_minus2[cmp] = npm2
        for _ in range(npm2 + 2):
            br.read_bits(bl_bit_depth)

    has_nlq = header['rpu_format'] & 0x700 == 0 and not header['disable_residual_flag']
    if has_nlq:
        br.read_bits(3)  # nlq_method_idc, must be 0 (linear deadzone)
        for _ in range(_NLQ_NUM_PIVOTS):
            br.read_bits(bl_bit_depth)  # nlq_pred_pivot_value

    br.read_ue()  # num_x_partitions_minus1
    br.read_ue()  # num_y_partitions_minus1

    coeff_len = header['coefficient_log2_denom_length']
    coeff_int = header['coefficient_data_type'] == 0

    for cmp in range(_NUM_COMPONENTS):
        for _ in range(num_pivots_minus2[cmp] + 1):
            mapping_idc = br.read_ue()
            if mapping_idc == 0:  # polynomial
                poly_order_minus1 = br.read_ue()
                linear_interp_flag = False
                if poly_order_minus1 == 0:
                    linear_interp_flag = bool(br.read_bit())
                if poly_order_minus1 == 0 and linear_interp_flag:
                    raise ValueError('linear interpolation mapping not supported')
                for _j in range(poly_order_minus1 + 2):
                    if coeff_int:
                        br.read_se()
                    br.read_bits(coeff_len)
            elif mapping_idc == 1:  # MMR
                mmr_order_minus1 = br.read_bits(2)
                if coeff_int:
                    br.read_se()
                br.read_bits(coeff_len)
                for _j in range(mmr_order_minus1 + 1):
                    for _k in range(_MMR_MAX_COEFFS):
                        if coeff_int:
                            br.read_se()
                        br.read_bits(coeff_len)
            else:
                raise ValueError('invalid mapping_idc')

    nlq_components = None
    if has_nlq:
        nlq_components = []
        el_bit_depth = header['el_bit_depth_minus8'] + 8
        coeff_data_type = header['coefficient_data_type']
        for _cmp in range(_NUM_COMPONENTS):
            nlq_offset = br.read_bits(el_bit_depth)

            vdr_in_max_int = br.read_ue() if coeff_int else 0
            vdr_in_max_frac = br.read_bits(coeff_len)
            vdr_in_max = _combine_coef(vdr_in_max_int, vdr_in_max_frac, coeff_data_type, coeff_len)

            # LinearDeadzone is the only defined nlq_method_idc value
            slope_int = br.read_ue() if coeff_int else 0
            slope_frac = br.read_bits(coeff_len)
            linear_deadzone_slope = _combine_coef(slope_int, slope_frac, coeff_data_type, coeff_len)

            threshold_int = br.read_ue() if coeff_int else 0
            threshold_frac = br.read_bits(coeff_len)
            linear_deadzone_threshold = _combine_coef(threshold_int, threshold_frac, coeff_data_type,
                                                        coeff_len)

            nlq_components.append({
                'nlq_offset': nlq_offset,
                'vdr_in_max': vdr_in_max,
                'linear_deadzone_slope': linear_deadzone_slope,
                'linear_deadzone_threshold': linear_deadzone_threshold,
            })

    return nlq_components


def _parse_ext_block(br, level, length):
    if level == 1:
        return {'min_pq': br.read_bits(12), 'max_pq': br.read_bits(12), 'avg_pq': br.read_bits(12)}

    if level == 2:
        d = {
            'target_max_pq': br.read_bits(12),
            'trim_slope': br.read_bits(12),
            'trim_offset': br.read_bits(12),
            'trim_power': br.read_bits(12),
            'trim_chroma_weight': br.read_bits(12),
            'trim_saturation_gain': br.read_bits(12),
        }
        ms_weight = br.read_bits(13)
        if ms_weight > 4095:
            ms_weight -= 8192
        d['ms_weight'] = ms_weight
        return d

    if level == 3:
        return {
            'min_pq_offset': br.read_bits(12),
            'max_pq_offset': br.read_bits(12),
            'avg_pq_offset': br.read_bits(12),
        }

    if level == 5:
        return {
            'left': br.read_bits(13),
            'right': br.read_bits(13),
            'top': br.read_bits(13),
            'bottom': br.read_bits(13),
        }

    if level == 6:
        return {
            'max_display_mastering_luminance': br.read_bits(16),
            'min_display_mastering_luminance': br.read_bits(16),
            'max_content_light_level': br.read_bits(16),
            'max_frame_average_light_level': br.read_bits(16),
        }

    if level == 8:
        d = {
            'length': length,
            'target_display_index': br.read_bits(8),
            'trim_slope': br.read_bits(12),
            'trim_offset': br.read_bits(12),
            'trim_power': br.read_bits(12),
            'trim_chroma_weight': br.read_bits(12),
            'trim_saturation_gain': br.read_bits(12),
            'ms_weight': br.read_bits(12),
        }
        if length > 10:
            d['target_mid_contrast'] = br.read_bits(12)
        if length > 12:
            d['clip_trim'] = br.read_bits(12)
        if length > 13:
            for _ in range(6):
                br.read_bits(8)  # saturation_vector_field, not exposed
        if length > 19:
            for _ in range(6):
                br.read_bits(8)  # hue_vector_field, not exposed
        return d

    if level == 9:
        d = {'length': length, 'source_primary_index': br.read_bits(8)}
        if length > 1:
            d['red_x'] = br.read_bits(16)
            d['red_y'] = br.read_bits(16)
            d['green_x'] = br.read_bits(16)
            d['green_y'] = br.read_bits(16)
            d['blue_x'] = br.read_bits(16)
            d['blue_y'] = br.read_bits(16)
            d['white_x'] = br.read_bits(16)
            d['white_y'] = br.read_bits(16)
        return d

    if level == 10:
        d = {
            'length': length,
            'target_display_index': br.read_bits(8),
            'target_max_pq': br.read_bits(12),
            'target_min_pq': br.read_bits(12),
            'target_primary_index': br.read_bits(8),
        }
        if length > 5:
            d['red_x'] = br.read_bits(16)
            d['red_y'] = br.read_bits(16)
            d['green_x'] = br.read_bits(16)
            d['green_y'] = br.read_bits(16)
            d['blue_x'] = br.read_bits(16)
            d['blue_y'] = br.read_bits(16)
            d['white_x'] = br.read_bits(16)
            d['white_y'] = br.read_bits(16)
        return d

    if level == 11:
        content_type = br.read_bits(8)
        byte1 = br.read_bits(8)
        br.read_bits(8)  # reserved_byte2
        br.read_bits(8)  # reserved_byte3
        return {
            'content_type': content_type,
            'whitepoint': byte1 & 0x0F,
            'reference_mode_flag': bool((byte1 >> 4) & 0x01),
        }

    if level == 254:
        return {'dm_mode': br.read_bits(8), 'dm_version_index': br.read_bits(8)}

    # unsupported level (4 anamorphic, 255 debug, reserved): the declared
    # length fully accounts for the block, so it can be skipped wholesale
    br.skip_bits(length * 8)
    return None


def _parse_ext_block_group(br, blocks_out):
    num_ext_blocks = br.read_ue()
    br.align()
    for _ in range(num_ext_blocks):
        length = br.read_ue()
        level = br.read_bits(8)
        start_pos = br.pos
        block = _parse_ext_block(br, level, length)
        pad = length * 8 - (br.pos - start_pos)
        if pad > 0:
            br.skip_bits(pad)
        elif pad < 0:
            raise ValueError('metadata block overran its declared length')
        if block is None:
            continue
        if level in _MULTI_LEVELS:
            blocks_out.setdefault(level, []).append(block)
        else:
            blocks_out[level] = block


def _parse_vdr_dm_data(br, header):
    compressed = header['reserved_zero_3bits'] == 1
    source_min_pq = source_max_pq = 0
    has_source_pq = False

    if compressed:
        br.read_ue()  # affected_dm_metadata_id
        br.read_ue()  # current_dm_metadata_id
        br.read_ue()  # scene_refresh_flag
    else:
        br.read_ue()
        br.read_ue()
        br.read_ue()
        for _ in range(9):
            br.read_bits(16)  # ycc_to_rgb_coef
        for _ in range(3):
            br.read_bits(32)  # ycc_to_rgb_offset
        for _ in range(9):
            br.read_bits(16)  # rgb_to_lms_coef
        br.read_bits(16)  # signal_eotf
        br.read_bits(16)  # signal_eotf_param0
        br.read_bits(16)  # signal_eotf_param1
        br.read_bits(32)  # signal_eotf_param2
        br.read_bits(5)  # signal_bit_depth
        br.read_bits(2)  # signal_color_space
        br.read_bits(2)  # signal_chroma_format
        br.read_bits(2)  # signal_full_range_flag
        source_min_pq = br.read_bits(12)
        source_max_pq = br.read_bits(12)
        br.read_bits(10)  # source_diagonal
        has_source_pq = True

    blocks = {}
    _parse_ext_block_group(br, blocks)  # CM v2.9 levels: 1, 2, 4, 5, 6, 255

    # a legacy CM v2.9-only RPU has nothing left for the v4.0 block group
    if br.bits_left() >= 56:
        _parse_ext_block_group(br, blocks)  # CM v4.0 levels: 3, 8, 9, 10, 11, 254

    return {
        'compressed': compressed,
        'has_source_pq': has_source_pq,
        'source_min_pq': source_min_pq,
        'source_max_pq': source_max_pq,
        'blocks': blocks,
    }


def _build_trim(nits, block, ms_can_disable):
    slope = block['trim_slope']
    offset = block['trim_offset']
    power = block['trim_power']
    chroma_weight = block['trim_chroma_weight']
    saturation_gain = block['trim_saturation_gain']
    ms_weight = block['ms_weight']
    ms_disabled = ms_can_disable and ms_weight == -1

    return {
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


def _primaries_coords(block):
    return {
        'red': (block['red_x'], block['red_y']),
        'green': (block['green_x'], block['green_y']),
        'blue': (block['blue_x'], block['blue_y']),
        'white': (block['white_x'], block['white_y']),
    }


def _resolve(header, dm, nlq_components=None):
    el_flag_condition = (header['el_spatial_resampling_filter_flag'] and
                          not header['disable_residual_flag'])
    result = {
        'profile': _guessed_profile(header),
        'header': {
            'rpu_type': header['rpu_type'],
            'rpu_format': header['rpu_format'],
            'vdr_rpu_profile': header['vdr_rpu_profile'],
            'vdr_rpu_level': header['vdr_rpu_level'],
            'bl_bit_depth': header['bl_bit_depth_minus8'] + 8 if header['vdr_seq_info_present_flag'] else None,
            'el_bit_depth': header['el_bit_depth_minus8'] + 8 if header['vdr_seq_info_present_flag'] else None,
            'vdr_bit_depth': header['vdr_bit_depth_minus8'] + 8 if header['vdr_seq_info_present_flag'] else None,
            'el_spatial_resampling_filter_flag': header['el_spatial_resampling_filter_flag'],
            'disable_residual_flag': header['disable_residual_flag'],
            'el_type': _decide_el_type(el_flag_condition, nlq_components),
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

    if dm is None:
        return result

    result['compressed'] = dm['compressed']
    if not dm['compressed'] and dm['has_source_pq']:
        result['source'] = {
            'min_pq': dm['source_min_pq'],
            'min_nits': pq_to_nits(dm['source_min_pq']),
            'max_pq': dm['source_max_pq'],
            'max_nits': pq_to_nits(dm['source_max_pq']),
        }

    blocks = dm['blocks']
    result['cm_version'] = '4.0' if 254 in blocks else ('2.9' if blocks else None)

    if 1 in blocks:
        b = blocks[1]
        result['l1'] = {
            'min_pq': b['min_pq'], 'min_nits': pq_to_nits(b['min_pq']),
            'max_pq': b['max_pq'], 'max_nits': pq_to_nits(b['max_pq']),
            'avg_pq': b['avg_pq'], 'avg_nits': pq_to_nits(b['avg_pq']),
        }

    if 3 in blocks:
        b = blocks[3]
        result['l3'] = {
            'min_pq_offset': b['min_pq_offset'],
            'max_pq_offset': b['max_pq_offset'],
            'avg_pq_offset': b['avg_pq_offset'],
        }

    if 5 in blocks:
        b = blocks[5]
        result['l5'] = {'left': b['left'], 'right': b['right'], 'top': b['top'], 'bottom': b['bottom']}

    if 6 in blocks:
        b = blocks[6]
        result['l6'] = {
            'max_cll': b['max_content_light_level'],
            'max_fall': b['max_frame_average_light_level'],
            'min_lum_raw': b['min_display_mastering_luminance'],
            'min_lum_nits': b['min_display_mastering_luminance'] * 0.0001,
            'max_lum_raw': b['max_display_mastering_luminance'],
            'max_lum_nits': b['max_display_mastering_luminance'],
        }

    if 9 in blocks:
        b = blocks[9]
        has_coords = b['length'] >= 17
        l9 = {
            'index': b['source_primary_index'],
            'has_coords': has_coords,
            'name': primaries_name(b['source_primary_index'], has_coords),
        }
        if has_coords:
            l9['coords'] = _primaries_coords(b)
        result['l9'] = l9

    if 11 in blocks:
        b = blocks[11]
        result['l11'] = {
            'content_type': b['content_type'],
            'content_type_name': content_type_name(b['content_type']),
            'whitepoint': b['whitepoint'],
            'whitepoint_kelvin': whitepoint_kelvin(b['whitepoint']),
            'whitepoint_name': whitepoint_name(b['whitepoint']),
            'reference_mode': b['reference_mode_flag'],
        }

    l2_list = []
    for b in blocks.get(2, []):
        nits = snap_target_nits(pq_to_nits(b['target_max_pq']))
        l2_list.append(_build_trim(nits, b, ms_can_disable=True))
    l2_list.sort(key=lambda t: t['nits'])
    result['l2'] = l2_list

    l10_index_to_nits = {}
    l10_list = []
    for b in blocks.get(10, []):
        nits = snap_target_nits(pq_to_nits(b['target_max_pq']))
        if nits <= 0:
            continue
        has_coords = b['length'] >= 21
        entry = {
            'target_display_index': b['target_display_index'],
            'nits': nits,
            'target_max_pq': b['target_max_pq'],
            'target_min_pq': b['target_min_pq'],
            'primary_index': b['target_primary_index'],
            'primary_name': primaries_name(b['target_primary_index'], has_coords),
            'has_coords': has_coords,
        }
        if has_coords:
            entry['coords'] = _primaries_coords(b)
        l10_list.append(entry)
        l10_index_to_nits[b['target_display_index']] = nits
    l10_list.sort(key=lambda t: (t['nits'], t['primary_index']))
    result['l10'] = l10_list

    l8_list = []
    for b in blocks.get(8, []):
        idx = b['target_display_index']
        nits = l10_index_to_nits.get(idx, 0) or target_index_nits(idx)
        if nits == 0:
            continue
        trim = _build_trim(nits, b, ms_can_disable=False)
        trim['target_display_index'] = idx
        if 'target_mid_contrast' in b:
            trim['mid_contrast'] = b['target_mid_contrast']
        if 'clip_trim' in b:
            trim['clip_trim'] = b['clip_trim']
        l8_list.append(trim)
    l8_list.sort(key=lambda t: t['nits'])
    result['l8'] = l8_list

    return result


def parse_rpu_payload(payload):
    """Parse a raw RPU payload starting at the 0x19 rpu_nal_prefix byte
    (start-code-emulation-prevention still applied, as in a dovi_tool
    extract-rpu file or an HEVC NAL62 with its 2-byte nal_unit_header
    already stripped). Returns the resolved dict, or None on any parse
    failure or malformed input.
    """
    try:
        cleaned = _clear_emulation_prevention(bytes(payload))
        br = BitReader(cleaned)
        if br.read_bits(8) != _RPU_PREFIX:
            return None
        header = _parse_header(br)
        nlq_components = None
        if not header['use_prev_vdr_rpu_flag']:
            nlq_components = _parse_rpu_data_mapping(br, header)
        dm = _parse_vdr_dm_data(br, header) if header['vdr_dm_metadata_present_flag'] else None
        return _resolve(header, dm, nlq_components)
    except Exception:
        return None


def parse_hevc_nal62(nal):
    """Parse the escaped HEVC NAL unit 62, as delivered whole by the
    dovi.rpu sidedata key (starting with the two nal_unit_header bytes
    7C 01). Returns the resolved dict, or None if this isn't a DV RPU NAL.
    """
    try:
        data = bytes(nal)
    except Exception:
        return None
    if len(data) < 4:
        return None
    if data[0] == 0x7C and data[1] == 0x01:
        return parse_rpu_payload(data[2:])
    if data[0] == _RPU_PREFIX:
        return parse_rpu_payload(data)
    return None


_AV1_T35_SIGNATURE = bytes((0xB5, 0x00, 0x3B, 0x00, 0x00, 0x08, 0x00))


def parse_av1_t35(payload):
    """Best-effort AV1 path: the Dolby Vision ITU-T T.35 metadata OBU
    payload, starting at the country code. Untested against real AV1
    content (all test assets are HEVC) - see README.
    """
    try:
        data = bytes(payload)
    except Exception:
        return None
    if len(data) < 7 or data[:7] != _AV1_T35_SIGNATURE:
        return None
    return parse_rpu_payload(data[7:])
