#!/bin/sh
# Re-run the GMX V2 getNextFundingFactorPerSecond external proof (C11 + LIN C0).
set -eu
cd "$(dirname "$0")/.."
export LIN_TCC_LIB="${LIN_TCC_LIB:-/tmp/tinycc/libtcc.so}"
export LIN_TCC_DIR="${LIN_TCC_DIR:-/tmp/tinycc}"
if [ ! -x transpile/c/bin/lin_c0 ]; then
  make -C transpile/c c0 || exit 2
fi
exec python3 test/prove_gmx_v2_funding_fps_external.py
