<img src="resources/icon.png" alt="Sidedata Module" width="128" height="128">

# script.module.sidedata

A CoreELEC addon that parses the raw Dolby Vision and HDR sidedata CoreELEC's Amlogic video player publishes through the `player.process(video.sidedata)` infolabel, and returns it as a plain dict. Needs CoreELEC 22 on an Amlogic device, not stock Kodi.

## From an addon

Declare the dependency in your own `addon.xml`:

```xml
<import addon="script.module.sidedata" version="1.6.0"/>
```

That version is a minimum per Kodi's `<import>` semantics. CoreELEC's build appends a fourth component, so a module reporting `1.6.0.0` still satisfies an import of `1.6.0`. Import the three-component version.

The module registers as an `xbmc.python.module` extension point, so `import sidedata` works once declared:

```python
import sidedata

label = xbmc.getInfoLabel('player.process(video.sidedata)')
if label != last_label:
    last_label = label
    result = sidedata.parse_sidedata(label)
    if result['rpu'] and result['rpu']['l1']:
        print(result['rpu']['l1']['max_nits'])
```

`parse_sidedata` never raises. Missing or empty input, an unavailable engine, or a payload that fails to parse each degrade only that section to `None` rather than failing the whole call. The result has seven keys (`flags`, `structure`, `config`, `rpu`, `hdr10plus`, `mdcv`, `cll`), each `None` when absent or unparseable except `flags`, which is `[]`. See [FIELDS.md](FIELDS.md) for the field reference, with a changelog per release. The one opt-out is `include_mapping=False`, which skips the composer `rpu.data_mapping` subtree ([RPU-DATA-MAPPING.md](RPU-DATA-MAPPING.md)) and leaves it `None`.

`parse_sidedata` does no caching of its own, so it decodes the JSON and reruns the native RPU and HDR10+ engines on every call. If you poll `player.process(video.sidedata)` on a tick like the example above, keeping `last_label` around and skipping the call when the label has not changed avoids paying that cost on every poll. It is the same guard the bundled service uses on its own poll loop.

## From a skin

A small service publishes every parsed field except the `rpu.data_mapping` subtree as a Home window property, prefixed `sidedata.`:

```xml
$INFO[Window(Home).Property(sidedata.rpu.profile)]
```

See FIELDS.md's ["Window properties"](FIELDS.md#window-properties) section for the complete reference: the naming rules for lists, trims and coordinate pairs, the derived properties (counts, first/last aliases, presence flags), and further skin examples.

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

libdovi's `dovi_rpu_get_data_mapping` (the composer/reshaping curves and NLQ data, what most players call the composer metadata) is published as `rpu.data_mapping`. See [RPU-DATA-MAPPING.md](RPU-DATA-MAPPING.md) for its field reference. Callers who don't need it pass `include_mapping=False` to skip the extra native call. The bundled service does exactly that, so `sidedata.rpu.data_mapping.*` never appears as a Home window property.

## Known limitations

- Two blocks of the same level can resolve to the same nits value, since distinct raw targets snap to the same preset bucket (dovi_tool's own info output rounds the same way and prints such duplicates too). Both appear in their list. Callers keying by nits get list order, RPU order for ties, not uniqueness.
- HDR10+ exposes processing window 0 only. `num_windows` is still reported so a caller can detect the multi-window case, which has not been seen in practice.

## License

GPL-2.0-or-later, full text in `LICENSE.txt`.

The bundled aarch64 `libdovi-3.4.0` build is quietvoid's, MIT licensed, with its license text in `LICENSES/dovi_tool.MIT`. `libavutil` (part of FFmpeg, LGPL-2.1-or-later) is CoreELEC's own copy, loaded at runtime, with no FFmpeg code vendored or linked. See `NOTICE.md` for the full third-party notices.
