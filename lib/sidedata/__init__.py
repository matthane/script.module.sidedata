"""sidedata - pure-Python parsers for the raw DV/HDR sidedata payloads that
Kodi publishes via the player.process(video.sidedata) infolabel.

Public entry point: parse_sidedata(json_str) -> dict. Missing or unparseable
input never raises; every section degrades to None/[] instead, so a
diagnostic overlay reading a malformed frame stays alive.

Result shape of parse_sidedata()
---------------------------------
{
  'flags': [str, ...],           # tokens from dovi.flags, e.g. ['converted']; [] when absent

  'config': {                    # from dovi.config (dvcC/dvvC), or None
    'version_major': int, 'version_minor': int,
    'profile': int, 'level': int,
    'rpu_present': bool, 'el_present': bool, 'bl_present': bool,
    'compat_id': int, 'md_compression': int,
  },

  'rpu': {                       # from dovi.rpu, or None
    'profile': int,              # guessed DV profile (0/4/5/7/8)
    'header': {
      'rpu_type': int, 'rpu_format': int,
      'vdr_rpu_profile': int, 'vdr_rpu_level': int,
      'bl_bit_depth': int or None, 'el_bit_depth': int or None,
      'vdr_bit_depth': int or None,   # meaningful as content depth only with a FEL residual
      'el_spatial_resampling_filter_flag': bool, 'disable_residual_flag': bool,
      'el_type': 'MEL' or 'FEL' or None,   # None when there is no enhancement layer at all;
                                            # see rpu.py's _decide_el_type for the algorithm
                                            # (ported from Kodi's DVDVideoCodecFFmpeg.cpp)
    },
    'compressed': bool,          # dv_md_compression active; source PQ zeroed when true
    'cm_version': '2.9' or '4.0' or None,
    'source': {'min_pq': int, 'min_nits': float, 'max_pq': int, 'max_nits': float} or None,

    'l1': {'min_pq': int, 'min_nits': float, 'max_pq': int, 'max_nits': float,
           'avg_pq': int, 'avg_nits': float} or None,

    'l2': [                      # trim passes, sorted by nits; [] when none
      {
        'nits': int,             # target resolved via exact ST 2084 decode + snap to standard list
        'slope': int, 'offset': int, 'power': int,        # raw 12-bit codes, 2048 neutral
        'chromaweight': int, 'saturation': int,
        'tonedetail': int or None,                        # raw ms_weight; None when disabled (-1 sentinel)
        'ui': {                  # Dolby UI scale, inverted from the raw codes
          'gain': float, 'lift': float or None, 'gamma': float,
          'chromaweight': float, 'saturation': float, 'tonedetail': float or None,
        },
      }, ...
    ],

    'l3': {'min_pq_offset': int, 'max_pq_offset': int, 'avg_pq_offset': int} or None,

    'l5': {'left': int, 'right': int, 'top': int, 'bottom': int} or None,

    'l6': {'max_cll': int, 'max_fall': int,
           'min_lum_raw': int, 'min_lum_nits': float,      # min is 0.0001 cd/m2 units
           'max_lum_raw': int, 'max_lum_nits': int} or None,  # max is already cd/m2

    'l8': [                      # trim passes, target resolved (L10 first, then preset table),
      {                          # entries with no resolvable target are dropped; sorted by nits
        'nits': int, 'target_display_index': int,
        'slope': int, 'offset': int, 'power': int,
        'chromaweight': int, 'saturation': int, 'tonedetail': int,   # unsigned, no disabled sentinel
        'ui': {...},              # same shape as l2[]['ui']
        'mid_contrast': int,      # present only when the block serialization carries it (length > 10)
        'clip_trim': int,         # present only when length > 12
      }, ...
    ],

    'l9': {'index': int, 'name': str, 'has_coords': bool,
           'coords': {'red': (x, y), 'green': (x, y), 'blue': (x, y), 'white': (x, y)}}
          or None,               # 'coords' present only when has_coords; raw 16-bit CIE codes

    'l10': [                     # target display definitions; sorted by (nits, primary_index)
      {
        'target_display_index': int, 'nits': int,
        'target_max_pq': int, 'target_min_pq': int,
        'primary_index': int, 'primary_name': str, 'has_coords': bool,
        'coords': {...},         # present only when has_coords
      }, ...
    ],

    'l11': {'content_type': int, 'content_type_name': str,
            'whitepoint': int, 'whitepoint_kelvin': int, 'whitepoint_name': str,
            'reference_mode': bool} or None,
  },

  'hdr10plus': {                 # from hdr10plus (ST 2094-40 T.35), or None. Window 0 only.
    'application_version': int, 'num_windows': int,
    'targeted_system_display_maximum_luminance': int,   # code is nits directly
    'maxscl': [float, float, float],                    # nits
    'average_maxrgb': float,                             # nits
    'distribution': [{'percentage': int, 'nits': float}, ...],
    'fraction_bright_pixels': float,                     # percent
    'profile': 'A' or 'B',
    'knee_point_x': float, 'knee_point_y': float,        # 0..1
    'bezier_anchors': [int, ...],                        # raw 10-bit codes, count matches profile B curve
  },

  'mdcv': {                      # from mdcv SEI payload, or None
    'primaries': {'red': (x, y), 'green': (x, y), 'blue': (x, y)} or None,  # None when all-zero (unknown)
    'white_point': (x, y),
    'max_luminance': float, 'min_luminance': float,       # nits
  },

  'cll': {'max_cll': int, 'max_fall': int} or None,       # from cll SEI payload
}

Primary names (l9/l10 'name'/'primary_name'), content type names (l11) and the
whitepoint Kelvin formula mirror the device-verified AMLFrameMetadata.h
reference (see convert.py). The RPU bitstream parse follows dovi_tool's
parsing logic (quietvoid, MIT) and is validated against dovi_tool's own JSON
output - see README.md and tests/test_rpu.py. The rpu['header']['el_type']
decision (MEL/FEL) is ported from Kodi's own ffmpeg codepath instead
(DVDVideoCodecFFmpeg.cpp), since dovi_tool's own struct fields don't carry
this classification the same way - see README.md's caveats.
"""

import base64
import json

from . import hdr10plus as _hdr10plus
from . import rpu as _rpu
from . import statics as _statics

__all__ = ['parse_sidedata']


def _empty_result():
    return {
        'flags': [],
        'config': None,
        'rpu': None,
        'hdr10plus': None,
        'mdcv': None,
        'cll': None,
    }


def _decode(value):
    return base64.b64decode(value)


def parse_sidedata(json_str):
    result = _empty_result()

    if not json_str:
        return result

    try:
        data = json.loads(json_str)
    except (TypeError, ValueError):
        return result

    if not isinstance(data, dict):
        return result

    flags = data.get('dovi.flags')
    if isinstance(flags, str) and flags.strip():
        result['flags'] = flags.split()

    config_b64 = data.get('dovi.config')
    if config_b64:
        try:
            result['config'] = _statics.parse_config(_decode(config_b64))
        except Exception:
            result['config'] = None

    rpu_b64 = data.get('dovi.rpu')
    if rpu_b64:
        try:
            raw = _decode(rpu_b64)
        except Exception:
            raw = None
        if raw is not None:
            result['rpu'] = _rpu.parse_hevc_nal62(raw)
            if result['rpu'] is None:
                result['rpu'] = _rpu.parse_av1_t35(raw)

    hdr10plus_b64 = data.get('hdr10plus')
    if hdr10plus_b64:
        try:
            result['hdr10plus'] = _hdr10plus.parse_t35(_decode(hdr10plus_b64))
        except Exception:
            result['hdr10plus'] = None

    mdcv_b64 = data.get('mdcv')
    if mdcv_b64:
        try:
            result['mdcv'] = _statics.parse_mdcv(_decode(mdcv_b64))
        except Exception:
            result['mdcv'] = None

    cll_b64 = data.get('cll')
    if cll_b64:
        try:
            result['cll'] = _statics.parse_cll(_decode(cll_b64))
        except Exception:
            result['cll'] = None

    return result
