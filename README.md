# script.module.dvhdr

Pure-Python parser library for the raw Dolby Vision / HDR sidedata that Kodi
publishes via the `player.process(video.sidedata)` infolabel. Stdlib only
(`json`, `base64`, `struct`) - no external dependencies, so it runs inside
Kodi's bundled Python.

Registered as an `xbmc.python.module` extension point (`library="lib"`), so
any addon that `<import addon="script.module.dvhdr" version="1.0.0"/>` in its
`addon.xml` can `import dvhdr`.

## Usage

```python
import dvhdr

result = dvhdr.parse_sidedata(xbmc.getInfoLabel('player.process(video.sidedata)'))

if result['rpu'] and result['rpu']['l1']:
    print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises: missing or empty input returns the all-None/[]
shape below, and an unparseable individual payload (malformed frame, garbled
sidedata) degrades just that section to `None` rather than the whole call.

## Input contract

`player.process(video.sidedata)` returns a JSON object; each present payload
is a key with base64-encoded bytes, except `dovi.flags` which is plain text:

| key | contents |
|---|---|
| `dovi.config` | 24-byte dvcC/dvvC configuration record |
| `dovi.rpu` | HEVC: the escaped NAL unit 62 verbatim (`7C 01` header + payload). AV1: the Dolby Vision ITU-T T.35 OBU payload from the country code (best-effort, untested - see below) |
| `hdr10plus` | ST 2094-40 ITU-T T.35 payload from the country code (`B5 00 3C 00 01 04`), unescaped |
| `mdcv` | mastering display colour volume SEI payload, 24 bytes |
| `cll` | content light level SEI payload, 4 bytes |
| `dovi.flags` | plain text, space-separated tokens from `{converted, rpu-removed, l5-zeroed}` |

## Result shape

```
dvhdr.parse_sidedata(json_str) -> {
  'flags': [str, ...],           # [] when absent

  'config': {                    # or None
    'version_major': int, 'version_minor': int,
    'profile': int, 'level': int,
    'rpu_present': bool, 'el_present': bool, 'bl_present': bool,
    'compat_id': int, 'md_compression': int,
  },

  'rpu': {                       # or None
    'profile': int,              # guessed DV profile (0/4/5/7/8)
    'header': {
      'rpu_type': int, 'rpu_format': int,
      'vdr_rpu_profile': int, 'vdr_rpu_level': int,
      'bl_bit_depth': int or None, 'el_bit_depth': int or None,
      'vdr_bit_depth': int or None,   # content depth only meaningful with a FEL residual
    },
    'compressed': bool,          # dv_md_compression active; source PQ zeroed when true
    'cm_version': '2.9' or '4.0' or None,
    'source': {'min_pq': int, 'min_nits': float, 'max_pq': int, 'max_nits': float} or None,

    'l1': {'min_pq': int, 'min_nits': float, 'max_pq': int, 'max_nits': float,
           'avg_pq': int, 'avg_nits': float} or None,

    'l2': [                      # trim passes, sorted by nits; [] when none
      {
        'nits': int,             # exact ST 2084 decode, snapped to the standard target list
        'slope': int, 'offset': int, 'power': int,        # raw 12-bit codes, 2048 neutral
        'chromaweight': int, 'saturation': int,
        'tonedetail': int or None,                        # raw ms_weight; None = disabled (-1 sentinel)
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

    'l8': [                      # trim passes, target resolved L10-first then the preset
      {                          # table; unresolvable entries are dropped; sorted by nits
        'nits': int, 'target_display_index': int,
        'slope': int, 'offset': int, 'power': int,
        'chromaweight': int, 'saturation': int, 'tonedetail': int,   # unsigned, no sentinel
        'ui': {...},              # same shape as l2[]['ui']
        'mid_contrast': int,      # present only when the block serialization carries it
        'clip_trim': int,         # present only when the block serialization carries it
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

  'hdr10plus': {                 # or None. Window 0 only (real content is essentially
    'application_version': int, 'num_windows': int,        # always num_windows == 1)
    'targeted_system_display_maximum_luminance': int,      # code is nits directly
    'maxscl': [float, float, float],                       # nits
    'average_maxrgb': float,                                # nits
    'distribution': [{'percentage': int, 'nits': float}, ...],
    'fraction_bright_pixels': float,                        # percent
    'profile': 'A' or 'B',
    'knee_point_x': float, 'knee_point_y': float,           # 0..1
    'bezier_anchors': [int, ...],                           # raw 10-bit codes
  },

  'mdcv': {                      # or None
    'primaries': {'red': (x, y), 'green': (x, y), 'blue': (x, y)} or None,  # None = all-zero/unknown
    'white_point': (x, y),
    'max_luminance': float, 'min_luminance': float,        # nits
  },

  'cll': {'max_cll': int, 'max_fall': int} or None,
}
```

## Structure

```
addon.xml
lib/dvhdr/__init__.py   parse_sidedata() + the full result-shape docstring
lib/dvhdr/rpu.py         Dolby Vision RPU bit parser + field resolution
lib/dvhdr/hdr10plus.py   ST 2094-40 T.35 parser
lib/dvhdr/statics.py     dvcC/dvvC config, MDCV, CLL
lib/dvhdr/convert.py     PQ<->nits, target-nits snapping, name tables, trim UI scale
lib/dvhdr/_bits.py       shared MSB-first bitstream reader
tests/                   stdlib unittest, run with: python3 -m unittest discover tests
```

## Testing

```
python3 -m unittest discover tests
```

The RPU tests are cross-checked against real device-captured content (Signs
2002, profile 8.1) using `dovi_tool`'s own JSON dump as ground truth
(`tests/testdata/signs_frame0.{rpu,json}` and `signs_frame500.{rpu,json}`,
extracted from a longer capture). The HDR10+ tests use a trimmed prefix of a
real HDR10+ HEVC capture (`tests/testdata/lake10_prefix.hevc`) and assert
against values independently confirmed on-device against FFmpeg's own T.35
decoder (see `~/ce22-docs/hdr10plus-labels-plan.md`).

## Known limitations

- **AV1 is untested.** `dvhdr.rpu.parse_av1_t35` implements the AV1 ITU-T T.35
  OBU path best-effort (skip the 7-byte T.35/EMDF header, remove start-code
  emulation prevention, parse as a regular RPU). All test content available
  for this addon is HEVC; no AV1+DV sample was on hand to validate against.
- Two L2 or L8/L10 blocks that resolve to the same nits value (e.g. preset
  indices 24 and 25 both mapping to 300 nits) both appear in their list;
  callers that key by nits should expect the list order (RPU order for
  ties) rather than assuming uniqueness.
- HDR10+ parsing exposes only processing window 0. `num_windows` is still
  reported so a caller can detect the (currently unseen in practice) case
  of multiple windows.
- Individual L8 secondary 6-vector saturation/hue trims (block length 19/25)
  are parsed structurally (to keep bit alignment correct) but not exposed,
  matching the scope of the reference this parser mirrors.

## Credits and licensing

This addon is licensed **GPL-2.0-or-later** (see `addon.xml`), the CoreELEC/
Kodi addon convention.

The Dolby Vision RPU bitstream layout in `lib/dvhdr/rpu.py` was determined by
reading, and is test-validated against the output of, **dovi_tool** by
quietvoid (MIT License, https://github.com/quietvoid/dovi_tool). The MIT
license text and copyright notice are reproduced verbatim in
`LICENSES/dovi_tool.MIT`; see `NOTICE.md` for the full attribution. No
dovi_tool code is vendored.

The HDR10+ (ST 2094-40) parser in `lib/dvhdr/hdr10plus.py` is implemented
from the ATSC A/341 / ST 2094-40 specification and cross-checked against
FFmpeg's `av_dynamic_hdr_plus_from_t35` decoder for field order and bit
widths.

Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10
primaries name table, the L11 content-type and whitepoint tables, and the
L2/L8 trim UI-scale inversion) are ported from `AMLFrameMetadata.h`, the
device-tested CoreELEC reference implementation this module's field names and
scalings mirror.
