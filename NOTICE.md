# Third-party notices

This addon (script.module.sidedata) is licensed GPL-2.0-or-later as a whole.

The Dolby Vision RPU bitstream layout implemented in `lib/sidedata/rpu.py` was
determined by reading the parser source of **dovi_tool** / the `dolby_vision`
crate by quietvoid (https://github.com/quietvoid/dovi_tool), and this addon's
parser is validated against that tool's own JSON output (`tests/test_rpu.py`).
No code from dovi_tool is vendored or linked; this is an independent
from-scratch Python implementation of the same bitstream layout. dovi_tool's
license is reproduced verbatim, with its copyright notice, in
`LICENSES/dovi_tool.MIT` per the terms of the MIT License.

The HDR10+ (ST 2094-40) parser in `lib/sidedata/hdr10plus.py` was written from
the ATSC A/341 (ST 2094-40 amendment) specification and cross-checked against
FFmpeg's `av_dynamic_hdr_plus_from_t35` decoder (`libavutil/hdr_dynamic_metadata.c`,
LGPL-2.1-or-later, part of FFmpeg) for field order and bit widths. No FFmpeg
code is vendored or linked; this is an independent implementation.
