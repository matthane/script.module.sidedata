# ST 2094-40 (HDR10+) dynamic metadata, ITU-T T.35 payload. Bit layout mirrors
# ffmpeg's av_dynamic_hdr_plus_from_t35 (libavutil/hdr_dynamic_metadata.c),
# the reference the AMLFillFromHdr10PlusT35 device-tested implementation also
# parses through. Window 0 only is exposed, matching that implementation:
# real content is essentially always num_windows == 1.

from ._bits import BitReader

_SIGNATURE = bytes((0xB5, 0x00, 0x3C, 0x00, 0x01, 0x04))


def parse_t35(data):
    try:
        data = bytes(data)
        if len(data) < 8 or data[:6] != _SIGNATURE:
            return None
        return _parse(data[6:])
    except Exception:
        return None


def _skip_window_geometry(br):
    for _ in range(4):
        br.read_bits(16)
    br.read_bits(16)
    br.read_bits(16)
    br.read_bits(8)
    for _ in range(3):
        br.read_bits(16)
    br.read_bit()


def _skip_peak_luminance_matrix(br):
    rows = br.read_bits(5)
    cols = br.read_bits(5)
    for _ in range(rows * cols):
        br.read_bits(4)


def _parse(data):
    br = BitReader(data)

    app_version = br.read_bits(8)
    num_windows = br.read_bits(2)
    if num_windows < 1 or num_windows > 3:
        return None

    for _w in range(1, num_windows):
        _skip_window_geometry(br)

    target_lum = br.read_bits(27)
    if br.read_bit():
        _skip_peak_luminance_matrix(br)

    windows = []
    for _w in range(num_windows):
        maxscl = [br.read_bits(17) for _ in range(3)]
        avg_maxrgb = br.read_bits(17)
        n_pct = br.read_bits(4)
        dist = [(br.read_bits(7), br.read_bits(17)) for _ in range(n_pct)]
        fraction_bright = br.read_bits(10)
        windows.append({
            'maxscl': maxscl,
            'avg_maxrgb': avg_maxrgb,
            'dist': dist,
            'fraction_bright': fraction_bright,
        })

    if br.read_bit():
        _skip_peak_luminance_matrix(br)

    for window in windows:
        tone_mapping_flag = br.read_bit()
        knee_x = knee_y = 0
        anchors = []
        if tone_mapping_flag:
            knee_x = br.read_bits(12)
            knee_y = br.read_bits(12)
            n_anchors = br.read_bits(4)
            anchors = [br.read_bits(10) for _ in range(n_anchors)]
        window['tone_mapping_flag'] = bool(tone_mapping_flag)
        window['knee_x'] = knee_x
        window['knee_y'] = knee_y
        window['bezier_anchors'] = anchors

        if br.read_bit():
            br.read_bits(6)

    w0 = windows[0]
    distribution = [{'percentage': pct, 'nits': val / 10.0} for pct, val in w0['dist']]

    return {
        'application_version': app_version,
        'num_windows': num_windows,
        'targeted_system_display_maximum_luminance': target_lum,
        'maxscl': [v / 10.0 for v in w0['maxscl']],
        'average_maxrgb': w0['avg_maxrgb'] / 10.0,
        'distribution': distribution,
        'fraction_bright_pixels': w0['fraction_bright'] / 10.0,
        'profile': 'B' if w0['tone_mapping_flag'] else 'A',
        'knee_point_x': w0['knee_x'] / 4095.0,
        'knee_point_y': w0['knee_y'] / 4095.0,
        'bezier_anchors': w0['bezier_anchors'],
    }
