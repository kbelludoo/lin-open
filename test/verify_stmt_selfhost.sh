#!/usr/bin/env bash
# Gate do slice B3: statements/control-flow em LIN puro sobre o host C11.
# Escopo fechado: assignment, if/else e while; não é ainda parser arbitrário.
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1
LIN_C0=${LIN_C0:-transpile/c/bin/lin_c0}
MOD=src/linvm0_compiler/lin_stmt_lower_selfhost.lin
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
fail=0; pass=0
ok(){ pass=$((pass+1)); echo "ok   $1"; }
ko(){ fail=$((fail+1)); echo "NOK  $1"; }
result(){ sed -n 's/\.result{ fn="[^"]*" value=\([-0-9]*\) steps=\([0-9]*\) }.*/\1 \2/p'; }
[ -x "$LIN_C0" ] || { echo "NOK  host C11 ausente: $LIN_C0"; exit 1; }
for sel in 0 1 2; do
  got=$("$LIN_C0" vm "$MOD" stmt_gate 2>/dev/null | result); rc=$?
  [ "$rc" -eq 0 ] && [ "${got%% *}" = 1 ] && ok "stmt_gate selecionado=$sel (gate agregado)" || ko "stmt_gate (got '$got', rc=$rc)"
  break
done
img="$TMP/lin_stmt_lower_selfhost.linbc"
"$LIN_C0" image "$MOD" -o "$img" >"$TMP/image.log" 2>&1; rc=$?
if [ "$rc" -eq 0 ] && [ -s "$img" ]; then
  ok "imagem LINBC1 criada"
  "$LIN_C0" image "$MOD" -o "$TMP/second.linbc" >/dev/null 2>&1
  cmp -s "$img" "$TMP/second.linbc" && ok "imagem reproduzível byte a byte" || ko "imagem não reproduzível"
  src_run=$("$LIN_C0" vm "$MOD" stmt_gate 2>/dev/null | result)
  img_run=$("$LIN_C0" run "$img" stmt_gate 2>/dev/null | result)
  [ "$src_run" = "$img_run" ] && ok "rota fonte == rota LINBC1 ($src_run)" || ko "rota fonte '$src_run' != imagem '$img_run'"
else
  ko "imagem LINBC1 falhou (rc=$rc)"
fi
if [ "$fail" -eq 0 ]; then
  echo "STMT-SELFHOST: PASS ($pass verificações, slice B3)"
else
  echo "STMT-SELFHOST: FAIL ($fail falhas de $((pass+fail)))"
fi
exit "$fail"
