<img src="resources/icon.png" alt="Sidedata Module" width="128" height="128">

# script.module.sidedata

A CoreELEC addon that parses the raw Dolby Vision and HDR sidedata CoreELEC's Amlogic video player publishes through the `player.process(video.sidedata)` infolabel, and returns it as a plain dict. Needs CoreELEC 22 on an Amlogic device, not stock Kodi.

## From an addon

Declare the dependency in your own `addon.xml`:

```xml
<import addon="script.module.sidedata" version="1.4.2"/>
```

That version is a minimum per Kodi's `<import>` semantics. CoreELEC's build appends a fourth component, so a module reporting `1.4.2.0` still satisfies an import of `1.4.2`. Import the three-component version.

The module registers as an `xbmc.python.module` extension point, so `import sidedata` works once declared:

```python
import sidedata

result = sidedata.parse_sidedata(xbmc.getInfoLabel('player.process(video.sidedata)'))

if result['rpu'] and result['rpu']['l1']:
    print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises. Missing or empty input, an unavailable engine, or a payload that fails to parse each degrade only that section to `None` rather than failing the whole call. The result has seven keys (`flags`, `structure`, `config`, `rpu`, `hdr10plus`, `mdcv`, `cll`), each `None` when absent or unparseable except `flags`, which is `[]`. See [FIELDS.md](FIELDS.md) for the field reference, with a changelog per release.

## From a skin

A small service publishes every parsed field as a Home window property, prefixed `sidedata.` and mirroring the field paths in FIELDS.md (`rpu.header.el_type` becomes `sidedata.rpu.header.el_type`):

```xml
$INFO[Window(Home).Property(sidedata.rpu.profile)]
```

| rule | example |
|---|---|
| plain field path | `sidedata.rpu.header.el_type` |
| list section (`flags`, `hdr10plus.maxscl`, `hdr10plus.bezier_anchors`), space joined | `sidedata.flags` |
| coordinate pair, splits into `.x`/`.y` | `sidedata.mdcv.primaries.red.x` |
| L2/L8 trim, keyed by nits value. `.l2.nits`/`.l8.nits` enumerate the values present | `sidedata.rpu.l2.600.ui.gain` |
| L10 target display, keyed by `target_display_index` (two blocks can share a nits value). `.l10.indexes` enumerates them | `sidedata.rpu.l10.0.max_pq` |
| HDR10+ distribution, keyed by percentile. `.distribution.percentages` enumerates them | `sidedata.hdr10plus.distribution.50` |
| collision (two blocks resolve to the same key), later ones get a dash and an ordinal | second 300 nit L2 trim: `sidedata.rpu.l2.300-2` |
| derived: entry count for L2, L8, L10 and the HDR10+ distribution | `sidedata.rpu.l2.count` |
| derived: L2/L8 first/last trim by nits, duplicating that entry's keyed fields | `sidedata.rpu.l2.first.ui.gain`, `sidedata.rpu.l2.last.ui.gain` |
| derived: presence flags for the whole payload, Dolby Vision, HDR10+, MDCV and CLL | `sidedata.present`, `sidedata.dovi.present`, `sidedata.hdr10plus.present` |

Each enumeration property lists the exact tokens in the order the blocks appeared, dash suffixes included, so a skin can walk every one by taking each token as the next path segment. Booleans publish as `true` or `false`, floats drop trailing zeros, and a field that's `None` or absent from the current frame publishes no property. Presence flags only ever publish `true`, so a skin reads absence as false with `String.IsEmpty`.

Properties follow the metadata within about a tenth of a second, aligned to scene cuts, and clear when playback stops or the RPU disappears from the label. No import is needed for this path. The service starts on its own once the addon is installed.

## Input

The infolabel returns a JSON object whose payloads are base64-encoded bytes, except `structure`, which is plain text, and `flags`, which is a JSON array of strings.

| key | contents |
|---|---|
| `dovi.config` | 24-byte dvcC/dvvC configuration record |
| `dovi.rpu` | HEVC: the escaped NAL unit 62 verbatim (`7C 01` header + payload). AV1: the Dolby Vision ITU-T T.35 OBU payload from the country code |
| `hdr10plus` | ST 2094-40 ITU-T T.35 payload from the country code (`B5 00 3C 00 01 04`), unescaped |
| `mdcv` | mastering display colour volume SEI payload, 24 bytes |
| `cll` | content light level SEI payload, 4 bytes |
| `flags` | JSON array of tokens from `{converted, rpu-removed, hdr10plus-removed, l5-zeroed}` |
| `structure` | `st-dl` or `dt-dl` for a dual-layer Dolby Vision stream, absent for single-layer |

## Parsing engines

No bitstream parsing happens in Python. Both engines are real libraries called through `ctypes`. This package handles dispatch, unit conversion, and the fixed-layout unpacks for dvcC/dvvC, MDCV and CLL.

- Dolby Vision RPU uses [quietvoid's `libdovi`](https://github.com/quietvoid/dovi_tool), bundled for aarch64. The loader tries `SIDEDATA_LIBDOVI_PATH`, then the bundled build, then a platform `libdovi.so` (by soname, then `find_library`). There is no pure-Python fallback, so `result['rpu']` is `None` if none resolve.
- HDR10+ uses FFmpeg's `libavutil`, borrowed at runtime from CoreELEC's own copy and never bundled. `avutil.py` checks `avutil_version()` on load and refuses an unrecognized major (60 or 61, CoreELEC 22's ffmpeg), since a struct layout mismatch would be silent memory corruption rather than an error. Both bindings mirror a fixed upstream build for that reason. See `.github/UPDATING.md` before moving either pin.

## Known limitations

- Two blocks of the same level can resolve to the same nits value, since distinct raw targets snap to the same preset bucket (dovi_tool's own info output rounds the same way and prints such duplicates too). Both appear in their list. Callers keying by nits get list order, RPU order for ties, not uniqueness.
- HDR10+ exposes processing window 0 only. `num_windows` is still reported so a caller can detect the multi-window case, which has not been seen in practice.
- Individual L8 secondary 6-vector saturation and hue trims (block length 19/25) are not exposed by libdovi's own `DoviExtMetadataBlockLevel8`.

## License

GPL-2.0-or-later, full text in `LICENSE.txt`.

The bundled aarch64 `libdovi-3.3.1` build is quietvoid's, MIT licensed, with its license text in `LICENSES/dovi_tool.MIT`. `libavutil` (part of FFmpeg, LGPL-2.1-or-later) is CoreELEC's own copy, loaded at runtime, with no FFmpeg code vendored or linked. See `NOTICE.md` for the full third-party notices.
