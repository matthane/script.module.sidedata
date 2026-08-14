"""sidedata, a CoreELEC addon: parsers for the raw DV/HDR sidedata payloads
that CoreELEC's Amlogic video player publishes via the
player.process(video.sidedata) infolabel (CoreELEC 22, Amlogic only). The
RPU and HDR10+ payloads are parsed by real engines (libdovi, libavutil) via
ctypes; this package is glue, dispatch and conversion only. See README.md.

Public entry point: parse_sidedata(json_str) -> dict. Missing or unparseable
input never raises; every section degrades to None/[] instead, so a
diagnostic overlay reading a malformed frame stays alive. This is a
Python-layer guarantee only. See README.md's Known limitations for the
one uncatchable exception, a libdovi panic on malformed RPU bytes.

Result shape of parse_sidedata()
---------------------------------
{
  'flags': [str, ...],       # tokens from the flags key, e.g. ['converted']; [] when absent
  'structure': str or None,  # 'st-dl' or 'dt-dl' for dual-layer DV; None for single-layer
  'config': {...} or None,   # dvcC/dvvC configuration record
  'rpu': {...} or None,      # Dolby Vision RPU: profile, header, source, l1-l11
  'hdr10plus': {...} or None,  # ST 2094-40 dynamic metadata, window 0 only
  'mdcv': {...} or None,      # mastering display colour volume
  'cll': {...} or None,       # content light level
}

See FIELDS.md for the complete field-by-field reference and its
per-release changelog. The RPU is parsed entirely by libdovi (native.py, quietvoid's
dovi_tool via ctypes); the HDR10+ section is parsed entirely by the
platform's libavutil (avutil.py, av_dynamic_hdr_plus_from_t35 via ctypes).
Name tables and value scalings (PQ-to-nits, target-nits snapping, primaries
and content-type names, whitepoint Kelvin) follow dovi_tool and FFmpeg; see
convert.py. See README.md.
"""

import base64
import json

from . import avutil as _avutil
from . import rpu as _rpu
from . import statics as _statics

__all__ = ['parse_sidedata']


def _empty_result():
    return {
        'flags': [],
        'structure': None,
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

    flags = data.get('flags')
    if isinstance(flags, list):
        result['flags'] = [f for f in flags if isinstance(f, str)]

    structure = data.get('structure')
    if isinstance(structure, str):
        result['structure'] = structure

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
            result['hdr10plus'] = _avutil.parse_t35(_decode(hdr10plus_b64))
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
