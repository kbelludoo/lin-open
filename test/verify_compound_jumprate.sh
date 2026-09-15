#!/bin/sh
# Gate: Compound JumpRate V2 LIN clone vs independent C11 oracle. No Zig.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /tmp/tinycc/lib/libtcc.so ]; then
  export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/lib/libtcc.so}"
else
  export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
fi
export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
export LD_LIBRARY_PATH="/tmp/tinycc/lib:${LD_LIBRARY_PATH:-}"
# TinyCC looks for libtcc1.a at $LIN_TCC_DIR/libtcc1.a (prefix layout puts it in lib/tcc/).
if [ ! -e /tmp/tinycc/libtcc1.a ] && [ -f /tmp/tinycc/lib/tcc/libtcc1.a ]; then
  ln -sf /tmp/tinycc/lib/tcc/libtcc1.a /tmp/tinycc/libtcc1.a
fi
if [ ! -e /tmp/tinycc/libtcc.so ] && [ -f /tmp/tinycc/lib/libtcc.so ]; then
  ln -sf /tmp/tinycc/lib/libtcc.so /tmp/tinycc/libtcc.so
fi
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
python3 "$ROOT/test/prove_compound_jumprate_external.py" || exit $?
exec python3 "$ROOT/test/prove_compound_improvements_independent.py"
