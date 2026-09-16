#!/bin/sh
# External 512-bit coprocessor proof (no Zig).
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x test/prove_u512_coprocessor_external.py \
         examples/u512_coprocessor/verify_u512_receipt.py \
         examples/u512_coprocessor/verify_u512_receipt.js
exec python3 test/prove_u512_coprocessor_external.py
