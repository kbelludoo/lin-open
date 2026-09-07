#!/usr/bin/env bash
# test/verify_c0_check.sh — `check`/`lint` do host C11 byte-idênticos ao Stage0.
#
# O que esta porta prova (e nada mais):
#   1. parte pinada (só C0, sem Zig): vetores negativos e positivos com
#      rc/stdout/stderr EXATOS pinados neste script (goldens derivados do
#      Stage0 Zig uma vez, na autoria — mesma disciplina do vms_gate);
#   2. parte diferencial (precisa do Zig como oráculo): `check` e `lint` do
#      C0 byte-idênticos ao `lin_native` em TODO o corpus src/ + examples/
#      (rc + stdout + stderr). Sem Zig no PATH, esta parte é pulada;
#   3. parte autoconsistência (só C0): todo .lin do corpus passa no `check`
#      (rc=0, cabeçalho LIN_CHECK) e no `lint` (rc=0) — o que `make test`
#      exige do Stage0, exigido aqui do C0.
# Com SAN=1 o binário é reconstruído com ASan+UBSan (inclui lin_c0_check.c).
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1

C0=${1:-transpile/c/bin/lin_c0}
LIN_NATIVE=${LIN_NATIVE:-zig-out/bin/lin_native}
SAN=${SAN:-}
CC=${CC:-cc}
pass=0; fail=0
ok(){ pass=$((pass + 1)); echo "ok   $1"; }
ko(){ fail=$((fail + 1)); echo "NOK  $1"; }

if [ ! -x "$C0" ]; then
  build=$(make -C transpile/c c0 2>&1); rc=$?
  [ "$rc" -eq 0 ] || { echo "NOK  build do host C11"; exit 1; }
fi
[ -x "$C0" ] || { echo "NOK  host não encontrado ($C0)"; exit 1; }

C0RUN=$C0
if [ -n "$SAN" ]; then
  SWEEP_TMP=$(mktemp -d)/lin_c0_check_san
  $CC -O1 -g -std=c11 -fsanitize=address,undefined -fno-sanitize-recover=all \
      -I transpile/c -I transpile/c/lin_c -o "$SWEEP_TMP" \
      transpile/c/tool/lin_c0.c transpile/c/tool/lin_c0_front.c \
      transpile/c/tool/lin_c0_check.c \
      transpile/c/lin_c/*.c || { echo "NOK  build com sanitizers"; exit 1; }
  echo "     sanitizers ..... ASan+UBSan ativos"
  C0RUN=$SWEEP_TMP
fi

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

echo "--- 1. vetores pinados (só C0) ---"
# mkneg <nome> <conteúdo...> : escreve o .lin via printf %b
mkneg() {
  local name=$1; shift
  printf '%b' "$1" > "$TMP/$name.lin"
}
check_pin() { # check_pin <nome> <rc> <stdout> <stderr>
  local name=$1 exprc=$2 expout=$3 experr=$4 gotrc=0
  "$C0RUN" check "$TMP/$name.lin" > "$TMP/got.out" 2> "$TMP/got.err" || gotrc=$?
  if [ "$gotrc" = "$exprc" ] && [ "$(cat "$TMP/got.out")" = "$expout" ] \
     && [ "$(cat "$TMP/got.err")" = "$experr" ]; then
    ok "check $name (rc=$exprc)"
  else
    ko "check $name: rc=$gotrc out=[$(head -c 100 "$TMP/got.out")] err=[$(head -c 120 "$TMP/got.err")]"
  fi
}

mkneg unbalanced '!f(x: int) -> int {\n  ^x;\n'
check_pin unbalanced 1 "" "LIN_PARSE"
mkneg nofn '// so comentario\n'
check_pin nofn 1 "" "LIN_PARSE"
mkneg empty ''
check_pin empty 1 "" "LIN_PARSE"
mkneg ret_int_str '@LIN:L1c:0.2\n!f(x: int) -> int {\n  ^"s";\n}\n=ex{f}\n'
check_pin ret_int_str 1 "" "LIN_TYPE_ERROR: function 'f' return type mismatch: expected int, got string"
mkneg arg_bool_int '@LIN:L1c:0.2\n!f(x: bool) -> bool {\n  ^x;\n}\n!g(y: int) -> bool {\n  z = f(y);\n  ^z;\n}\n=ex{f,g}\n'
check_pin arg_bool_int 1 "" "LIN_TYPE_ERROR: function 'f' argument 'x' expected type bool, got int"
mkneg mini '@LIN:L1c:0.2\n!k(x: int) -> int { ^x * 2 + 1 }\n=ex{k}\n'
check_pin mini 0 '@RULEL:LIN_CHECK:1.0.0
.header="@LIN:L1c:0.2"
.fns=["k"]
.exports=["k"]
.types{
  .k{ params=["x:int"] return="int" }
}
.typecheck=passed' ""

lint_pin() { # lint_pin <nome> <conteúdo> <rc> <stdout>
  local name=$1 exprc=$3 expout=$4 gotrc=0
  printf '%b' "$2" > "$TMP/$name.lin"
  "$C0RUN" lint "$TMP/$name.lin" > "$TMP/got.out" 2> "$TMP/got.err" || gotrc=$?
  if [ "$gotrc" = "$exprc" ] && [ "$(cat "$TMP/got.out")" = "$expout" ] \
     && [ ! -s "$TMP/got.err" ]; then
    ok "lint $name (rc=$exprc)"
  else
    ko "lint $name: rc=$gotrc out=[$(head -c 200 "$TMP/got.out")]"
  fi
}
lint_pin div '@LIN:L1c:0.2\n!f(x: int) -> int {\n  y = x / 2;\n  ^y;\n}\n=ex{f}\n' 0 '@RULEL:LIN_LINT:1.0.0
.policy{ level=error fail_closed=true rationale=every_rejected_construct_names_its_supported_alternative }
.diagnostics{
  .d{ code=INT_DIVISION line=3 col=9 fix="no integer division; subtract in a loop or pass a power of ten" }
}
.summary{ errors=1 }'
lint_pin mini '@LIN:L1c:0.2\n!k(x: int) -> int { ^x * 2 + 1 }\n=ex{k}\n' 0 '@RULEL:LIN_LINT:1.0.0
.policy{ level=error fail_closed=true rationale=every_rejected_construct_names_its_supported_alternative }
.diagnostics{
}
.summary{ errors=0 }'

echo "--- 2. diferencial contra o Stage0 (oráculo) ---"
if [ -x "$LIN_NATIVE" ]; then
  n=0
  for f in $(find src examples -name '*.lin' | sort); do
    n=$((n + 1))
    "$LIN_NATIVE" check "$f" > "$TMP/z.out" 2> "$TMP/z.err"; zrc=$?
    "$C0RUN" check "$f" > "$TMP/c.out" 2> "$TMP/c.err"; crc=$?
    if [ "$zrc" != "$crc" ] || ! cmp -s "$TMP/z.out" "$TMP/c.out" \
       || ! cmp -s "$TMP/z.err" "$TMP/c.err"; then
      ko "check $f (zig rc=$zrc c0 rc=$crc)"; continue
    fi
    "$LIN_NATIVE" lint "$f" > "$TMP/z.out" 2> "$TMP/z.err"; zrc=$?
    "$C0RUN" lint "$f" > "$TMP/c.out" 2> "$TMP/c.err"; crc=$?
    if [ "$zrc" != "$crc" ] || ! cmp -s "$TMP/z.out" "$TMP/c.out" \
       || ! cmp -s "$TMP/z.err" "$TMP/c.err"; then
      ko "lint $f (zig rc=$zrc c0 rc=$crc)"; continue
    fi
  done
  ok "diferencial check+lint byte-idêntico em $n arquivos"
else
  echo "     oráculo Zig ausente ($LIN_NATIVE) — diferencial pulado"
fi

echo "--- 3. autoconsistência do corpus (só C0) ---"
n=0
for f in $(find src examples -name '*.lin' | sort); do
  n=$((n + 1))
  if ! "$C0RUN" check "$f" 2>/dev/null | grep -q '^@RULEL:LIN_CHECK:1.0.0'; then
    ko "check $f"
  fi
  if ! "$C0RUN" lint "$f" >/dev/null 2>&1; then
    ko "lint $f"
  fi
done
ok "autoconsistência check+lint em $n arquivos"

echo ""
echo "=== C0-CHECK: $pass ok, $fail falhas ==="
[ "$fail" -eq 0 ]
