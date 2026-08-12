# Test fixtures

The golden RPU and HDR10+ fixtures used by `tests/test_native.py`,
`tests/test_hdr10plus.py`, and `tests/test_parse_sidedata.py` are payloads
extracted from real commercial titles. They are kept out of this public
repo and live at `~/ce/dvhdr-testdata/module-fixtures` on the maintainer's
machine instead. `SIDEDATA_FIXTURES_DIR` overrides that location.

- `signs_frame0.{rpu,json}` and `signs_frame500.{rpu,json}` are real
  device-captured content (Signs 2002, profile 8.1); frame 500 also
  exercises L8/L10 target resolution.
- `dv10_av1_frame{0,700}.{t35,json}` are two ITU-T T.35 metadata OBU
  payloads walked out of a real AV1 elementary stream, checked against
  `dovi_tool`'s own JSON dump of the same title's separately-extracted
  regular-RPU form at the matching frame index. Every one of the title's
  1450 frames was cross-checked this way during development, not just the
  two committed fixtures; see git history.
- `dv7fel_frame0.{rpu,json}` and `dv7mel_frame0.{rpu,json}` are real
  dual-layer profile 7 content, one FEL title and one MEL title, so
  `el_type` is checked against real NLQ residual data, not just a
  synthetic flag flip.
- `lake10_prefix.hevc` is real HDR10+ SEI-bearing HEVC content used by the
  HDR10+ golden test.

Every test that reads from this directory is `skipUnless` guarded and
names the expected directory in its skip message when the directory is
missing, so `python3 -m unittest discover tests` still passes cleanly
without the fixtures, just with fewer things actually checked. Run the
suite once with the fixtures present before trusting a change to the
parsers.

# Updating the bundled libdovi

Checklist for moving `lib/sidedata/native_libs/aarch64/libdovi.so` to a new
upstream `dolby_vision`/`libdovi` tag.

1. Diff `libdovi/rpu_parser.h` between the currently bundled tag and the new
   one (quietvoid/dovi_tool, `dolby_vision/` crate). If any struct field,
   order, or type changed, update the matching `ctypes.Structure` in
   `lib/sidedata/native.py` to match. **Never swap the `.so` alone.** A
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
build for local test runs. That's what backs
`~/ce/dvhdr-testdata/libdovi.so.3.3.1.x86_64` and `SIDEDATA_LIBDOVI_PATH` in
`tests/test_native.py`. It's never packaged into the addon zip.

# Updating for a new CE ffmpeg major

Checklist for covering a new `libavutil` major in `lib/sidedata/avutil.py`
(currently 60 and 61, FFmpeg 8.1.2 and 9.0) when CoreELEC 22 bumps ffmpeg.

1. Find the new `libavutil/hdr_dynamic_metadata.h` in the CE build tree for
   the new ffmpeg version (`build.CoreELEC-Amlogic-*/build/ffmpeg-*/libavutil/`).
   Diff `AVDynamicHDRPlus`, `AVHDRPlusColorTransformParams` and
   `AVHDRPlusPercentile` against the ctypes structs in `avutil.py`. If any
   field, order, type, or array bound changed, update the matching
   `ctypes.Structure` to match. This is a plain stack struct passed by
   pointer, not an opaque allocation, so a layout slip corrupts the stack
   rather than crashing cleanly.
2. Add the new `LIBAVUTIL_VERSION_MAJOR` (from the new build's
   `libavutil/version.h`) to `_LIBAVUTIL_VERSION_MAJORS` in `avutil.py`,
   newest first, and add the matching `libavutil.so.<major>` candidate to
   the loader. Drop majors no supported CE release still ships.
3. Retest: a host with a version-matched system `libavutil` will run
   `tests/test_hdr10plus.py`'s golden test for real. Otherwise, which is
   the common case since a dev host's system ffmpeg rarely matches CE's
   pinned major, verify on device, the same way HDR10+ conformance has
   been proven since this addon moved off the pure-Python parser.
4. Update the "Pinned versions" table in `README.md` and the version notes
   in `NOTICE.md`.
5. Bump the addon version in `addon.xml`.
6. Rebuild the addon zip.
