#!/bin/sh
# Re-run the GMX V2 getCappedPnl external proof (C11 + LIN C0).
set -eu
cd "$(dirname "$0")/.."
exec python3 test/prove_gmx_v2_capped_pnl_external.py
