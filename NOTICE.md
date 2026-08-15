# Third-party notices

This addon (script.module.sidedata) is licensed GPL-2.0-or-later as a whole.

## libdovi

`lib/sidedata/native.py` binds to a `libdovi.so` build through `ctypes.CDLL` at runtime and calls straight into it. All Dolby Vision RPU bitstream parsing is done by that library, not by this addon (see README.md).

`lib/sidedata/native_libs/aarch64/libdovi.so` is an unmodified compiled build of `libdovi` 3.3.1 (MIT, quietvoid, https://github.com/quietvoid/dovi_tool), built from the `libdovi-3.3.1` tag of dovi_tool's `dolby_vision` crate per `tools/build-libdovi.sh`, and is distributed with this addon on that architecture. Other architectures fall back to a platform-provided `libdovi.so`, loaded at runtime with nothing distributed, and there is no bundled fallback parser for those.

`native.py` itself contains no dovi_tool code beyond struct layouts and function signatures transcribed from its public C header (`libdovi/rpu_parser.h`) so ctypes can call into it correctly. The MIT license terms apply equally to the bundled binary and this binding. The license text and copyright notice are reproduced in `LICENSES/dovi_tool.MIT`.

## libavutil

`lib/sidedata/avutil.py` binds to CoreELEC's own `libavutil.so` (part of FFmpeg, LGPL-2.1-or-later) through `ctypes.CDLL` at runtime and calls `av_dynamic_hdr_plus_from_t35` directly. All HDR10+ (ST 2094-40) T.35 parsing is done by that library, not by this addon.

`avutil.py` declares ctypes structs transcribed from FFmpeg 8.1.2's public header (`libavutil/hdr_dynamic_metadata.h`), unchanged in FFmpeg 9.0, the versions CoreELEC 22 has shipped, so ctypes can call into it correctly, gated on a matching `avutil_version()` major (see README.md's "Parsing engines"). No FFmpeg code is vendored or linked, and nothing is distributed with this addon for this path. `libavutil.so` is always CoreELEC's own copy.
