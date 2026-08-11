# script.module.sidedata

Parser library for the raw Dolby Vision / HDR sidedata that Kodi publishes
via the `player.process(video.sidedata)` infolabel. Stdlib only (`json`,
`base64`, `struct`, `ctypes`) - no external dependencies, so it runs inside
Kodi's bundled Python.

Parsing is done entirely by real engines, via `ctypes`:

- **Dolby Vision RPU** - [quietvoid's `libdovi`](https://github.com/quietvoid/dovi_tool),
  bundled for aarch64.
- **HDR10+** - FFmpeg's `libavutil`, the CE image's own copy, borrowed at
  runtime (never bundled).

This package itself is dispatch/ctypes glue, unit conversions and the
trivial fixed-layout unpacks (dvcC/dvvC, MDCV, CLL) - no bitstream parsing
lives in Python. See "Pinned versions" below for why that matters.

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
The same applies when an engine simply isn't available on the running
platform - `result['rpu']` and `result['hdr10plus']` are `None` rather than
raising, exactly like a parse failure.

## Pinned versions

Both bindings mirror a fixed struct layout from a specific upstream build,
so a version drift is silent memory corruption, not a compile error -
see `UPDATING.md` for the procedure to move either pin.

| Engine | Pinned to | Struct source | Version check |
|---|---|---|---|
| `libdovi` | `libdovi-3.3.1` | `libdovi/rpu_parser.h` (mirrored in `native.py`) | none - the bundled `.so` *is* that build |
| `libavutil` | major 60 (FFmpeg 8.1.2, CE-22's ffmpeg) | `libavutil/hdr_dynamic_metadata.h` (mirrored in `avutil.py`) | `avutil_version()` gated at load, see below |

`libdovi` is bundled as a known-good binary, so there's nothing to check at
runtime. `libavutil` is never bundled - it's whatever the running platform
ships - so `avutil.py` calls `avutil_version()` on load and refuses a
library whose major doesn't match the pinned one, treating it as
unavailable rather than risking a struct layout mismatch.

quietvoid's `hdr10plus_tool` (the `hdr10plus_rs` capi, same bundling
pattern as `libdovi`) was evaluated as a bundled alternative for HDR10+, but
its public C API has no entry point that parses a T.35 payload in memory -
`hdr10plus_rs_parse_json` reads a file path through the tool's own
extraction pipeline, and the rest of the API is a writer, not a parser -
hence binding directly to the platform's own `libavutil` instead.

## RPU parsing: libdovi

`result['rpu']` is parsed by a real `libdovi.so` (quietvoid's `dovi_tool`),
loaded via `ctypes` (`native.py`). This addon bundles its own aarch64 build
(`lib/sidedata/native_libs/aarch64/libdovi.so`) and loads it preferentially
on that architecture; other architectures fall through to
`SIDEDATA_LIBDOVI_PATH` or a platform-provided `libdovi.so` if either
supplies one. If none of those resolve, `result['rpu']` is `None` -
there is no pure-Python fallback.

The loader tries, in order: the `SIDEDATA_LIBDOVI_PATH` env var (useful for
testing a specific build, on-device or off), this addon's bundled build for
the running `platform.machine()` (`native_libs/<arch>/libdovi.so`, resolved
relative to `native.py`'s own path, never `cwd`), then `libdovi.so` /
`ctypes.util.find_library('dovi')`. Loader failure (missing library, wrong
ABI, anything else) is never raised to callers - `parse_sidedata` just
returns `None` for that section.

`rpu.py` (`parse_hevc_nal62`, `parse_av1_t35`) is a thin dispatch layer over
`native.py`: it names the two input forms `dovi.rpu` can carry (the escaped
HEVC NAL unit 62, or the AV1 Dolby Vision ITU-T T.35 metadata OBU payload)
and calls straight through. All bitstream parsing, value scaling (via
`convert.py`) and result assembly happens in `native.py`, reading libdovi's
`DoviRpuDataHeader` and `DoviVdrDmData` structs directly - see `native.py`'s
module docstring for the struct-layout source of truth.

`rpu['header']['el_type']` (MEL/FEL) is read straight off libdovi's own
`DoviRpuDataHeader.el_type` field - there is no separate decision logic in
this addon for it.

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

  'rpu': {                       # or None (no dovi.rpu payload, parse
                                  # failure, or libdovi unavailable)
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

  'hdr10plus': {                 # or None (no hdr10plus payload, parse failure,
                                  # or libavutil unavailable / version-mismatched).
    'application_version': int, 'num_windows': int,        # Window 0 only (real content
    'targeted_system_display_maximum_luminance': int,      # is essentially always
    'maxscl': [float, float, float],                       # num_windows == 1)
    'average_maxrgb': float,
    'distribution': [{'percentage': int, 'nits': float}, ...],
    'fraction_bright_pixels': float,
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
lib/sidedata/rpu.py         RPU dispatch (parse_hevc_nal62 / parse_av1_t35) over native.py
lib/sidedata/native.py      ctypes bindings to libdovi, bit parsing, result assembly
lib/sidedata/native_libs/aarch64/libdovi.so   bundled libdovi build
lib/sidedata/avutil.py      ctypes binding to libavutil for HDR10+ (av_dynamic_hdr_plus_from_t35)
lib/sidedata/statics.py     dvcC/dvvC config, MDCV, CLL - fixed-layout unpacks
lib/sidedata/convert.py     PQ<->nits, target-nits snapping, name tables, trim UI scale, HDR10+ scalings
tools/build-libdovi.sh   rebuilds the bundled libdovi.so, see UPDATING.md
tests/                   stdlib unittest, run with: python3 -m unittest discover tests
```

## Testing

```
python3 -m unittest discover tests
```

The RPU golden tests run every fixture this repo carries through the real
`libdovi` bindings and check the result field-by-field against `dovi_tool`'s
own JSON dump:

- `tests/testdata/signs_frame0.{rpu,json}` / `signs_frame500.{rpu,json}` -
  real device-captured content (Signs 2002, profile 8.1); frame 500 also
  exercises L8/L10 target resolution.
- `tests/testdata/dv10_av1_frame{0,700}.{t35,json}` - two ITU-T T.35
  metadata OBU payloads walked out of a real AV1 elementary stream, checked
  against `dovi_tool`'s own JSON dump of the same title's
  separately-extracted regular-RPU form at the matching frame index (every
  one of the title's 1450 frames was cross-checked this way during
  development, not just the two committed fixtures - see git history).
- `tests/testdata/dv7fel_frame0.{rpu,json}` / `dv7mel_frame0.{rpu,json}` -
  real dual-layer profile 7 content, one FEL title and one MEL title, so
  `el_type` is checked against real NLQ residual data, not just a
  synthetic flag flip.

These tests need a real `libdovi.so` to mean anything, so they're
`skipUnless` one is available - the bundled aarch64 build satisfies that
automatically on-device; on other hosts, `SIDEDATA_LIBDOVI_PATH`. For local
development this repo's test suite auto-detects a host-arch build at
`~/ce/dvhdr-testdata/libdovi.so.3.3.1.x86_64` (outside the repo - never
packaged) and points `SIDEDATA_LIBDOVI_PATH` at it if present, so the golden
suite runs for real rather than skipping; see `tools/build-libdovi.sh` for
building one. The rest of `tests/test_native.py` - loader failure modes,
the bundled-arch-mismatch fallback, and the never-raise contract on
malformed/truncated/bit-flipped input - runs unconditionally, without
needing a native library at all.

HDR10+ golden testing (`tests/test_hdr10plus.py`) works the same way but
against `libavutil`: it's `skipUnless` a version-matched `libavutil` loads,
gated on `avutil_version()`'s major (see "Pinned versions"). A typical dev
host's system ffmpeg is a different major, so that test is expected to skip
off-device - HDR10+ conformance against this fixture was previously proven
against compiled ffmpeg (see git history for the pure-Python parser this
addon carried before this cut, and its device cross-check), and is verified
on device against CE-22's own `libavutil.so.60`. `tests/test_avutil.py`
covers the loader and version gate unconditionally, the same way
`test_native.py` does for `libdovi`.

## Known limitations

- Two L2 or L8/L10 blocks that resolve to the same nits value (e.g. preset
  indices 24 and 25 both mapping to 300 nits) both appear in their list;
  callers that key by nits should expect the list order (RPU order for
  ties) rather than assuming uniqueness.
- HDR10+ parsing exposes only processing window 0. `num_windows` is still
  reported so a caller can detect the (currently unseen in practice) case
  of multiple windows.
- Individual L8 secondary 6-vector saturation/hue trims (block length 19/25)
  are not exposed by libdovi's own `DoviExtMetadataBlockLevel8`, matching
  the scope of the reference this addon's field names mirror.

## Credits and licensing

This addon is licensed **GPL-2.0-or-later** (see `addon.xml`), the CoreELEC/
Kodi addon convention.

`lib/sidedata/native.py` loads a `libdovi.so` build via `ctypes` at
runtime; it declares ctypes structs mirroring `libdovi-3.3.1`'s public C
header (`libdovi/rpu_parser.h`) so it can call into that build directly. This
addon bundles an unmodified aarch64 build of `libdovi-3.3.1`
(`lib/sidedata/native_libs/aarch64/libdovi.so`, MIT License, quietvoid,
https://github.com/quietvoid/dovi_tool) and loads it in place of a
platform-provided one on that architecture - see `NOTICE.md` and
`UPDATING.md`. The MIT license text and copyright notice are reproduced in
`LICENSES/dovi_tool.MIT`.

`lib/sidedata/avutil.py` loads the platform's own `libavutil.so` (part of
FFmpeg, LGPL-2.1-or-later) via `ctypes` at runtime and calls
`av_dynamic_hdr_plus_from_t35` directly; it declares ctypes structs
mirroring `libavutil/hdr_dynamic_metadata.h` from FFmpeg 8.1.2, the version
CE-22 ships. No FFmpeg code is vendored or linked, and nothing is
distributed with this addon for this path - see `NOTICE.md`.

`rpu['header']['el_type']` (MEL/FEL) is read directly from libdovi's own
`DoviRpuDataHeader.el_type` field.

Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10
primaries name table, the L11 content-type and whitepoint tables, the L2/L8
trim UI-scale inversion, and the HDR10+ raw-code-to-nits/percent scalings)
are ported from `AMLFrameMetadata.h`, the device-tested CoreELEC reference
implementation this module's field names and scalings mirror.
