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
   `TestNativeConformance` (`tests/test_native.py`) must still match the
   pure parser dict-for-dict.
4. Update the version notes in `NOTICE.md` and `README.md`.
5. Bump the addon version in `addon.xml`.
6. Rebuild the addon zip.

## Planned: libhdr10plus-rs

A second bundled library, `libhdr10plus-rs` (quietvoid's `hdr10plus_tool`,
same capi/cargo-c pattern as `libdovi`), is planned to follow this same
checklist once added. Once both native backends are device-proven, the
pure-Python DV and HDR10+ parsers (`rpu.py`, `hdr10plus.py`) are scheduled
for removal.
