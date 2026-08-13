<img src="resources/icon.png" alt="" width="128" align="right">

# script.module.sidedata

A CoreELEC addon. It parses the raw Dolby Vision and HDR sidedata that
CoreELEC's Amlogic video player publishes through the
`player.process(video.sidedata)` infolabel and returns it as a plain dict.

That infolabel is CoreELEC-specific, so this needs CoreELEC 22 on an Amlogic
device. Stock Kodi is not supported. Nothing beyond Kodi's bundled Python is
required.

## Usage

Declare the dependency in your own `addon.xml`:

```xml
<import addon="script.module.sidedata" version="1.2.2"/>
```

That version is a minimum, per Kodi's `<import>` semantics. CoreELEC's
build appends a fourth component of its own, so a module showing as
`1.2.2.0` in Kodi satisfies an import of `1.2.2`. Import the
three-component version. The module registers as an `xbmc.python.module`
extension point, so `import sidedata` then works:

```python
import sidedata

result = sidedata.parse_sidedata(xbmc.getInfoLabel('player.process(video.sidedata)'))

if result['rpu'] and result['rpu']['l1']:
    print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises. Missing or empty input returns the all-None
shape below, and a payload that fails to parse degrades only its own section
to `None` rather than the whole call. A section whose parsing engine is not
available on the running platform is `None` the same way.

## Result

A dict with seven keys: `flags`, `structure`, `config`, `rpu`, `hdr10plus`,
`mdcv`, `cll`. Each one is `None` when its payload is absent or unparseable,
except `flags`, which is a list and is `[]` instead.

[FIELDS.md](FIELDS.md) is the field-by-field reference, pinned per release.
Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10
primaries table, L11 content-type and whitepoint tables, the L2/L8 trim
UI-scale inversion, the HDR10+ raw-code scalings) follow dovi_tool's output
conventions and FFmpeg's field semantics. The test suite holds the parsed
output to those tools' values on real streams.

## Input

The infolabel returns a JSON object. Each present payload is a key holding
base64-encoded bytes, except `flags` and `structure`, which are plain text.

| key | contents |
|---|---|
| `dovi.config` | 24-byte dvcC/dvvC configuration record |
| `dovi.rpu` | HEVC: the escaped NAL unit 62 verbatim (`7C 01` header + payload). AV1: the Dolby Vision ITU-T T.35 OBU payload from the country code |
| `hdr10plus` | ST 2094-40 ITU-T T.35 payload from the country code (`B5 00 3C 00 01 04`), unescaped |
| `mdcv` | mastering display colour volume SEI payload, 24 bytes |
| `cll` | content light level SEI payload, 4 bytes |
| `flags` | space-separated tokens from `{converted, rpu-removed, hdr10plus-removed, l5-zeroed}` |
| `structure` | `st-dl` or `dt-dl` for a dual-layer Dolby Vision stream, absent for single-layer |

## Under the hood

No bitstream parsing happens in Python. Both engines are real libraries
called through `ctypes`, and this package is dispatch, unit conversion, and
the fixed-layout unpacks for dvcC/dvvC, MDCV and CLL.

- **Dolby Vision RPU** uses
  [quietvoid's `libdovi`](https://github.com/quietvoid/dovi_tool), bundled
  for aarch64. The loader tries `SIDEDATA_LIBDOVI_PATH`, then the bundled
  build, then a platform-provided `libdovi.so`, by soname and then through
  `find_library`. There is no pure-Python fallback, so `result['rpu']` is
  `None` if none of those resolve.
- **HDR10+** uses FFmpeg's `libavutil`, always CoreELEC's own copy, borrowed
  at runtime and never bundled. Because the copy is whatever CoreELEC ships,
  `avutil.py` checks `avutil_version()` on load and refuses a major it does
  not know (60 or 61, CoreELEC 22's ffmpeg). A struct layout mismatch is
  silent memory corruption rather than an error, which is also why both
  bindings mirror a fixed upstream build. See `.github/UPDATING.md` before
  moving either pin.

## Known limitations

- Two L2 or L8/L10 blocks that resolve to the same nits value (preset
  indices 24 and 25 both map to 300 nits, for example) both appear in their
  list. Callers keying by nits should expect list order, RPU order for ties,
  rather than uniqueness.
- HDR10+ exposes processing window 0 only. `num_windows` is still reported
  so a caller can detect the multi-window case, which has not been seen in
  practice.
- Individual L8 secondary 6-vector saturation and hue trims (block length
  19/25) are not exposed by libdovi's own `DoviExtMetadataBlockLevel8`.
- A malformed DV RPU can in rare cases trigger a panic inside libdovi
  (Rust, with no `catch_unwind` across its C API) that aborts the host
  process. That is uncatchable from Python, so the never-raises guarantee
  does not cover it. CoreELEC's own player feeds the same bytes to the same
  library during playback, so this is not exposure the addon adds. An
  upstream fix is tracked for a future update.

## License

GPL-2.0-or-later, full text in `LICENSE.txt`.

The bundled aarch64 `libdovi-3.3.1` build is quietvoid's, MIT licensed, with
its license text in `LICENSES/dovi_tool.MIT`. `libavutil` (part of FFmpeg,
LGPL-2.1-or-later) is CoreELEC's own copy, loaded at runtime, with no
FFmpeg code vendored or linked. See
`NOTICE.md` for the full third-party notices.
