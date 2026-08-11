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

`lib/sidedata/native.py` binds to a `libdovi.so` build of the same project
at runtime via `ctypes.CDLL`, as a preferred RPU parsing backend (see
README.md). `lib/sidedata/native_libs/aarch64/libdovi.so` is an unmodified
compiled build of `libdovi` 3.3.1 (MIT, quietvoid), built from the
`libdovi-3.3.1` tag of dovi_tool's `dolby_vision` crate per
`tools/build-libdovi.sh`, and is distributed with this addon on that
architecture; other architectures fall back to a platform-provided
`libdovi.so` (dynamic runtime load only, nothing distributed) or this
addon's own pure-Python parser. `native.py` itself contains no dovi_tool
code beyond struct layouts and function signatures transcribed from its
public C header (`libdovi/rpu_parser.h`) so ctypes can call into it
correctly. The MIT license terms above apply equally to the bundled binary
and this binding; the license text and copyright notice are reproduced in
`LICENSES/dovi_tool.MIT`.

The HDR10+ (ST 2094-40) parser in `lib/sidedata/hdr10plus.py` was written from
the ATSC A/341 (ST 2094-40 amendment) specification and cross-checked against
FFmpeg's `av_dynamic_hdr_plus_from_t35` decoder (`libavutil/hdr_dynamic_metadata.c`,
LGPL-2.1-or-later, part of FFmpeg) for field order and bit widths. No FFmpeg
code is vendored or linked; this is an independent implementation.
