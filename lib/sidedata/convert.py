# Value scalings and name tables shared by the RPU and HDR10+ parsers. The
# nits/kelvin/name conversions follow dovi_tool's output conventions and the
# Dolby level semantics it implements, and the golden tests hold them to
# dovi_tool's and FFmpeg's values on real streams.

_ST2084_Y_MAX = 10000.0
_ST2084_M1 = 2610.0 / 16384.0
_ST2084_M2 = (2523.0 / 4096.0) * 128.0
_ST2084_C1 = 3424.0 / 4096.0
_ST2084_C2 = (2413.0 / 4096.0) * 32.0
_ST2084_C3 = (2392.0 / 4096.0) * 32.0

# well known codes returned exactly, the 12 bit quantization rounds them off
_EXACT_PQ_NITS = {
    0: 0.0,
    7: 0.0001,
    10: 0.0002,
    17: 0.0005,
    26: 0.001,
    38: 0.002,
    62: 0.005,
    3079: 1000.0,
    3388: 2000.0,
    3696: 4000.0,
    4095: 10000.0,
}


def pq_to_nits(pq):
    if pq in _EXACT_PQ_NITS:
        return _EXACT_PQ_NITS[pq]

    pq_pow = (pq / 4095.0) ** (1.0 / _ST2084_M2)
    num = max(pq_pow - _ST2084_C1, 0.0)
    den = _ST2084_C2 - _ST2084_C3 * pq_pow

    if abs(den) < 1e-12:
        return 0.0

    return _ST2084_Y_MAX * (num / den) ** (1.0 / _ST2084_M1)


_SNAP_TARGETS = (48, 100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 1000,
                 1500, 2000, 2500, 3000, 4000, 10000)


def snap_target_nits(nits):
    for target in _SNAP_TARGETS:
        if abs(nits - target) <= max(target * 0.04, 10.0):
            return target
    return int(round(nits))


# nits for the preset L8/L10 target_display_index values. 20/22/23 belong to
# the mastering display id namespace and unknown indices resolve nothing.
# 24/25 come from dolby's target display documentation, not dovi_tool's
# preset list, so they will not cross-check against its sources
_TARGET_INDEX_NITS = {
    1: 100,
    16: 48, 18: 48, 21: 48,
    24: 300, 25: 300,
    27: 600, 28: 600,
    37: 2000, 38: 2000,
    42: 108,
    48: 1000, 49: 1000,
}


def target_index_nits(index):
    return _TARGET_INDEX_NITS.get(index, 0)


# preset names as spelled by dovi_tool; 255 and explicit coordinates mean a
# custom set, other unnamed indices render raw
_PRIMARIES_NAMES = {
    0: 'DCI-P3 D65',
    1: 'BT.709',
    2: 'BT.2020',
    3: 'SMPTE-C',
    4: 'BT.601',
    5: 'DCI-P3',
    6: 'ACES',
    7: 'S-Gamut',
    8: 'S-Gamut-3.Cine',
}


def primaries_name(index, has_coords):
    name = _PRIMARIES_NAMES.get(index)
    if name is not None:
        return name
    if index == 255 or has_coords:
        return 'custom'
    return str(index)


# CIE xy chromaticities for the sets in _PRIMARIES_NAMES, dovi_tool's own
# PREDEFINED_COLORSPACE_PRIMARIES table (primaries.rs), red/green/blue/white
_PRIMARIES_COORDS = {
    0: ((0.680, 0.320), (0.265, 0.690), (0.150, 0.060), (0.3127, 0.3290)),
    1: ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060), (0.3127, 0.3290)),
    2: ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046), (0.3127, 0.3290)),
    3: ((0.630, 0.340), (0.310, 0.595), (0.155, 0.070), (0.3127, 0.3290)),
    4: ((0.640, 0.330), (0.290, 0.600), (0.150, 0.060), (0.3127, 0.3290)),
    5: ((0.680, 0.320), (0.265, 0.690), (0.150, 0.060), (0.3140, 0.3510)),
    6: ((0.7347, 0.2653), (0.0, 1.0), (0.0001, -0.077), (0.32168, 0.33767)),
    7: ((0.730, 0.280), (0.140, 0.855), (0.100, -0.050), (0.3127, 0.3290)),
    8: ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087), (0.3127, 0.3290)),
}

_PRIMARIES_MATCH_TOLERANCE = 0.001


def _coords_close(a, b):
    return (abs(a[0] - b[0]) <= _PRIMARIES_MATCH_TOLERANCE and
            abs(a[1] - b[1]) <= _PRIMARIES_MATCH_TOLERANCE)


# matches decoded mdcv primaries/white point against _PRIMARIES_COORDS
# within the SEI's own 1/50000 quantization; returns the _PRIMARIES_NAMES
# text for the first set that matches all four points, None otherwise
def mdcv_primaries_name(red, green, blue, white):
    for index, (table_red, table_green, table_blue, table_white) in _PRIMARIES_COORDS.items():
        if (_coords_close(red, table_red) and _coords_close(green, table_green) and
                _coords_close(blue, table_blue) and _coords_close(white, table_white)):
            return _PRIMARIES_NAMES[index]
    return None


# content type names per Dolby's L11 content type metadata article; 0 is a
# defined value, undocumented codes render raw
_CONTENT_TYPE_NAMES = {
    0: 'Default',
    1: 'Movies',
    2: 'Game',
    3: 'Sport',
    4: 'User Generated Content',
}


def content_type_name(content_type):
    return _CONTENT_TYPE_NAMES.get(content_type, str(content_type))


def whitepoint_kelvin(code):
    return 6504 + 375 * code


# dovi_tool's interpretation, D65 at code 0. The patent's table is
# contradicted by observed display behavior; see trim-labels-plan.md
def whitepoint_name(code):
    if code == 0:
        return '6504K (D65)'
    return '{}K'.format(whitepoint_kelvin(code))


# HDR10+ (ST 2094-40) raw code scalings, ffmpeg's own denominators from
# av_dynamic_hdr_plus_from_t35 (libavutil/hdr_dynamic_metadata.c: rgb_den,
# fraction_pixel_den, knee_point_den). avutil.py hands these the .num off
# each AVRational it reads, mirroring what the pure parser did with the raw
# bitstream code directly
def hdr10plus_rgb_nits(code):
    return code / 10.0


def hdr10plus_fraction_bright_percent(code):
    return code / 10.0


def hdr10plus_knee_point(code):
    return code / 4095.0


# one trim control shared by L2 and L8 UI scale. lift, gain and gamma jointly
# invert the slope/offset/power encoding that CM XML tooling writes into the
# RPU; ms_disabled mirrors the L2 ms_weight -1 sentinel (tone detail off)
def trim_ui_values(slope, offset, power, chroma_weight, saturation_gain, ms_weight, ms_disabled):
    slope_f = (slope - 2048) / 2048.0
    offset_f = (offset - 2048) / 2048.0
    power_f = (power - 2048) / 2048.0
    gain = slope_f + offset_f

    lift = None
    if abs(gain + 2.0) >= 1e-12:
        lift = 2.0 * offset_f / (gain + 2.0)

    gamma = 4.0 / (power_f + 2.0) - 2.0

    return {
        'gain': gain,
        'lift': lift,
        'gamma': gamma,
        'chromaweight': (chroma_weight - 2048) / 2048.0,
        'saturation': (saturation_gain - 2048) / 2048.0,
        'tonedetail': None if ms_disabled else (ms_weight - 2048) / 2048.0,
    }
