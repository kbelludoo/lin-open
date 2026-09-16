#!/bin/sh
# Gate: u512 numeric coprocessor vs Python bigint + C11. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
python3 "$ROOT/test/prove_u512_coprocessor_external.py" || exit 1
exec python3 "$ROOT/examples/u512_coprocessor/verify_u512_receipt.py" \
  "$ROOT/examples/u512_coprocessor/u512_coprocessor_evidence.json"
