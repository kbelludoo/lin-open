#!/bin/sh
# Gate: u512 numeric coprocessor vs Python int + C11 oracles. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
if [ "${1:-}" = "--verify-receipt" ]; then
  exec python3 "$ROOT/examples/u512_coprocessor/verify_u512_receipt.py" \
    "$ROOT/examples/u512_coprocessor/u512_coprocessor_evidence.json"
fi
exec python3 "$ROOT/test/prove_u512_coprocessor_external.py"
