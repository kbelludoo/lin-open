#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BIN=${LIN_BIN:-$ROOT/zig-out/bin/lin_native}
TMP=${TMPDIR:-/tmp}/lin_image_view_dispatch_$$.lin
trap 'rm -f "$TMP"' EXIT
[ -x "$BIN" ] || { echo "IMAGE-VIEW: missing LIN_BIN=$BIN" >&2; exit 2; }
{
  tail -n +4 "$ROOT/src/lin_linbc1_loader.lin"
  tail -n +4 "$ROOT/src/linvm_image_view.lin"
} > "$TMP"
"$BIN" check "$TMP" >/dev/null
"$BIN" lint "$TMP" >/dev/null
run() {
  "$BIN" vm "$TMP" "$1" 2>&1 | sed -n 's/.*value=\(-\?[0-9]*\).*/\1/p'
}
loader=$(run lb1_validate_fixture)
[ "$loader" = 2 ] || { echo "IMAGE-VIEW: loader expected=2 got=$loader" >&2; exit 1; }
call=$(run iv_call_image)
[ "$call" = 42 ] || { echo "IMAGE-VIEW: call expected=42 got=$call" >&2; exit 1; }
array=$(run iv_array_image)
[ "$array" = 99 ] || { echo "IMAGE-VIEW: array expected=99 got=$array" >&2; exit 1; }
bad=$(run iv_bad_index)
[ "$bad" = 1 ] || { echo "IMAGE-VIEW: bad-index expected=1 got=$bad" >&2; exit 1; }
all=$(run iv_gate)
[ "$all" = 3 ] || { echo "IMAGE-VIEW: gate expected=3 got=$all" >&2; exit 1; }
echo "IMAGE-VIEW: PASS (H8 offsets -> H5 call -> H6 arrays)"
