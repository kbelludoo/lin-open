#!/usr/bin/env bash
# verify_linvm0.sh — gate do front-end compiler0 em LIN (marco V2, Stage B2).
#
# Verifica que:
#   1. src/linvm0_compiler/lin_lexer_selfhost.lin passa `check` e `lint`, e que
#      o lexer LIN reproduz bit-exact o checksum do oraculo independente
#      (`reference_tokenize.py`) — lex_gate == 1.
#   2. src/linvm0_compiler/lin_expr_eval.lin passa `check` e `lint`, e que o
#      avaliador de expressoes reproduz os resultados dos vetores v0/v7/v8/v9/
#      v10/v11/v14/v15/v16/v17 do LINVM_ISA_V1 §7 — xver_gate == 1.
#   3. src/linvm0_compiler/lin_lower_selfhost.lin passa `check`/`lint` e que o
#      lowerer LIN emite o bytecode canonico (fold sobre opcodes+operandos)
#      dos vetores v0/v8/v11/v14/v17, batendo com o oraculo
#      `reference_lower.py` (que replica o post-order do consenso) — low_gate == 1.
#
# Honestidade (R5): ISTO e o INICIO de V2 (front-end subset). NAO e o compilador
# completo, NAO ha ponto fixo C0=C1=C2, nem imagem LINBC1 derivada de texto.
# Rotulado EXPERIMENTAL em AGENTS.md/R5.
#
# Uso: verify_linvm0.sh [BIN]  (default: zig-out/bin/lin_native)
set -euo pipefail
BIN="${1:-zig-out/bin/lin_native}"
DIR="src/linvm0_compiler"

fail() { echo "LINVM0: FAIL: $*"; exit 1; }
ok()   { echo "LINVM0:   ok: $*"; }

[ -x "$BIN" ] || fail "lin binary not found: $BIN"

# --- 1. lexer selfhost ---
echo "== lexer selfhost =="
"$BIN" check "$DIR/lin_lexer_selfhost.lin" >/dev/null || fail "lexer check"
ok "check"
"$BIN" lint  "$DIR/lin_lexer_selfhost.lin" | grep -q 'errors=0' || fail "lexer lint"
ok "lint"
echo "-- oraculo independente (reference_tokenize.py) --"
python3 "$DIR/reference_tokenize.py" | grep -q 'num_tokens=20' || fail "oracle tokens"
ok "oracle num_tokens=20"
python3 "$DIR/reference_tokenize.py" | grep -q 'checksum=1371904279658369433' || fail "oracle checksum"
ok "oracle checksum"
g="$( "$BIN" vm "$DIR/lin_lexer_selfhost.lin" lex_gate | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$g" = "1" ] || fail "lex_gate (got $g)"
ok "lex_gate=1"
s="$( "$BIN" vm "$DIR/lin_lexer_selfhost.lin" lex_scan_embedded | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$s" = "1371904279658369433" ] || fail "lex checksum (got $s)"
ok "lex checksum == oracle"

# --- 2. expr eval (subset dos vetores §7) ---
echo "== expr eval (subset xver) =="
"$BIN" check "$DIR/lin_expr_eval.lin" >/dev/null || fail "eval check"
ok "check"
"$BIN" lint  "$DIR/lin_expr_eval.lin" | grep -q 'errors=0' || fail "eval lint"
ok "lint"
g="$( "$BIN" vm "$DIR/lin_expr_eval.lin" xver_gate | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$g" = "1" ] || fail "xver_gate (got $g)"
ok "xver_gate=1 (10/10 vetores)"

# --- 3. lowerer (fonte -> bytecode canonico) ---
echo "== lowerer (fonte -> bytecode canonico) =="
"$BIN" check "$DIR/lin_lower_selfhost.lin" >/dev/null || fail "lower check"
ok "check"
"$BIN" lint  "$DIR/lin_lower_selfhost.lin" | grep -q 'errors=0' || fail "lower lint"
ok "lint"
echo "-- oraculo independente (reference_lower.py) --"
python3 "$DIR/reference_lower.py" >/dev/null || fail "lower oracle"
ok "lower oracle"
g="$( "$BIN" vm "$DIR/lin_lower_selfhost.lin" low_gate | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$g" = "1" ] || fail "low_gate (got $g)"
ok "low_gate=1 (5/5 folds == consenso)"

echo
echo "LINVM0-GATE: PASS (marco V2/B2: front-end subset em LIN — lexer+eval+lowerer)"
