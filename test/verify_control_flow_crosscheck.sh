#!/usr/bin/env bash
# Cross-check integrado do parser/compiler + LinVM Zig + Compiler 0 C11.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
BIN=${BIN:-zig-out/bin/lin_native}
C0=${LIN_C0:-transpile/c/bin/lin_c0}
SRC=test/fixtures/control_flow_regression.lin

[ -x "$BIN" ] || { echo "missing Zig binary: $BIN" >&2; exit 1; }
[ -x "$C0" ] || { echo "missing C11 host: $C0" >&2; exit 1; }

run() {
  local exe=$1 fn=$2; shift 2
  "$exe" vm "$SRC" "$fn" "$@" \
    | sed -n 's/.*\.result{ fn="[^"]*" value=\([-0-9]*\) steps=\([0-9]*\) }.*/\1 \2/p'
}

check_pair() {
  local fn=$1 expected=$2; shift 2
  local zig_run c_run
  zig_run=$(run "$BIN" "$fn" "$@")
  c_run=$(run "$C0" "$fn" "$@")
  [ "$zig_run" = "$expected" ] || { echo "Zig mismatch: $fn -> '$zig_run', expected '$expected'"; exit 1; }
  [ "$c_run" = "$expected" ] || { echo "C11 mismatch: $fn -> '$c_run', expected '$expected'"; exit 1; }
  [ "$zig_run" = "$c_run" ] || { echo "cross-check divergence: $fn Zig='$zig_run' C11='$c_run'"; exit 1; }
  echo "ok   $fn $* -> value/steps=$zig_run"
}

"$BIN" check "$SRC" >/dev/null
check_pair branch "7 6" 5
check_pair branch "0 6" -2
check_pair count_to_three "3 35"
echo "CONTROL-FLOW-CROSSCHECK: PASS (Zig == C11, 3 vectors)"
