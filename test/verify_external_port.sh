#!/bin/sh
# verify_external_port.sh — gate do port EXTERNO: código clonado do GitHub → LIN.
#
# O que ele mede (e só o que ele mede):
#   1. o host C11 (`lin_c0`) aceita e executa o lexer LIN escrito a partir do
#      contrato do `stb_c_lexer.h` (github.com/nothings/stb) e reproduz os
#      goldens publicados;
#   2. os mesmos valores E os mesmos `steps` no host Zig, quando o Zig existe
#      no ambiente (senao: SKIP explicito, nunca PASS emprestado);
#   3. o mesmo valor saindo da IMAGEM congelada (rota `roundtrip`);
#   4. um oráculo independente em Python re-deriva os goldens a partir do corpus
#      (nem LIN, nem C) — forjar um golden exige mudar `ref_oracle.py` tambem;
#   5. os `.lin` conferem com `gen_fixture.py` (nada editado a mao);
#   6. o caso FORA DA FATIA (`boundary.c`: hex/float/sufixos) tem que dar
#      `mx_gate=0`. Este gate FALHA se alguem passar a reproduzir o upstream
#      nesse caso sem atualizar a documentacao da fronteira.
#
# Com STB_DIR apontando para um clone de `github.com/nothings/stb` (commit
# 2c980bb59875b0d32144a71867fbdebb2f77cd20), a perna 7 compila o lexer REAL de
# terceiro sobre o mesmo corpus e exige igualdade bit a bit. Sem STB_DIR: SKIP.
# O cabecalho de terceiro NAO e vendorizado neste repositorio (licenca MIT/domínio
# publico, mas o gate nao depende de baixar nada).
#
# Nada aqui chama `zig build`. O unico uso de Zig e `zig-out/bin/lin_native vm`,
# se o binario existir.
#
# Uso:
#   ./test/verify_external_port.sh
#   STB_DIR=/caminho/stb ./test/verify_external_port.sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FIX=$ROOT/test/fixtures/external_port
C0=${C0:-$ROOT/transpile/c/bin/lin_c0}
ZIGBIN=${ZIGBIN:-$ROOT/zig-out/bin/lin_native}
STB_DIR=${STB_DIR:-}

# goldens publicados (medidos em 2026-09-01: stb upstream compilado com cc, ORACLE
# python e os dois hosts da LinVM, todos independentes, todos iguais)
GATE_SCAN=899720538059731284
GATE_TOK=43
BND_SCAN=4780590326083434039
BND_TOK=12
# expectativa PUBLICADA no arquivo do caso de fronteira (o que o upstream mediu,
# NAO o que a fatia produz — e por isso que aquele mx_gate da 0)
UP_BND_SCAN=-1320994109422618346
UP_BND_TOK=8

if [ ! -x "$C0" ]; then
  printf 'verify_external_port: %s nao existe — construa com `make -C transpile/c c0`\n' "$C0" >&2
  exit 2
fi

LIN=$FIX/mx_stb_lin.lin
BND=$FIX/mx_stb_lin_boundary.lin
for f in "$LIN" "$BND" "$FIX/corpus.c" "$FIX/gen_fixture.py" "$FIX/ref_oracle.py"; do
  [ -f "$f" ] || { printf 'verify_external_port: falta %s\n' "$f" >&2; exit 2; }
done

pass=0
fail=0
skip=0

expect() {  # expect <rotulo> <trecho-esperado> <comando...>
  label=$1; want=$2; shift 2
  raw=$("$@" 2>&1); rc=$?
  got=$(printf '%s' "$raw" | tr '\n' '|')
  if [ $rc -ne 0 ]; then
    fail=$((fail + 1)); printf '  FAIL  %s (exit %d)\n        obtido: %s\n' "$label" "$rc" "$got"
    return
  fi
  case $got in
    *"$want"*) pass=$((pass + 1)); printf '  ok    %s\n' "$label" ;;
    *) fail=$((fail + 1)); printf '  FAIL  %s\n        esperado: %s\n        obtido:   %s\n' "$label" "$want" "$got" ;;
  esac
}

# expect_val <rotulo> <fn> <valor esperado> <arquivo.lin>
expect_val() {
  label=$1; fn=$2; want=$3; file=$4
  expect "$label" "fn=\"$fn\" value=$want" "$C0" vm "$file" "$fn"
}

# extrai steps=NNN de uma saida .result (para comparar Zig x C11)
steps_of() {  # steps_of <comando...>
  out=$("$@" 2>&1) || return 1
  printf '%s' "$out" | sed -n 's/.*steps=\([-0-9]*\).*/\1/p' | head -1
}

printf 'verify_external_port — port externo (stb clonado do GitHub) -> LIN\n'
printf '  binario ...... %s\n' "$C0"
printf '  host ......... %s\n' "$("$C0" --version 2>&1 | tr '\n' ' ')"
printf '  corpus ....... %s bytes (o teto do array do subconjunto e 256)\n' "$(wc -c < "$FIX/corpus.c" | tr -d ' ')"

printf '\n-- 1. o host C11 aceita o modulo e a cobertura e a publicada --\n'
expect "info: 9 fns, todas elegiveis" ".coverage{ total=9 eligible=9 rejected=0 }" \
       "$C0" info "$LIN"
expect "info: sem Zig no host" ".host{ engine=\"C11-lin_c0\" zig=false" \
       "$C0" info "$LIN"

printf '\n-- 2. goldens no host C11 (subconjunto LINVM-1/i64) --\n'
expect_val "mx_scan (fold do lexer)" mx_scan "$GATE_SCAN" "$LIN"
expect_val "mx_tokens" mx_tokens "$GATE_TOK" "$LIN"
expect_val "mx_gate == 1 (bate com o upstream)" mx_gate 1 "$LIN"

printf '\n-- 3. caso FORA da fatia: deve FALHAR de propósito --\n'
expect_val "boundary: mx_scan (valor da fatia)" mx_scan "$BND_SCAN" "$BND"
expect_val "boundary: mx_tokens (valor da fatia)" mx_tokens "$BND_TOK" "$BND"
expect_val "boundary: mx_gate == 0 (nao reproduz upstream)" mx_gate 0 "$BND"

printf '\n-- 4. paridade de contagem e de passos: C11 x Zig --\n'
if [ -x "$ZIGBIN" ]; then
  expect_val "Zig: mx_scan" mx_scan "$GATE_SCAN" "$LIN"
  expect_val "Zig: mx_gate" mx_gate 1 "$LIN"
  s_c0=$(steps_of "$C0" vm "$LIN" mx_scan)
  s_zg=$(steps_of "$ZIGBIN" vm "$LIN" mx_scan)
  if [ -n "$s_c0" ] && [ "$s_c0" = "$s_zg" ]; then
    pass=$((pass + 1)); printf '  ok    steps identicos nos dois hosts (steps=%s)\n' "$s_c0"
  else
    fail=$((fail + 1)); printf '  FAIL  steps divergem: C11=%s Zig=%s\n' "$s_c0" "$s_zg"
  fi
else
  skip=$((skip + 1)); printf '  SKIP  sem %s — a perna Zig NAO conta como passada\n' "$ZIGBIN"
fi

printf '\n-- 5. rota congelada: fonte -> LINBC1 -> executa da imagem --\n'
expect "roundtrip CONSENSUS (sem Zig)" "status=\"CONSENSUS\"" \
       "$C0" roundtrip "$LIN" mx_gate

printf '\n-- 6. oraculo independente (Python) re-deriva os goldens --\n'
if command -v python3 >/dev/null 2>&1; then
  expect "oracle: fold do corpus" "fold=$GATE_SCAN" \
         python3 "$FIX/ref_oracle.py" "$FIX/corpus.c"
  expect "oracle: tokens do corpus" "tokens=$GATE_TOK" \
         python3 "$FIX/ref_oracle.py" "$FIX/corpus.c"
  expect "oracle: fold do boundary" "fold=$BND_SCAN" \
         python3 "$FIX/ref_oracle.py" "$FIX/boundary.c"
else
  skip=$((skip + 1)); printf '  SKIP  sem python3 — oraculo nao rodou\n'
fi

printf '\n-- 7. os .lin conferem com o gerador (nada editado a mao) --\n'
TMPD=$(mktemp -d) || { printf '  FAIL  mktemp\n'; exit 1; }
trap 'rm -rf "$TMPD"' EXIT INT TERM
( cd "$FIX" && python3 gen_fixture.py corpus.c "$TMPD/g.lin" "$GATE_SCAN" "$GATE_TOK" >/dev/null \
    && python3 gen_fixture.py boundary.c "$TMPD/b.lin" "$UP_BND_SCAN" "$UP_BND_TOK" >/dev/null ) \
  && cmp -s "$TMPD/g.lin" "$LIN" && cmp -s "$TMPD/b.lin" "$BND" \
  && { pass=$((pass + 1)); printf '  ok    mx_stb_lin.lin e mx_stb_lin_boundary.lin reproduziveis\n'; } \
  || { fail=$((fail + 1)); printf '  FAIL  gerador != .lin versionados — rode gen_fixture.py\n'; }

printf '\n-- 8. lexer REAL de terceiro (upstream clonado), se STB_DIR for dado --\n'
if [ -n "$STB_DIR" ] && [ -f "$STB_DIR/stb_c_lexer.h" ]; then
  if cc -O1 -I"$STB_DIR" -o "$TMPD/mini_lex" "$FIX/mini_lex.c" 2>"$TMPD/cc.log"; then
    expect "stb upstream: fold identico ao port" "fold=$GATE_SCAN" \
           "$TMPD/mini_lex" "$FIX/corpus.c"
    expect "stb upstream: tokens identicos" "tokens=$GATE_TOK" \
           "$TMPD/mini_lex" "$FIX/corpus.c"
  else
    fail=$((fail + 1)); printf '  FAIL  compilacao do harness upstream:\n'
    sed 's/^/        /' "$TMPD/cc.log" | head -5
  fi
else
  skip=$((skip + 1))
  printf '  SKIP  STB_DIR vazio — para a perna de terceiro:\n'
  printf '          git clone --depth 1 https://github.com/nothings/stb && STB_DIR=$PWD/stb ./test/verify_external_port.sh\n'
fi

printf '\n'
if [ $fail -ne 0 ]; then
  printf 'VERIFY-EXTERNAL-PORT: FAIL (%d falhas, %d ok, %d skip)\n' "$fail" "$pass" "$skip"
  exit 1
fi
printf 'VERIFY-EXTERNAL-PORT: PASS (%d verificacoes, %d skip; port LIN == lexer C de terceiro)\n' "$pass" "$skip"
