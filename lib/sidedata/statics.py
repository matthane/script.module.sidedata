# Fixed-layout payloads: the dvcC/dvvC configuration record and the MDCV/CLL
# SEI messages. Layouts per the sidedata contract (ff_isom_put_dvcc_dvvc for
# the config record, the standard mastering-display-colour-volume and
# content-light-level SEI payloads for mdcv/cll).

import struct

from .convert import mdcv_primaries_name


def parse_config(data):
    data = bytes(data)
    if len(data) < 5:
        return None

    b2, b3, b4 = data[2], data[3], data[4]

    return {
        'version_major': data[0],
        'version_minor': data[1],
        'profile': (b2 >> 1) & 0x7F,
        'level': ((b2 & 0x01) << 5) | (b3 >> 3),
        'rpu_present': bool((b3 >> 2) & 0x01),
        'el_present': bool((b3 >> 1) & 0x01),
        'bl_present': bool(b3 & 0x01),
        'compat_id': (b4 >> 4) & 0x0F,
        'md_compression': (b4 >> 2) & 0x03,
    }


def parse_mdcv(data):
    data = bytes(data)
    if len(data) < 24:
        return None

    (green_x, green_y, blue_x, blue_y, red_x, red_y, white_x, white_y,
     max_lum, min_lum) = struct.unpack('>8HII', data[:24])

    white_point = (white_x / 50000.0, white_y / 50000.0)

    primaries = None
    if not (green_x == green_y == blue_x == blue_y == red_x == red_y == 0):
        red = (red_x / 50000.0, red_y / 50000.0)
        green = (green_x / 50000.0, green_y / 50000.0)
        blue = (blue_x / 50000.0, blue_y / 50000.0)
        primaries = {
            'red': red,
            'green': green,
            'blue': blue,
            'name': mdcv_primaries_name(red, green, blue, white_point),
        }

    return {
        'primaries': primaries,
        'white_point': white_point,
        'max_luminance': max_lum / 10000.0,
        'min_luminance': min_lum / 10000.0,
    }


def parse_cll(data):
    data = bytes(data)
    if len(data) < 4:
        return None

    max_cll, max_fall = struct.unpack('>HH', data[:4])
    return {'max_cll': max_cll, 'max_fall': max_fall}
