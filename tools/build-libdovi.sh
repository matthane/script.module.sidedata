#!/bin/bash
# Rebuilds lib/sidedata/native_libs/aarch64/libdovi.so from quietvoid/dovi_tool's
# dolby_vision crate (capi feature, cargo-c library name "dovi" -> libdovi.so).
# See UPDATING.md for the full maintainer checklist this script is one step of.
#
# The same cargo cbuild invocation below, run without --target from inside
# $SRC_DIR, produces a host-arch build instead - that's the x86_64 build
# tests/test_native.py points SIDEDATA_LIBDOVI_PATH at for local golden
# testing (never packaged into the addon zip). See UPDATING.md.
set -euo pipefail

LIBDOVI_TAG="libdovi-3.3.1"
SRC_URL="https://github.com/quietvoid/dovi_tool/archive/refs/tags/${LIBDOVI_TAG}.tar.gz"
TARGET_TRIPLE="aarch64-unknown-linux-gnu"
CROSS_CC="aarch64-linux-gnu-gcc"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/lib/sidedata/native_libs/aarch64/libdovi.so"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "fetching $SRC_URL"
curl -fsSL "$SRC_URL" | tar -xz -C "$WORKDIR"
SRC_DIR="$(find "$WORKDIR" -mindepth 1 -maxdepth 1 -type d)/dolby_vision"

# Path (a): generic rustup + cargo-c cross build. Device-untested on this
# host (no rust toolchain here) - written from cargo-c's documented
# --target/--library-type interface; dolby_vision/Cargo.toml's
# package.metadata.capi.library.name = "dovi" is what names the output
# libdovi.so.
if command -v cargo >/dev/null 2>&1 && command -v "$CROSS_CC" >/dev/null 2>&1; then
  rustup target add "$TARGET_TRIPLE"
  cargo install cargo-c --locked

  (
    cd "$SRC_DIR"
    CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER="$CROSS_CC" \
      cargo cbuild --release --target "$TARGET_TRIPLE" --library-type cdylib
  )
  OUT="$SRC_DIR/target/$TARGET_TRIPLE/release/libdovi.so"
else
  echo "no rustup + cargo-c + $CROSS_CC toolchain found on this host" >&2
  echo "path (b): any aarch64-glibc cross toolchain works too - e.g. the" >&2
  echo "CoreELEC aarch64 toolchain - run the same 'cargo cbuild' invocation" >&2
  echo "above from inside that toolchain's environment, with its own cc and" >&2
  echo "target triple in place of $CROSS_CC/$TARGET_TRIPLE; the resulting" >&2
  echo "libdovi.so is ABI-compatible regardless of which aarch64-glibc" >&2
  echo "toolchain produced it" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
cp "$OUT" "$DEST"

echo "$DEST"
file "$DEST"
