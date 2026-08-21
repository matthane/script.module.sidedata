# RPU data mapping reference

`rpu.data_mapping` is what most players and tools call the composer or reshaping metadata: the per-component curves and dequantization data a Dolby Vision decoder applies to the base layer (and, for dual-layer profiles, the enhancement layer residual) to reconstruct the intended picture. This document is the field-by-field reference for that subtree, a companion to [FIELDS.md](FIELDS.md). See FIELDS.md's own "rpu.data_mapping" entry for how the subtree is gated by `include_mapping`.

The values here come straight from libdovi's `DoviRpuDataMapping` struct (`dovi_rpu_get_data_mapping`), same approach as the rest of the RPU: raw code values, no second reference implementation to check a derived scaling against, except where the ST/SMPTE RPU syntax itself defines the arithmetic (the coefficient combination below).

## Contents

- [rpu.data_mapping](#rpudata_mapping)
- [rpu.data_mapping.curves\[\]](#rpudata_mappingcurves)
  - [.polynomial](#polynomial)
  - [.mmr](#mmr)
- [rpu.data_mapping.nlq](#rpudata_mappingnlq)
- [Reading the pivots](#reading-the-pivots)
- [Combining integer and fractional coefficients](#combining-integer-and-fractional-coefficients)
- [Polynomial vs MMR](#polynomial-vs-mmr)
- [NLQ and dual-layer profiles](#nlq-and-dual-layer-profiles)

## rpu.data_mapping

| Field | Type | Meaning |
| --- | --- | --- |
| `vdr_rpu_id` | int | VDR RPU id this mapping data belongs to. |
| `mapping_color_space` | int | raw mapping color space code. |
| `mapping_chroma_format_idc` | int | raw mapping chroma format code. |
| `num_x_partitions` | int | horizontal tile partition count, `num_x_partitions_minus1 + 1`. |
| `num_y_partitions` | int | vertical tile partition count, `num_y_partitions_minus1 + 1`. |
| `curves` | list of 3 dict | the per-component reshaping curves, in libdovi's `curves[3]` order: index 0 is luma (Y), 1 and 2 are chroma (Cb, Cr). See "rpu.data_mapping.curves[]" below. |
| `nlq_method_idc` | int or None | raw NLQ method code. `None` when libdovi's `-1` sentinel marks it not present, i.e. every RPU that isn't a dual-layer profile (4 or 7). |
| `nlq_num_pivots` | int or None | NLQ pivot count, `nlq_num_pivots_minus2 + 2`. `None` under the same condition as `nlq_method_idc`. |
| `nlq_pred_pivot_value` | list of int or None | NLQ prediction pivot codewords. `None` when libdovi reports a zero-length buffer, i.e. not present. |
| `nlq` | dict or None | per-component NLQ dequantization data. `None` for single-layer RPUs. See "rpu.data_mapping.nlq" below. |

## rpu.data_mapping.curves[]

Each of the three entries in `curves` has this shape.

| Field | Type | Meaning |
| --- | --- | --- |
| `num_pivots` | int | pivot count for this component, `num_pivots_minus2 + 2`. Always at least 2, so there's always at least one segment. |
| `pivots` | list of int | codeword values, 0-1023 (10 bit), that divide the input range into `num_pivots - 1` segments. See "Reading the pivots" below. |
| `mapping_idc` | int | `0` for piecewise polynomial, `1` for MMR. See "Polynomial vs MMR" below. |
| `polynomial` | dict or None | present when `mapping_idc` is `0`, else `None`. See ".polynomial" below. |
| `mmr` | dict or None | present when `mapping_idc` is `1`, else `None`. See ".mmr" below. |

### .polynomial

One entry per segment (`num_pivots - 1` of them) in every list below, segments in pivot order.

| Field | Type | Meaning |
| --- | --- | --- |
| `poly_order` | list of int | polynomial order for each segment, `poly_order_minus1 + 1`. A segment's coefficient lists below hold `poly_order + 1` values. |
| `linear_interp_flag` | list of bool | per segment, true forces linear interpolation across that segment regardless of `poly_order`. |
| `poly_coef_int` | list of list of int | per segment, the integer part of each coefficient, lowest order term first. |
| `poly_coef` | list of list of int | per segment, the fractional part of each coefficient, same shape as `poly_coef_int`. See "Combining integer and fractional coefficients" below. |

### .mmr

One entry per segment in `mmr_order`, `mmr_constant_int` and `mmr_constant`. `mmr_coef_int`/`mmr_coef` add a middle dimension: per segment, one row per order level from 1 up to that segment's `mmr_order`.

| Field | Type | Meaning |
| --- | --- | --- |
| `mmr_order` | list of int | MMR order for each segment, `mmr_order_minus1 + 1`. |
| `mmr_constant_int` | list of int | per segment, the integer part of the curve's constant term. |
| `mmr_constant` | list of int | per segment, the fractional part of the constant term. |
| `mmr_coef_int` | list of list of list of int | per segment, per order row, the integer part of that row's cross-component coefficients. |
| `mmr_coef` | list of list of list of int | per segment, per order row, the fractional part, same shape as `mmr_coef_int`. |

The row length within `mmr_coef_int`/`mmr_coef` grows with its order level, since MMR (multivariate multiple regression) adds cross-component product terms (Y, Cb, Cr and their products) as order increases. This module doesn't interpret those terms further. It publishes the raw arrays libdovi returns.

## rpu.data_mapping.nlq

Present only when `rpu.data_mapping.nlq_method_idc` is not `None`, i.e. dual-layer profiles 4 and 7. Every field is a 3 element list, one value per component (Y, Cb, Cr), straight from libdovi's `DoviRpuDataNlq`.

| Field | Type | Meaning |
| --- | --- | --- |
| `nlq_offset` | list of 3 int | NLQ offset per component. |
| `vdr_in_max_int` | list of 3 int | integer part of the VDR input maximum per component. |
| `vdr_in_max` | list of 3 int | fractional part of the VDR input maximum per component. |
| `linear_deadzone_slope_int` | list of 3 int | integer part of the linear deadzone slope per component. |
| `linear_deadzone_slope` | list of 3 int | fractional part of the linear deadzone slope per component. |
| `linear_deadzone_threshold_int` | list of 3 int | integer part of the linear deadzone threshold per component. |
| `linear_deadzone_threshold` | list of 3 int | fractional part of the linear deadzone threshold per component. |

## Reading the pivots

A curve's `pivots` list segments the 10 bit (0-1023) input codeword range for that component. `num_pivots - 1` segments run between consecutive pivot values, each with its own reshaping curve (its own polynomial or MMR coefficients). In every fixture this module carries, `pivots` starts at 0 and ends at 1023, covering the full range with no gaps.

## Combining integer and fractional coefficients

Every coefficient in `data_mapping` is split into an integer part and a fractional part, published exactly as libdovi returns them rather than combined into a float in code. Combine them yourself with `rpu.header.coefficient_log2_denom`:

```
value = int_part + frac_part / (2 ** coefficient_log2_denom)
```

This applies uniformly: `poly_coef_int`/`poly_coef` pairs, `mmr_constant_int`/`mmr_constant` pairs, `mmr_coef_int`/`mmr_coef` pairs, and the NLQ pairs (`vdr_in_max_int`/`vdr_in_max`, `linear_deadzone_slope_int`/`linear_deadzone_slope`, `linear_deadzone_threshold_int`/`linear_deadzone_threshold`) all combine the same way.

## Polynomial vs MMR

`mapping_idc` is consistent per component across a given RPU: the luma curve (`curves[0]`) is always `0` (piecewise polynomial), and the chroma curves (`curves[1]`, `curves[2]`) are `1` (MMR) whenever chroma reshaping is actually applied. A chroma curve with no reshaping to do (common in practice) still often reports `mapping_idc` `0` with a trivial single-segment linear polynomial, rather than an MMR curve, since a no-op curve is cheaper to signal that way.

## NLQ and dual-layer profiles

NLQ (non-linear dequantization) reconstructs the enhancement layer residual for dual-layer profiles 4 and 7, where the base layer and enhancement layer travel as separate coded pictures. Single-layer profiles (5, 8, and most streams encoded today) never carry it: `nlq_method_idc`, `nlq_num_pivots`, `nlq_pred_pivot_value` and `nlq` are all `None`.
