#!/bin/sh
# Re-run the Compound III accrualDescaleFactor external proof (C11 + LIN C0).
set -eu
cd "$(dirname "$0")/.."
exec python3 test/prove_comet_descale_external.py
