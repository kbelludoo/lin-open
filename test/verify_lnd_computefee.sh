#!/bin/sh
# Gate: lnd BOLT07 ComputeFee LIN clone vs independent C11 oracle. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
exec python3 "$ROOT/test/prove_lnd_computefee_external.py"
