#!/bin/sh
# Gate: Compound JumpRate V2 LIN clone vs C11 + independent Python oracle. No Zig.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /tmp/tinycc/lib/libtcc.so ] && [ -d /tmp/tinycc/lib/tcc ]; then
  export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/lib/libtcc.so}"
  export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc/lib/tcc}"
  export LD_LIBRARY_PATH="/tmp/tinycc/lib:${LD_LIBRARY_PATH:-}"
else
  export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
  export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
fi
if [ ! -x "$ROOT/transpile/c/bin/lin_c0" ]; then
  make -C "$ROOT/transpile/c" c0 || exit 2
fi
python3 "$ROOT/test/prove_compound_jumprate_external.py" || exit 1
exec python3 "$ROOT/tools/verify_compound_improvements_oracle.py"
