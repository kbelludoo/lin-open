#!/bin/sh
# Gate: u512 numeric coprocessor + settle_u256_word LCR2 e2e. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
if [ ! -x "$ROOT/transpile/c/bin/lin_bc1_run" ]; then
  make -C "$ROOT/transpile/c" bin/lin_bc1_run || exit 2
fi
python3 "$ROOT/test/prove_u512_coprocessor_external.py" || exit 1
python3 "$ROOT/test/prove_u256_settle_lcr2_external.py" || exit 1
python3 "$ROOT/test/prove_u512_coprocessor_external.py" --verify-receipt "$ROOT/examples/u512_coprocessor/u512_coprocessor_evidence.json" || exit 1
python3 "$ROOT/test/prove_u256_settle_lcr2_external.py" --verify-receipt "$ROOT/examples/u512_coprocessor/u256_settle_lcr2_evidence.json" || exit 1
echo "u512-coprocessor-proof: PASS"
