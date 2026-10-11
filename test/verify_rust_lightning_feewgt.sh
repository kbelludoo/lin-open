#!/bin/sh
# Gate: rust-lightning v0.2.7 fee_for_weight LIN clone vs independent C11/Rust oracles. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
exec python3 "$ROOT/test/prove_rust_lightning_feewgt_external.py"
