# script.module.sidedata

Parser library for the raw Dolby Vision / HDR sidedata that Kodi publishes
via the `player.process(video.sidedata)` infolabel. Stdlib only (`json`,
`base64`, `struct`, `ctypes`) - no external dependencies, so it runs inside
Kodi's bundled Python. RPU parsing prefers a native `libdovi` (via
`ctypes`) - this addon ships its own aarch64 build and loads it
preferentially on that architecture - and otherwise falls back to a bundled
pure-Python parser - see "RPU backend" below.

Registered as an `xbmc.python.module` extension point (`library="lib"`), so
any addon that `<import addon="script.module.sidedata" version="1.0.0"/>` in its
`addon.xml` can `import sidedata`.

## Usage

```python
import sidedata

result = sidedata.parse_sidedata(xbmc.getInfoLabel('player.process(video.sidedata)'))

if result['rpu'] and result['rpu']['l1']:
    print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises: missing or empty input returns the all-None/[]
shape below, and an unparseable individual payload (malformed frame, garbled
sidedata) degrades just that section to `None` rather than the whole call.

## RPU backend: native libdovi or the bundled parser

The Dolby Vision RPU section (`result['rpu']`) is parsed by one of two
backends, chosen automatically and transparently - the result shape is
identical either way:

- **`libdovi`**: a real `libdovi.so` (quietvoid's `dovi_tool`), loaded via
  `ctypes`. This is the preferred path: it's the reference implementation
  itself, not a port of it. This addon bundles its own aarch64 build
  (`lib/sidedata/native_libs/aarch64/libdovi.so`) and loads it
  preferentially on that architecture; other architectures fall back to
  the `builtin` parser below unless `SIDEDATA_LIBDOVI_PATH` or the
  platform itself supplies one.
- **`builtin`**: this addon's pure-Python RPU parser (`rpu.py`), used when
  no native library is available.

`sidedata.parser_backend()` reports which one is active (`'libdovi'` or
`'builtin'`). The bundled pure-Python parser is not just a fallback: it's
also this addon's own conformance reference. It was built and is still
tested against `dovi_tool`'s own JSON dump (`tests/test_rpu.py`), and the
native ctypes bindings in `lib/sidedata/native.py` are in turn validated
against *it* - `tests/test_native.py` runs every golden RPU fixture this
repo carries through both backends and asserts the result dicts are
identical. So the chain is: dovi_tool validates the bundled parser, and the
bundled parser validates the bindings.

The native path calls `dovi_parse_unspec62_nalu` / `dovi_parse_itu_t35_dovi_metadata_obu`
directly on the same bytes the pure parser receives, reads the header and
`vdr_dm_data` structs, and frees everything through libdovi's own
`dovi_rpu_free*` calls before returning - see `native.py`'s module docstring
for the struct-layout source of truth. Value scalings, name tables and the
L10-first L8/L2 target resolution are shared with the pure parser through
`convert.py`, so the two backends cannot drift in how they render the same
raw fields; only `el_type` is deliberately sourced differently between them
(see "RPU enhancement layer type" below).

If a payload makes the native backend throw or return nothing where the
pure parser can resolve a result, that one payload falls back to the pure
parser and the divergence is logged once (not disabled going forward - a
transient bad frame doesn't strand playback on the slower backend for the
rest of the stream). Loader failure (missing library, wrong ABI, anything
else) is never raised to callers: `parser_backend()` just reports `'builtin'`.

The loader tries, in order: the `SIDEDATA_LIBDOVI_PATH` env var (useful for
testing a specific build, on-device or off), this addon's bundled build for
the running `platform.machine()` (`native_libs/<arch>/libdovi.so`, resolved
relative to `native.py`'s own path, never `cwd`), then `libdovi.so` /
`ctypes.util.find_library('dovi')` as before. No bundled directory for the
current architecture (e.g. an x86_64 host, an armv7 device) just falls
through to that last step, same as if bundling didn't exist.

## Input contract

`player.process(video.sidedata)` returns a JSON object; each present payload
is a key with base64-encoded bytes, except `dovi.flags` which is plain text:

| key | contents |
|---|---|
| `dovi.config` | 24-byte dvcC/dvvC configuration record |
| `dovi.rpu` | HEVC: the escaped NAL unit 62 verbatim (`7C 01` header + payload). AV1: the Dolby Vision ITU-T T.35 OBU payload from the country code (see below) |
| `hdr10plus` | ST 2094-40 ITU-T T.35 payload from the country code (`B5 00 3C 00 01 04`), unescaped |
| `mdcv` | mastering display colour volume SEI payload, 24 bytes |
| `cll` | content light level SEI payload, 4 bytes |
| `dovi.flags` | plain text, space-separated tokens from `{converted, rpu-removed, l5-zeroed}` |

## Result shape

```
sidedata.parse_sidedata(json_str) -> {
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
      'el_spatial_resampling_filter_flag': bool, 'disable_residual_flag': bool,
      'el_type': 'MEL' or 'FEL' or None,   # None = no enhancement layer (e.g. profile 8)
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
lib/sidedata/__init__.py   parse_sidedata() + the full result-shape docstring
lib/sidedata/rpu.py         Dolby Vision RPU bit parser, field resolution, native/pure dispatch
lib/sidedata/native.py      ctypes bindings to libdovi (bundled or platform-provided)
lib/sidedata/native_libs/aarch64/libdovi.so   bundled native RPU parser build
lib/sidedata/hdr10plus.py   ST 2094-40 T.35 parser
lib/sidedata/statics.py     dvcC/dvvC config, MDCV, CLL
lib/sidedata/convert.py     PQ<->nits, target-nits snapping, name tables, trim UI scale
lib/sidedata/_bits.py       shared MSB-first bitstream reader
tools/build-libdovi.sh   rebuilds the bundled libdovi.so, see UPDATING.md
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

`sidedata.rpu.parse_av1_t35` follows dovi_tool's own AV1 module
(`dolby_vision/src/av1/{mod,emdf}.rs`, `DoviRpu::parse_itu_t35_dovi_metadata_obu`)
for unwrapping the EMDF container around the RPU. It's golden-tested against
real AV1+DV content: `tests/testdata/dv10_av1_frame{0,700}.{t35,json}` are two
ITU-T T.35 metadata OBU payloads walked out of a real AV1 elementary stream,
checked against `dovi_tool`'s own JSON dump of the same title's
separately-extracted regular-RPU form at the matching frame index. Every one
of the title's 1450 frames was cross-checked field-for-field this way during
development (not just the two committed fixtures, to keep the repo small);
zero mismatches. It's also round-trip tested against the HEVC fixture above
via a synthetic test-side EMDF writer (the exact inverse of the parser), and
fuzzed with truncations and header bit flips to confirm the never-raise
contract. Real-stream verification on an actual AV1+DV playback device is
still pending.

The MEL/FEL enhancement layer type is golden-tested against real dual-layer
profile 7 content: `tests/testdata/dv7fel_frame0.{rpu,json}` and
`dv7mel_frame0.{rpu,json}` (see "RPU enhancement layer type" below).

`tests/test_native.py` is the native/pure conformance suite (see "RPU
backend" above): its dict-equality checks against every golden fixture are
`skipUnless` a native `libdovi.so` is available, which the bundled aarch64
build satisfies automatically there; elsewhere it's `SIDEDATA_LIBDOVI_PATH`
or `ctypes.util.find_library('dovi')`, with a skip message explaining how
to build one (`tools/build-libdovi.sh`, see `UPDATING.md`). The rest of
that file - loader failure modes, the per-payload fallback, and
`parser_backend()` - runs unconditionally, without needing a native library
at all.

## Known limitations

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

## RPU enhancement layer type (MEL/FEL)

`rpu['header']['el_type']` is the one field the two backends resolve
differently by design: the native backend reads it straight off libdovi's
own `DoviRpuDataHeader.el_type`, while the `builtin` backend below ports the
decision from Kodi's own ffmpeg codepath. Both determine MEL/FEL from the
same underlying NLQ residual data and agree on every fixture this repo
carries (`tests/test_native.py`), but this is the one place a hand-written
port and the upstream implementation could diverge on unusual content
without it being this addon's bug.

The `builtin` backend is ported from Kodi's own ffmpeg codepath
(`DVDVideoCodecFFmpeg.cpp`, `ce-label-registry` branch of `~/ce/xbmc`), not
from dovi_tool: when `el_spatial_resampling_filter_flag == 1` and
`disable_residual_flag == 0`, the type defaults to `'MEL'`, upgraded to
`'FEL'` the moment any of the three color components carries a non-default
NLQ residual coefficient (`nlq_offset != 0`, `vdr_in_max != 8388608`,
`linear_deadzone_slope != 0`, or `linear_deadzone_threshold != 0` - the
`8388608 = 1 << 23` constant is ffmpeg's own literal "no residual" value,
mirrored as-is rather than derived, since real content's
`coefficient_log2_denom` is always 23). Outside that flag condition there is
no enhancement layer at all and `el_type` is `None`.

It's golden-tested against real dual-layer profile 7 content:
`tests/testdata/dv7fel_frame0.{rpu,json}` and `dv7mel_frame0.{rpu,json}` are
frame 0 of a real FEL title and a real MEL title respectively (RPUs walked
out with `dovi_tool extract-rpu`, ground truth from `dovi_tool`'s own `info`
JSON dump of the same frame - its summary independently reports "Profile: 7
(FEL)" and "Profile: 7 (MEL)" for the two titles). The FEL fixture's frame 0
carries a non-default NLQ residual, so this exercises the actual MEL-vs-FEL
branch of the decision, not just the flag condition (`tests/test_rpu.py`'s
`TestElTypeRealFixtures`).

## Credits and licensing

This addon is licensed **GPL-2.0-or-later** (see `addon.xml`), the CoreELEC/
Kodi addon convention.

The Dolby Vision RPU bitstream layout in `lib/sidedata/rpu.py` was determined by
reading, and is test-validated against the output of, **dovi_tool** by
quietvoid (MIT License, https://github.com/quietvoid/dovi_tool). The MIT
license text and copyright notice are reproduced verbatim in
`LICENSES/dovi_tool.MIT`; see `NOTICE.md` for the full attribution. No
dovi_tool code is vendored. The AV1 ITU-T T.35 / EMDF unwrapping in
`parse_av1_t35` is likewise determined by reading dovi_tool's
`dolby_vision/src/av1/mod.rs` and `emdf.rs` (tag `libdovi-3.3.1`).

`lib/sidedata/native.py` loads a `libdovi.so` build via `ctypes` at
runtime; it declares ctypes structs mirroring `libdovi-3.3.1`'s public C
header (`libdovi/rpu_parser.h`) so it can call into that build directly.
This addon bundles an unmodified aarch64 build of `libdovi-3.3.1`
(`lib/sidedata/native_libs/aarch64/libdovi.so`) and loads it in place of a
platform-provided one on that architecture - see `NOTICE.md` and
`UPDATING.md`.

The HDR10+ (ST 2094-40) parser in `lib/sidedata/hdr10plus.py` is implemented
from the ATSC A/341 / ST 2094-40 specification and cross-checked against
FFmpeg's `av_dynamic_hdr_plus_from_t35` decoder for field order and bit
widths.

The `el_type` (MEL/FEL) decision in `lib/sidedata/rpu.py` is ported from
Kodi's own `DVDVideoCodecFFmpeg.cpp` (`ce-label-registry` branch,
`~/ce/xbmc`) - Kodi is GPL-2.0-or-later, the same license this addon ships
under, so no separate license file is needed for that portion; no Kodi code
is vendored.

Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10
primaries name table, the L11 content-type and whitepoint tables, and the
L2/L8 trim UI-scale inversion) are ported from `AMLFrameMetadata.h`, the
device-tested CoreELEC reference implementation this module's field names and
scalings mirror.
