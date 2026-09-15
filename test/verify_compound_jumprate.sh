#!/bin/sh
# Gate: Compound JumpRate V2 LIN clone vs independent C11 + Python oracles. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -z "${LIN_TCC_LIB:-}" ]; then
  if [ -f /tmp/tinycc/lib/libtcc.so ]; then
    LIN_TCC_LIB=/tmp/tinycc/lib/libtcc.so
  elif [ -f /tmp/tinycc/libtcc.so ]; then
    LIN_TCC_LIB=/tmp/tinycc/libtcc.so
  fi
fi
if [ -z "${LIN_TCC_DIR:-}" ]; then
  if [ -f /tmp/tinycc/lib/tcc/libtcc1.a ]; then
    LIN_TCC_DIR=/tmp/tinycc/lib/tcc
  elif [ -f /tmp/tinycc/libtcc1.a ]; then
    LIN_TCC_DIR=/tmp/tinycc
  fi
fi
export LIN_TCC_LIB LIN_TCC_DIR
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
exec python3 "$ROOT/test/prove_compound_jumprate_external.py"
