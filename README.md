# script.module.sidedata

A CoreELEC addon. It is a parser library for the raw Dolby Vision and HDR
sidedata that CoreELEC's Amlogic video player publishes via the
`player.process(video.sidedata)` infolabel. It's built for CoreELEC 22 and
runs on all of CoreELEC 22's current Amlogic devices, which is CoreELEC's
whole current device base. The infolabel it parses is CoreELEC-specific and
does not exist on stock Kodi, so stock Kodi is not supported. It's stdlib only
(`json`, `base64`, `struct`, `ctypes`), with no external dependencies, and
runs inside Kodi's bundled Python.

Parsing is done entirely by real engines, called via `ctypes`:

- Dolby Vision RPU parsing uses [quietvoid's `libdovi`](https://github.com/quietvoid/dovi_tool), bundled for aarch64.
- HDR10+ parsing uses FFmpeg's `libavutil`, CoreELEC's own copy, borrowed at runtime and never bundled.

This package itself is dispatch and ctypes glue, unit conversions, and the
trivial fixed-layout unpacks for dvcC/dvvC, MDCV and CLL. No bitstream
parsing lives in Python; see "Pinned versions" below for why that matters.

Registered as an `xbmc.python.module` extension point (`library="lib"`), so
any addon can `import sidedata` after declaring
`<import addon="script.module.sidedata" version="1.2.0"/>` (a minimum
version, per Kodi's addon.xml `<import>` semantics) in its own `addon.xml`.

## Usage

```python
import sidedata

result = sidedata.parse_sidedata(xbmc.getInfoLabel('player.process(video.sidedata)'))

if result['rpu'] and result['rpu']['l1']:
    print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises. Missing or empty input returns the
all-None/[] shape below, and an unparseable individual payload (a malformed
frame, garbled sidedata) degrades just that section to `None` rather than
the whole call. The same applies when an engine isn't available on the
running platform: `result['rpu']` and `result['hdr10plus']` are `None`
rather than raising, exactly like a parse failure.

## Pinned versions

Both bindings mirror a fixed struct layout from a specific upstream build.
A version drift is silent memory corruption, not a compile error, so see
`UPDATING.md` for the procedure to move either pin.

| Engine | Pinned to | Struct source | Version check |
|---|---|---|---|
| `libdovi` | `libdovi-3.3.1` | `libdovi/rpu_parser.h` (mirrored in `native.py`) | none, the bundled `.so` *is* that build |
| `libavutil` | major 60 (FFmpeg 8.1.2, CoreELEC 22's ffmpeg) | `libavutil/hdr_dynamic_metadata.h` (mirrored in `avutil.py`) | `avutil_version()` gated at load, see below |

`libdovi` is bundled as a known-good binary, so there's nothing to check at
runtime. `libavutil` is never bundled: it's whatever CoreELEC ships, so
`avutil.py` calls `avutil_version()` on load and refuses a library whose
major doesn't match the pinned one, treating it as unavailable rather than
risking a struct layout mismatch.

quietvoid's `hdr10plus_tool` (the `hdr10plus_rs` capi, using the same
bundling pattern as `libdovi`) was evaluated as a bundled alternative for
HDR10+. Its public C API has no entry point that parses a T.35 payload in
memory: `hdr10plus_rs_parse_json` reads a file path through the tool's own
extraction pipeline, and the rest of the API is a writer, not a parser.
That's why this binds directly to CoreELEC's own `libavutil` instead.

## RPU parsing: libdovi

`result['rpu']` is parsed by a real `libdovi.so` (quietvoid's `dovi_tool`),
loaded via `ctypes` in `native.py`. This addon bundles its own aarch64
build (`lib/sidedata/native_libs/aarch64/libdovi.so`) and loads it
preferentially on that architecture. Other architectures fall through to
`SIDEDATA_LIBDOVI_PATH` or a platform-provided `libdovi.so` if either
supplies one. If none of those resolve, `result['rpu']` is `None`; there is
no pure-Python fallback.

The loader tries, in order: the `SIDEDATA_LIBDOVI_PATH` env var (useful for
testing a specific build, on-device or off), this addon's bundled build for
the running `platform.machine()` (`native_libs/<arch>/libdovi.so`, resolved
relative to `native.py`'s own path, never `cwd`), then `libdovi.so` or
`ctypes.util.find_library('dovi')`. Loader failure, whether a missing
library, the wrong ABI, or anything else, is never raised to callers;
`parse_sidedata` just returns `None` for that section.

`rpu.py` (`parse_hevc_nal62`, `parse_av1_t35`) is a thin dispatch layer over
`native.py`. It names the two input forms `dovi.rpu` can carry, the escaped
HEVC NAL unit 62 or the AV1 Dolby Vision ITU-T T.35 metadata OBU payload,
and calls straight through. All bitstream parsing, value scaling (via
`convert.py`) and result assembly happens in `native.py`, which reads
libdovi's `DoviRpuDataHeader` and `DoviVdrDmData` structs directly; see
`native.py`'s module docstring for the struct-layout source of truth.

`rpu['header']['el_type']` (MEL/FEL) is read straight off libdovi's own
`DoviRpuDataHeader.el_type` field. This addon has no separate decision
logic for it.

## Input contract

CoreELEC's `player.process(video.sidedata)` returns a JSON object. Each
present payload is a key with base64-encoded bytes, except `dovi.flags`,
which is plain text:

| key | contents |
|---|---|
| `dovi.config` | 24-byte dvcC/dvvC configuration record |
| `dovi.rpu` | HEVC: the escaped NAL unit 62 verbatim (`7C 01` header + payload). AV1: the Dolby Vision ITU-T T.35 OBU payload from the country code (see below) |
| `hdr10plus` | ST 2094-40 ITU-T T.35 payload from the country code (`B5 00 3C 00 01 04`), unescaped |
| `mdcv` | mastering display colour volume SEI payload, 24 bytes |
| `cll` | content light level SEI payload, 4 bytes |
| `dovi.flags` | plain text, space-separated tokens from `{converted, rpu-removed, l5-zeroed}` |

## Result shape

`parse_sidedata()` returns a dict with six top-level keys: `flags`,
`config`, `rpu`, `hdr10plus`, `mdcv`, `cll`. Every key except `flags` is
`None` when its sidedata payload is absent, fails to parse, or, for `rpu`
and `hdr10plus`, the parsing engine isn't available on the running
platform.

See [FIELDS.md](FIELDS.md) for the full field-by-field reference, pinned
per addon release.

## Structure

```
addon.xml
FIELDS.md                 result-shape field reference, pinned per addon release
lib/sidedata/__init__.py   parse_sidedata() entry point
lib/sidedata/rpu.py         RPU dispatch (parse_hevc_nal62 / parse_av1_t35) over native.py
lib/sidedata/native.py      ctypes bindings to libdovi, bit parsing, result assembly
lib/sidedata/native_libs/aarch64/libdovi.so   bundled libdovi build
lib/sidedata/avutil.py      ctypes binding to libavutil for HDR10+ (av_dynamic_hdr_plus_from_t35)
lib/sidedata/statics.py     dvcC/dvvC config, MDCV, CLL (fixed-layout unpacks)
lib/sidedata/convert.py     PQ<->nits, target-nits snapping, name tables, trim UI scale, HDR10+ scalings
tools/build-libdovi.sh   rebuilds the bundled libdovi.so, see UPDATING.md
tests/                   stdlib unittest, run with: python3 -m unittest discover tests
```

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
- Malformed or corrupted DV RPU payloads can, in rare cases, trigger a
  panic inside libdovi (Rust, with no `catch_unwind` across its C API)
  that aborts the host process. This is uncatchable at the Python layer,
  so `parse_sidedata`'s never-raises guarantee does not cover it. The
  exposure is shared with CoreELEC's own video player core, which feeds
  the same bytes to the same library during DV playback. The real remedy
  is an upstream fix, panic-catching in libdovi's C API, tracked for a
  future update.

## Credits and licensing

This addon is licensed **GPL-2.0-or-later** (see `addon.xml`), the CoreELEC/
Kodi addon convention.

`lib/sidedata/native.py` loads a `libdovi.so` build via `ctypes` at
runtime; it declares ctypes structs mirroring `libdovi-3.3.1`'s public C
header (`libdovi/rpu_parser.h`) so it can call into that build directly.
This addon bundles an unmodified aarch64 build of `libdovi-3.3.1`
(`lib/sidedata/native_libs/aarch64/libdovi.so`, MIT License, quietvoid,
https://github.com/quietvoid/dovi_tool) and loads it in place of a
platform-provided one on that architecture. See `NOTICE.md` and
`UPDATING.md`. The MIT license text and copyright notice are reproduced in
`LICENSES/dovi_tool.MIT`.

`lib/sidedata/avutil.py` loads CoreELEC's own `libavutil.so` (part of
FFmpeg, LGPL-2.1-or-later) via `ctypes` at runtime and calls
`av_dynamic_hdr_plus_from_t35` directly; it declares ctypes structs
mirroring `libavutil/hdr_dynamic_metadata.h` from FFmpeg 8.1.2, the version
CoreELEC 22 ships. No FFmpeg code is vendored or linked, and nothing is
distributed with this addon for this path. See `NOTICE.md`.

`rpu['header']['el_type']` (MEL/FEL) is read directly from libdovi's own
`DoviRpuDataHeader.el_type` field.

Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10
primaries name table, the L11 content-type and whitepoint tables, the L2/L8
trim UI-scale inversion, and the HDR10+ raw-code-to-nits/percent scalings)
are ported from `AMLFrameMetadata.h`, the device-tested CoreELEC reference
implementation this module's field names and scalings mirror.
