# Field reference

This document is the field-by-field reference for the dict `parse_sidedata()` returns, as of 1.4.2. The [Changelog](#changelog) at the end describes what each release changed. Every field documented below is also published live as a Home window property, prefixed `sidedata.` and named after its path in this document. See README.md's "From a skin" section for the exact naming rules for lists, trims and coordinate pairs.

Value scalings and name tables (PQ-to-nits, target-nits snapping, the L9/L10 primaries table, L11 content-type and whitepoint tables, the L2/L8 trim UI-scale inversion, the HDR10+ raw-code scalings) follow dovi_tool's output conventions and FFmpeg's field semantics. The test suite holds the parsed output to those tools' values on real streams.

## Contents

- [Top level](#top-level)
- [config](#config)
- [rpu](#rpu)
  - [rpu.header](#rpuheader)
  - [rpu.l1](#rpul1)
  - [rpu.l2](#rpul2)
  - [rpu.l3](#rpul3)
  - [rpu.l5](#rpul5)
  - [rpu.l6](#rpul6)
  - [rpu.l8](#rpul8)
  - [rpu.l9](#rpul9)
  - [rpu.l10](#rpul10)
  - [rpu.l11](#rpul11)
- [hdr10plus](#hdr10plus)
- [mdcv](#mdcv)
- [cll](#cll)
- [Changelog](#changelog)

## Top level

Each of `config`, `rpu`, `hdr10plus`, `mdcv`, `cll` is `None` when its sidedata key is absent from the input, the payload fails to decode or parse, or, for `rpu` and `hdr10plus`, the parsing engine (libdovi, libavutil) isn't available on the running platform. `structure` is `None` when its key is absent, i.e. for single-layer streams. `flags` is `[]` rather than `None` under the equivalent absent/empty case.

| Field | Type | Meaning |
| --- | --- | --- |
| `flags` | list of str | the tokens from the label's `flags` key, a JSON array of strings, passed through unchanged and not interpreted. Vocabulary is `converted`, `rpu-removed`, `hdr10plus-removed`, `l5-zeroed`. |
| `structure` | str or None | the label's plain-text `structure` key, passed through unchanged. `st-dl` when a dual-layer Dolby Vision stream carries its enhancement layer in the same track, `dt-dl` when a second track carries it. |
| `config` | dict or None | parsed `dovi.config` (dvcC/dvvC configuration record). |
| `rpu` | dict or None | parsed `dovi.rpu` (Dolby Vision RPU). |
| `hdr10plus` | dict or None | parsed `hdr10plus` (ST 2094-40 T.35 payload). |
| `mdcv` | dict or None | parsed `mdcv` (mastering display colour volume SEI). |
| `cll` | dict or None | parsed `cll` (content light level SEI). |

## config

| Field | Type | Meaning |
| --- | --- | --- |
| `version_major` | int | dvcC/dvvC record version major. |
| `version_minor` | int | dvcC/dvvC record version minor. |
| `profile` | int | Dolby Vision profile number. |
| `level` | int | Dolby Vision level number. |
| `rpu_present` | bool | RPU present flag. |
| `el_present` | bool | enhancement layer present flag. |
| `bl_present` | bool | base layer present flag. |
| `compat_id` | int | DV profile compatibility id. |
| `md_compression` | int | metadata compression method id. |

## rpu

Direct keys of the `rpu` dict. `header` and the `l1`-`l11` keys are broken out in their own sections below.

| Field | Type | Meaning |
| --- | --- | --- |
| `profile` | int | guessed Dolby Vision profile (0, 4, 5, 7 or 8), from libdovi's `guessed_profile`. |
| `header` | dict | see "rpu.header" below. |
| `compressed` | bool | true when `dv_md_compression` is active on the VDR DM data. False, with `source` left `None`, when there is no VDR DM data at all. |
| `cm_version` | '2.9' or '4.0' or None | `'4.0'` when the RPU carries an L254 block (dovi_tool's signal for CM v4.0 metadata), `'2.9'` when it carries another known DM metadata block without L254, `None` when neither is present. |
| `source` | dict or None | source PQ range. `None` when `compressed` is true or there is no VDR DM data. |
| `source.min_pq` | int | source minimum PQ code, 0-4095. |
| `source.min_nits` | float | `source.min_pq` converted to nits via the ST 2084 EOTF. |
| `source.max_pq` | int | source maximum PQ code, 0-4095. |
| `source.max_nits` | float | `source.max_pq` converted to nits via the ST 2084 EOTF. |
| `l1` | dict or None | see "rpu.l1" below. |
| `l2` | list | see "rpu.l2" below. |
| `l3` | dict or None | see "rpu.l3" below. |
| `l5` | dict or None | see "rpu.l5" below. |
| `l6` | dict or None | see "rpu.l6" below. |
| `l8` | list | see "rpu.l8" below. |
| `l9` | dict or None | see "rpu.l9" below. |
| `l10` | list | see "rpu.l10" below. |
| `l11` | dict or None | see "rpu.l11" below. |

### rpu.header

`rpu.header` is always a dict once `rpu` itself is non-`None`. libdovi returns a header for any RPU it can parse at all.

| Field | Type | Meaning |
| --- | --- | --- |
| `rpu_type` | int | RPU type, from `DoviRpuDataHeader.rpu_type`. |
| `rpu_format` | int | RPU format. |
| `vdr_rpu_profile` | int | VDR RPU profile id. |
| `vdr_rpu_level` | int | VDR RPU level id. |
| `bl_bit_depth` | int or None | base layer bit depth, `8 + bl_bit_depth_minus8`. `None` when `vdr_seq_info_present_flag` is false. |
| `el_bit_depth` | int or None | enhancement layer bit depth, `8 + el_bit_depth_minus8`. `None` under the same condition as `bl_bit_depth`. |
| `vdr_bit_depth` | int or None | VDR bit depth, `8 + vdr_bit_depth_minus8`. Meaningful as content depth only when a FEL residual is present. `None` under the same condition as `bl_bit_depth`. |
| `el_spatial_resampling_filter_flag` | bool | enhancement layer spatial resampling filter flag. |
| `disable_residual_flag` | bool | true disables the enhancement layer residual. |
| `el_type` | 'MEL' or 'FEL' or None | read straight off libdovi's own `DoviRpuDataHeader.el_type`. `None` when there is no enhancement layer, e.g. profile 8. |

### rpu.l1

Present when the RPU carries an L1 (min/max/avg content light) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `min_pq` | int | minimum PQ code, 0-4095. |
| `min_nits` | float | `min_pq` converted to nits. |
| `max_pq` | int | maximum PQ code, 0-4095. |
| `max_nits` | float | `max_pq` converted to nits. |
| `avg_pq` | int | average PQ code, 0-4095. |
| `avg_nits` | float | `avg_pq` converted to nits. |

### rpu.l2

List of trim passes, sorted by `nits`. `[]` when the RPU carries no L2 blocks.

| Field | Type | Meaning |
| --- | --- | --- |
| `nits` | int | target display nits. `target_max_pq` decoded via the ST 2084 EOTF and snapped to the nearest standard target (within 4% or 10 nits, whichever is larger). |
| `slope` | int | raw trim slope code, 12 bit, 2048 is neutral. |
| `offset` | int | raw trim offset code, 12 bit, 2048 is neutral. |
| `power` | int | raw trim power code, 12 bit, 2048 is neutral. |
| `chromaweight` | int | raw trim chroma weight code, 12 bit, 2048 is neutral. |
| `saturation` | int | raw trim saturation gain code, 12 bit, 2048 is neutral. |
| `tonedetail` | int or None | raw `ms_weight` code. `None` when the block's -1 sentinel marks tone detail disabled. |
| `ui.gain` | float | Dolby UI gain, derived from `slope` and `offset`. |
| `ui.lift` | float or None | Dolby UI lift. `None` at the `gain == -2.0` singularity where lift is undefined. |
| `ui.gamma` | float | Dolby UI gamma, derived from `power`. |
| `ui.chromaweight` | float | `chromaweight` rescaled to the -1..1 UI range. |
| `ui.saturation` | float | `saturation` rescaled to the -1..1 UI range. |
| `ui.tonedetail` | float or None | `tonedetail` rescaled to the -1..1 UI range. `None` under the same condition as `tonedetail`. |

### rpu.l3

Present when the RPU carries an L3 (PQ offset) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `min_pq_offset` | int | minimum PQ offset code. |
| `max_pq_offset` | int | maximum PQ offset code. |
| `avg_pq_offset` | int | average PQ offset code. |

### rpu.l5

Present when the RPU carries an L5 (active area) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `left` | int | left active area offset, pixels. |
| `right` | int | right active area offset, pixels. |
| `top` | int | top active area offset, pixels. |
| `bottom` | int | bottom active area offset, pixels. |

### rpu.l6

Present when the RPU carries an L6 (legacy MaxCLL/MaxFALL) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `max_cll` | int | maximum content light level, nits. |
| `max_fall` | int | maximum frame average light level, nits. |
| `min_lum_raw` | int | raw minimum display mastering luminance code. |
| `min_lum_nits` | float | `min_lum_raw` scaled by 0.0001 cd/m2 per unit. |
| `max_lum_raw` | int | raw maximum display mastering luminance code. |
| `max_lum_nits` | int | same value as `max_lum_raw`. The L6 code is already in cd/m2, unlike `min_lum_raw`. |

### rpu.l8

List of trim passes, sorted by `nits`. `[]` when the RPU carries no L8 blocks, or none resolve to a known target. `target_display_index` is resolved against `rpu.l10` first, falling back to a fixed preset table. Entries whose index resolves to neither are dropped.

| Field | Type | Meaning |
| --- | --- | --- |
| `nits` | int | resolved target display nits. |
| `target_display_index` | int | the L8 block's target display index. |
| `slope` | int | raw trim slope code, 12 bit, 2048 is neutral. |
| `offset` | int | raw trim offset code, 12 bit, 2048 is neutral. |
| `power` | int | raw trim power code, 12 bit, 2048 is neutral. |
| `chromaweight` | int | raw trim chroma weight code, 12 bit, 2048 is neutral. |
| `saturation` | int | raw trim saturation gain code, 12 bit, 2048 is neutral. |
| `tonedetail` | int | raw `ms_weight` code. Unsigned, unlike `rpu.l2`'s `tonedetail`. L8 has no disabled sentinel. |
| `ui.gain` | float | same derivation as `rpu.l2`'s `ui.gain`. |
| `ui.lift` | float or None | same derivation as `rpu.l2`'s `ui.lift`. |
| `ui.gamma` | float | same derivation as `rpu.l2`'s `ui.gamma`. |
| `ui.chromaweight` | float | same derivation as `rpu.l2`'s `ui.chromaweight`. |
| `ui.saturation` | float | same derivation as `rpu.l2`'s `ui.saturation`. |
| `ui.tonedetail` | float | same derivation as `rpu.l2`'s `ui.tonedetail`, always present since L8 has no disabled sentinel. |
| `mid_contrast` | int | target mid contrast code. Present only when the block's serialized length is greater than 10. |
| `clip_trim` | int | clip trim code. Present only when the block's serialized length is greater than 12. |

### rpu.l9

Present when the RPU carries an L9 (source colour primaries) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `index` | int | source primary index. |
| `name` | str | primary name. See "Primaries name table" below. |
| `has_coords` | bool | true when the block carries explicit CIE coordinates (serialized length >= 17). |
| `coords.red` | tuple of int | raw 16 bit CIE x, y for red. Present only when `has_coords`. |
| `coords.green` | tuple of int | raw 16 bit CIE x, y for green. Present only when `has_coords`. |
| `coords.blue` | tuple of int | raw 16 bit CIE x, y for blue. Present only when `has_coords`. |
| `coords.white` | tuple of int | raw 16 bit CIE x, y for white. Present only when `has_coords`. |

### rpu.l10

List of target display definitions, sorted by (`nits`, `primary_index`). `[]` when the RPU carries no L10 blocks, or none resolve to a nonzero nits value.

| Field | Type | Meaning |
| --- | --- | --- |
| `target_display_index` | int | the block's target display index. |
| `nits` | int | `target_max_pq` decoded via the ST 2084 EOTF and snapped to the nearest standard target, same snapping as `rpu.l2`'s `nits`. |
| `target_max_pq` | int | raw target maximum PQ code. |
| `target_min_pq` | int | raw target minimum PQ code. |
| `primary_index` | int | target primary index. |
| `primary_name` | str | same name resolution as `rpu.l9`'s `name`. See "Primaries name table" below. |
| `has_coords` | bool | true when the block carries explicit CIE coordinates (serialized length >= 21). |
| `coords.red` | tuple of int | raw 16 bit CIE x, y for red. Present only when `has_coords`. |
| `coords.green` | tuple of int | raw 16 bit CIE x, y for green. Present only when `has_coords`. |
| `coords.blue` | tuple of int | raw 16 bit CIE x, y for blue. Present only when `has_coords`. |
| `coords.white` | tuple of int | raw 16 bit CIE x, y for white. Present only when `has_coords`. |

Primaries name table, used by `rpu.l9`'s `name` and `rpu.l10`'s `primary_name`. Index 255, or any index paired with `has_coords`, renders as `custom`. Any other unnamed index renders as its own decimal string.

| Index | Name |
| --- | --- |
| 0 | `DCI-P3 D65` |
| 1 | `BT.709` |
| 2 | `BT.2020` |
| 3 | `SMPTE-C` |
| 4 | `BT.601` |
| 5 | `DCI-P3` |
| 6 | `ACES` |
| 7 | `S-Gamut` |
| 8 | `S-Gamut-3.Cine` |

### rpu.l11

Present when the RPU carries an L11 (content type/whitepoint) metadata block, else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `content_type` | int | raw content type code. |
| `content_type_name` | str | content type name. See "Content type name table" below. |
| `whitepoint` | int | raw whitepoint code. |
| `whitepoint_kelvin` | int | `6504 + 375 * whitepoint`. |
| `whitepoint_name` | str | `'6504K (D65)'` at code 0, else `'{whitepoint_kelvin}K'`. |
| `reference_mode` | bool | reference mode flag. |

Content type name table, used by `content_type_name`. Any other code renders as its own decimal string.

| Code | Name |
| --- | --- |
| 0 | `Default` |
| 1 | `Movies` |
| 2 | `Game` |
| 3 | `Sport` |
| 4 | `User Generated Content` |

## hdr10plus

Present when the sidedata carries an `hdr10plus` payload and a version-matched libavutil parses it, else `None`. Only processing window 0 is exposed, even when `num_windows` is greater than 1.

| Field | Type | Meaning |
| --- | --- | --- |
| `application_version` | int | ST 2094-40 application version. |
| `num_windows` | int | processing window count as reported by libavutil. Real content is essentially always 1. |
| `targeted_system_display_maximum_luminance` | int | targeted system display max luminance, nits. The T.35 code is already in nits. |
| `maxscl` | list of 3 float | per channel maximum RGB values, nits (raw code / 10). |
| `average_maxrgb` | float | average maxRGB, nits (raw code / 10). |
| `distribution` | list of dict | maxRGB percentile distribution, one entry per reported percentile. |
| `distribution[].percentage` | int | percentile, 0-100. |
| `distribution[].nits` | float | maxRGB value at that percentile, nits (raw code / 10). |
| `fraction_bright_pixels` | float | fraction of bright pixels, percent (raw code / 10). |
| `profile` | 'A' or 'B' | from the tone mapping flag. `'B'` when a Bezier tone curve is present. |
| `knee_point_x` | float | knee point x, 0..1 (raw code / 4095). |
| `knee_point_y` | float | knee point y, 0..1 (raw code / 4095). |
| `bezier_anchors` | list of int | raw 10 bit Bezier curve anchor codes. Empty when `profile` is `'A'`. |

## mdcv

Present when the sidedata carries a well formed `mdcv` payload (at least 24 bytes), else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `primaries` | dict or None | red/green/blue chromaticity coordinates. `None` when all three are zero (unknown). |
| `primaries.red` | tuple of float | CIE x, y, each raw code / 50000.0. Present only when `primaries` is not `None`. |
| `primaries.green` | tuple of float | CIE x, y, each raw code / 50000.0. Present only when `primaries` is not `None`. |
| `primaries.blue` | tuple of float | CIE x, y, each raw code / 50000.0. Present only when `primaries` is not `None`. |
| `primaries.name` | str or None | the well known primaries set name (DCI-P3 D65, BT.709, BT.2020, SMPTE-C, BT.601, DCI-P3, ACES, S-Gamut or S-Gamut-3.Cine) when the decoded `primaries` and `white_point` coordinates match that set's CIE chromaticities within about 0.001 per coordinate, well above the SEI's 1/50000 quantization step. `None` when no set matches. Present only when `primaries` is not `None`. |
| `white_point` | tuple of float | CIE x, y, each raw code / 50000.0. |
| `max_luminance` | float | nits, raw code / 10000.0. |
| `min_luminance` | float | nits, raw code / 10000.0. |

## cll

Present when the sidedata carries a well formed `cll` payload (at least 4 bytes), else `None`.

| Field | Type | Meaning |
| --- | --- | --- |
| `max_cll` | int | maximum content light level, nits. |
| `max_fall` | int | maximum frame average light level, nits. |

## Changelog

### 1.4.2

Documentation cleanup. No code changes.

### 1.4.0

The raw `flags` key in the sidedata JSON is now a JSON array of strings instead of a space-separated string. `parse_sidedata()` accepts the new form. The `flags` field in its returned dict is unchanged, still a list of str.

### 1.3.0

Initial release. Provides the `sidedata` parser module (`parse_sidedata()`), which decodes CoreELEC's raw DV/HDR sidedata JSON into `flags`, `structure`, `config`, `rpu`, `hdr10plus`, `mdcv` and `cll`, and a background window property service (`service.py`) that publishes every field above, plus derived properties (entry counts for `rpu.l2`, `rpu.l8`, `rpu.l10` and the HDR10+ distribution, presence flags for the whole payload and for Dolby Vision, HDR10+, MDCV and CLL individually, and first/last trim aliases for `rpu.l2` and `rpu.l8`), as Home window properties for skins and other non-python consumers.
