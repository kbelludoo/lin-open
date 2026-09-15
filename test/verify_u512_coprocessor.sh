#!/bin/sh
# Gate: 512-bit numeric coprocessor vs Python bigint + C11 limbs. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
exec python3 "$ROOT/test/prove_u512_coprocessor_external.py" "$@"
