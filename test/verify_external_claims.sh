#!/bin/sh
# verify_external_claims.sh — one-command rationalist proof.
#
# Builds (if needed) the no-Zig C11 Compiler-0 host, then runs the independent
# Python proof harness. The harness only marks a claim PASS when an outsider can
# redo it. It explicitly reports claims that are NOT proven (e.g. full Uniswap
# execution on LinVM on this host) instead of advertising them as true.
#
# Usage:
#   ./test/verify_external_claims.sh [--fetch]
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=$ROOT/transpile/c/bin/lin_c0
XREC=$ROOT/transpile/c/bin/lin_c_receipt

if [ ! -x "$C0" ] || [ ! -x "$XREC" ]; then
  echo "verify_external_claims: building Compiler-0 host (cc only, no Zig)..."
  make -C "$ROOT/transpile/c" all >/dev/null || {
    echo "verify_external_claims: build failed" >&2
    exit 2
  }
fi

exec python3 "$ROOT/test/prove_all_claims_external.py" "$@"
