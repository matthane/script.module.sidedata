<img src="resources/icon.png" alt="Sidedata Module" width="128" height="128">

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

## Skins and window properties

Alongside the python module, this addon runs a small service that publishes
every parsed field as a Home window property, so a skin or any other
non-python consumer can read the same data without touching python at all.
Property names are prefixed `sidedata.` and mirror the field paths in
FIELDS.md, so `rpu.header.el_type` becomes `sidedata.rpu.header.el_type`
and `rpu.l6.max_cll` becomes `sidedata.rpu.l6.max_cll`. Skins read a
property like this:

```xml
$INFO[Window(Home).Property(sidedata.rpu.profile)]
```

A few sections need their own naming rule because they hold lists rather
than a single dict. `flags`, `hdr10plus.maxscl` and `hdr10plus.bezier_anchors`
each publish as one space separated property. Coordinate pairs such as
`mdcv.primaries.red` or `rpu.l9.coords.white` split into `.x` and `.y`
properties. The L2 and L8 trim passes key by their nits value, so a 600 nit
L2 trim's gain lands at `sidedata.rpu.l2.600.ui.gain`, with
`sidedata.rpu.l2.nits` listing every nits value present so a skin can
enumerate them; L8 works the same way. L10 target displays key by
`target_display_index` instead, since two L10 blocks can share a nits value,
with `sidedata.rpu.l10.indexes` listing the indexes present. HDR10+'s
distribution keys by percentile the same way, `sidedata.hdr10plus.distribution.50`
for the 50th percentile's nits value and
`sidedata.hdr10plus.distribution.percentages` for the percentiles present.

Two blocks in the same section can resolve to the same key. The Known
limitations section below describes how two L2 or L8 trims can snap to the
same nits value, and the same collision handling covers an HDR10+
distribution percentile or an L10 index appearing twice. When it happens
the first block keeps the plain key and every later one gets a dash and an
ordinal appended, so a second 300 nit L2 trim publishes at
`sidedata.rpu.l2.300-2` rather than overwriting the first trim's fields.
The enumeration property for that section, `sidedata.rpu.l2.nits` and its
siblings, lists the exact tokens in the order the blocks appeared, dash
suffixes included, so a skin can walk every one of them by taking each
token as the next path segment.

Booleans publish as `true` or `false`, floats are trimmed of trailing
zeros, and a field that is `None` or a section absent from the current
frame publishes no property at all.

Properties follow the metadata within about a tenth of a second, aligned to
scene cuts, and clear the moment playback stops or the RPU disappears from
the label. No import or dependency declaration is needed for this path; the
service starts on its own once the addon is installed.

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
