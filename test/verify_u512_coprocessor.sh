#!/bin/sh
# Gate: u512 numeric coprocessor + u256 LCR2 e2e slice. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
python3 "$ROOT/test/prove_u512_coprocessor_external.py" || exit 1
exec python3 "$ROOT/test/prove_u256_lcr2_e2e_slice.py"
