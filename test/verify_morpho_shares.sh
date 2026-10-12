#!/usr/bin/env bash
# Fail-closed wrapper: Morpho Blue SharesMathLib LIN clone vs C11 / Python oracles.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/test/prove_morpho_shares_external.py"
