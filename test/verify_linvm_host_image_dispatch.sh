#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BIN=${LIN_BIN:-$ROOT/zig-out/bin/lin_native}
TMP=${TMPDIR:-/tmp}/linvm_host_image_dispatch_$$.lin
trap 'rm -f "$TMP"' EXIT
[ -x "$BIN" ] || { echo "HOST-IMAGE-DISPATCH: missing LIN_BIN=$BIN" >&2; exit 2; }
{
  tail -n +4 "$ROOT/src/lin_linbc1_loader.lin"
  tail -n +4 "$ROOT/src/linvm_host_v1.lin"
} > "$TMP"
"$BIN" check "$TMP" >/dev/null
"$BIN" lint "$TMP" >/dev/null
run() {
  "$BIN" vm "$TMP" "$1" 2>&1 | sed -n 's/.*value=\(-\?[0-9]*\).*/\1/p'
}
valid=$(run lb1_validate_fixture)
[ "$valid" = 2 ] || { echo "HOST-IMAGE-DISPATCH: loader expected=2 got=$valid" >&2; exit 1; }
call=$(run host_image_call)
[ "$call" = 42 ] || { echo "HOST-IMAGE-DISPATCH: call expected=42 got=$call" >&2; exit 1; }
array=$(run host_image_array)
[ "$array" = 99 ] || { echo "HOST-IMAGE-DISPATCH: array expected=99 got=$array" >&2; exit 1; }
bad=$(run host_image_array_bad_index)
[ "$bad" = 1 ] || { echo "HOST-IMAGE-DISPATCH: bad-index expected=1 got=$bad" >&2; exit 1; }
# The bridge must fail closed when H8 rejects the image.
"$BIN" vm "$TMP" host_image_dispatch_gate >/tmp/host_image_dispatch_gate.log 2>&1
bridge=$(sed -n 's/.*value=\(-\?[0-9]*\).*/\1/p' /tmp/host_image_dispatch_gate.log)
[ "$bridge" = 3 ] || { echo "HOST-IMAGE-DISPATCH: bridge expected=3 got=$bridge" >&2; exit 1; }
echo "HOST-IMAGE-DISPATCH: PASS (H8 loader -> H5 call -> H6 arrays)"
