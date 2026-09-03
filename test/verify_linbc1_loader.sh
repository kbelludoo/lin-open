#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN=${LIN_BIN:-$ROOT/zig-out/bin/lin_native}
SRC="$ROOT/src/lin_linbc1_loader.lin"

[ -x "$BIN" ] || { echo "LINBC1-LOADER: missing LIN_BIN=$BIN" >&2; exit 2; }
[ -f "$SRC" ] || { echo "LINBC1-LOADER: missing source=$SRC" >&2; exit 2; }

"$BIN" check "$SRC" >/dev/null
lint=$($BIN lint "$SRC")
grep -q 'errors=0' <<<"$lint"

out=$($BIN vm "$SRC" lb1_gate)
value=$(grep -o 'value=[-0-9]*' <<<"$out" | tail -1 | cut -d= -f2)
[ "$value" = 3 ] || { echo "LINBC1-LOADER: expected gate=3 got=$value" >&2; exit 1; }

expected=$($BIN vm "$SRC" lb1_gate_expected)
evalue=$(grep -o 'value=[-0-9]*' <<<"$expected" | tail -1 | cut -d= -f2)
[ "$evalue" = 3 ] || { echo "LINBC1-LOADER: expected marker=3 got=$evalue" >&2; exit 1; }

echo "LINBC1-LOADER: PASS (phase A safe reads + phase B static validation, 3 vectors)"
