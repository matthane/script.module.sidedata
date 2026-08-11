# Updating the bundled libdovi

Checklist for moving `lib/sidedata/native_libs/aarch64/libdovi.so` to a new
upstream `dolby_vision`/`libdovi` tag.

1. Diff `libdovi/rpu_parser.h` between the currently bundled tag and the new
   one (quietvoid/dovi_tool, `dolby_vision/` crate). If any struct field,
   order, or type changed, update the matching `ctypes.Structure` in
   `lib/sidedata/native.py` to match. **Never swap the `.so` alone** - a
   layout slip there is silent memory corruption, not a crash.
2. Bump `LIBDOVI_TAG` at the top of `tools/build-libdovi.sh` and rebuild:
   `tools/build-libdovi.sh`.
3. Run the golden suite against the new library: on real aarch64 hardware,
   or elsewhere by pointing `SIDEDATA_LIBDOVI_PATH` at a host-arch build of
   the same tag (`python3 -m unittest discover tests`). Every fixture in
   `tests/test_native.py`'s golden test classes must still match
   `dovi_tool`'s own JSON dump field-for-field.
4. Update the version notes in `NOTICE.md` and `README.md`.
5. Check whether upstream has added FFI panic-catching (`catch_unwind`) to
   libdovi's C API; if so, remove the panic caveat from README.md's Known
   limitations.
6. Bump the addon version in `addon.xml`.
7. Rebuild the addon zip.

`tools/build-libdovi.sh` cross-builds the bundled aarch64 `.so`. The same
`cargo cbuild --release --library-type cdylib` invocation, run from inside
the checked-out `dolby_vision` crate directory *without* `--target` (so it
builds for the host triple instead of cross-compiling), produces a host
build for local test runs - that's what backs
`~/ce/dvhdr-testdata/libdovi.so.3.3.1.x86_64` and `SIDEDATA_LIBDOVI_PATH` in
`tests/test_native.py`. It's never packaged into the addon zip.

# Updating for a new CE ffmpeg major

Checklist for moving `lib/sidedata/avutil.py`'s pinned `libavutil` major
(currently 60, FFmpeg 8.1.2) to whatever ffmpeg CE-22 bumps to next.

1. Find the new `libavutil/hdr_dynamic_metadata.h` in the CE build tree for
   the new ffmpeg version (`build.CoreELEC-Amlogic-*/build/ffmpeg-*/libavutil/`).
   Diff `AVDynamicHDRPlus`, `AVHDRPlusColorTransformParams` and
   `AVHDRPlusPercentile` against the ctypes structs in `avutil.py`. If any
   field, order, type, or array bound changed, update the matching
   `ctypes.Structure` to match - this is a plain stack struct passed by
   pointer, not an opaque allocation, so a layout slip corrupts the stack,
   it doesn't crash cleanly.
2. Bump `_LIBAVUTIL_VERSION_MAJOR` in `avutil.py` to the new
   `LIBAVUTIL_VERSION_MAJOR` (from the new build's `libavutil/version.h`).
3. Retest: a host with a version-matched system `libavutil` will run
   `tests/test_hdr10plus.py`'s golden test for real; otherwise (the common
   case - a dev host's system ffmpeg rarely matches CE's pinned major)
   verify on device, same as HDR10+ conformance has been proven since this
   addon moved off the pure-Python parser.
4. Update the "Pinned versions" table in `README.md` and the version notes
   in `NOTICE.md`.
5. Bump the addon version in `addon.xml`.
6. Rebuild the addon zip.
