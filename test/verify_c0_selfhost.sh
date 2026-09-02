#!/usr/bin/env bash
# test/verify_c0_selfhost.sh — o compiler0 escrito EM LIN roda na LinVM sem Zig.
#
# O que esta porta prova (e nada mais):
#   1. o front-end de #46 (`src/linvm0_compiler/*.lin` — lexer, avaliador de
#      expressões e lowerer em LIN) compila e executa sob o host C11 `lin_c0`, e
#      bate bit a bit com os oráculos independentes (`reference_tokenize.py`,
#      `reference_lower.py`);
#   2. o front-end pode ser CONGELADO como imagem LINBC1 e REEXECUTADO a partir
#      da imagem na LinVM, com resultado e custo idênticos à rota-fonte;
#   3. auto-aplicação (passo B2): o lexer em LIN tokeniza o TEXTO do próprio
#      front-end (256 primeiros bytes — limite VM_MAX_ARR_LEN da ISA), módulo
#      gerado por `test/lin0_selflex.py`, e o `lex_gate()` interno continua 1;
#   4. as imagens e a raiz agregada batem com `compiler0_manifest.rulel`.
# Com `LIN_C0=<binário com -fsanitize=address,undefined>` as 30 verificações também
# passam (medido em 2026-09-01) — cobre o `run` de imagem sob sanitizers.
# Zig em nenhum passo. O que continua no Stage0: `check`/`lint` (se houver
# Stage0, este script o usa como oracle extra) e o ponto fixo C0=C1=C2.
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1

LIN_C0=${LIN_C0:-transpile/c/bin/lin_c0}
LIN_NATIVE=${LIN_NATIVE:-zig-out/bin/lin_native}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ pass=$((pass + 1)); echo "ok   $1"; }
ko(){ fail=$((fail + 1)); echo "NOK  $1"; }

# extrai "value steps" de uma linha @RULEL:LIN_VM_RUN
result(){ sed -n 's/\.result{ fn="[^"]*" value=\([-0-9]*\) steps=\([0-9]*\) }.*/\1 \2/p'; }
vm_run(){ "$LIN_C0" vm "$1" "$2" | result; }
img_run(){ "$LIN_C0" run "$1" "$2" | result; }
gate_of(){ case "$1" in
  lin_lexer_selfhost) echo lex_gate ;;
  lin_expr_eval)      echo xver_gate ;;
  lin_lower_selfhost) echo low_gate ;;
  *) echo "" ;;
esac; }

if [ ! -x "$LIN_C0" ]; then
  echo "--- 0. host ausente: construindo ($LIN_C0) ---"
  build=$(make -C transpile/c c0 2>&1); rc=$?
  [ "$rc" -eq 0 ] || { echo "NOK  build do host C11: $(echo "$build" | grep 'error:' | head -2)"; exit 1; }
fi
[ -x "$LIN_C0" ] || { echo "NOK  host não encontrado ($LIN_C0)"; exit 1; }
echo "--- 0. host C11 ($("$LIN_C0" --version | tr -d '\n')) ---"
if command -v zig >/dev/null 2>&1; then
  echo "     nota: este ambiente TEM zig; nenhum passo abaixo o usa"
else
  ok "ambiente sem zig no PATH (é exatamente o caso desta porta)"
fi

echo "--- 1. front-end em LIN compilado e executado pela LinVM (rota fonte) ---"
LEX=src/linvm0_compiler/lin_lexer_selfhost.lin
EVL=src/linvm0_compiler/lin_expr_eval.lin
LOW=src/linvm0_compiler/lin_lower_selfhost.lin
gate(){ # gate <mod> <fn> <value esperado> <steps esperado>
  local got rc; got=$(vm_run "$1" "$2"); rc=$?
  [ "$rc" -eq 0 ] || { ko "vm $1 $2 (rc=$rc)"; return; }
  if [ "$got" = "$3 $4" ]; then ok "vm $(basename "$1") $2 -> value=$3 steps=$4"
  else ko "vm $(basename "$1") $2 -> '$got' (esperado '$3 $4')"; fi
}
gate "$LEX" lex_gate 1 10097
gate "$LEX" lex_scan_embedded 1371904279658369433 5653
gate "$LEX" lex_count_embedded 20 4424
gate "$EVL" xver_gate 1 12445
gate "$LOW" low_gate 1 4386

echo "--- 2. oráculos independentes (#46) ---"
if command -v python3 >/dev/null 2>&1; then
  out=$(python3 src/linvm0_compiler/reference_tokenize.py 2>&1 | tr '\n' ' '); rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q 'num_tokens=20' \
     && echo "$out" | grep -q 'checksum=1371904279658369433'; then
    ok "reference_tokenize.py == LIN-na-LinVM (tokens=20 checksum=1371904279658369433)"
  else
    ko "reference_tokenize.py diverge do módulo LIN: $out"
  fi
  out=$(python3 src/linvm0_compiler/reference_lower.py 2>&1 | grep code_sha256 | tr -d ' '); rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q 'fb10ce577eb15188e0590e6fb03990ad13670befb08c55e0930cd5b187e2d46e'; then
    ok "reference_lower.py == consenso Zig/C11 publicado (code_sha256 fb10ce57…)"
  else
    ko "reference_lower.py diverge do fold publicado: $out"
  fi
else
  echo "     check/lint NÃO verificados (sem python3 para os oráculos)"
  ko "python3 ausente: oráculos não conferidos"
fi

echo "--- 3. congelar o front-end como imagem LINBC1 + executar da imagem ---"
for m in "$LEX" "$EVL" "$LOW"; do
  b=$(basename "$m" .lin); fn=$(gate_of "$b"); img="$TMP/$b.linbc"
  imgout=$("$LIN_C0" image "$m" -o "$img" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] || [ ! -f "$img" ]; then ko "$b: image -> $img falhou (rc=$rc)"; continue; fi
  "$LIN_C0" image "$m" -o "$TMP/$b.b.linbc" >/dev/null 2>&1
  if cmp -s "$img" "$TMP/$b.b.linbc"; then
    ok "$b: imagem reproduzível byte a byte ($(wc -c <"$img") B)"
  else
    ko "$b: imagem não reproduzível entre duas execuções"
  fi
  sha=$(echo "$imgout" | sed -n 's/.*img="\([0-9a-f]*\)".*/\1/p')
  bytes=$(echo "$imgout" | sed -n 's/.*\.image{ bytes=\([0-9]*\).*/\1/p')
  fold=$(echo "$imgout" | sed -n 's/.*fold=\([-0-9]*\).*/\1/p')
  [ "$bytes" = "$(wc -c <"$img")" ] && [ -n "$sha" ] \
    && ok "$b: digest publicado img=$bytes B sha256=${sha:0:16}… fold=$fold" \
    || ko "$b: digest/bytes publicados não batem com o arquivo"
  s_r=$(vm_run "$m" "$fn"); i_r=$(img_run "$img" "$fn")
  if [ -n "$i_r" ] && [ "$s_r" = "$i_r" ]; then
    ok "$b: $fn idêntico pelas duas rotas (fonte e imagem): value/steps=$i_r"
  else
    ko "$b: rota imagem '$i_r' != rota fonte '$s_r'"
  fi
done

echo "--- 4. manifesto das imagens (compiler0_manifest.rulel) ---"
out=$(python3 test/verify_compiler0_manifest.py 2>&1); rc=$?
echo "$out" | sed 's/^/     /'
if [ "$rc" -eq 0 ]; then ok "imagens + raiz agregada + self-lex pinados batem"; else ko "manifesto de imagens divergiu (rc=$rc)"; fi

echo "--- 5. auto-aplicação: o lexer LIN sobre o texto do front-end (cap 256 B) ---"
for t in "$LEX" "$EVL" "$LOW"; do
  b=$(basename "$t" .lin); gen="$TMP/selflex_$b.lin"
  meta=$(python3 test/lin0_selflex.py "$t" --out "$gen" 2>&1); rc=$?
  if [ "$rc" -ne 0 ]; then ko "lin0_selflex $t (rc=$rc): $(echo "$meta" | head -1)"; continue; fi
  want=$(echo "$meta" | sed -n 's/^checksum=\([-0-9]*\)$/\1/p')
  ntok=$(echo "$meta" | sed -n 's/^tokens=\([0-9]*\)$/\1/p')
  got=$(vm_run "$gen" lex_scan_embedded)
  if [ "$(echo "$got" | cut -d' ' -f1)" = "$want" ]; then
    ok "$b: lexer-LIN == oráculo sobre o texto do próprio fonte (checksum=$want)"
  else
    ko "$b: lexer-LIN '$got' != oráculo '$want'"
  fi
  cnt=$(vm_run "$gen" lex_count_embedded)
  [ "$(echo "$cnt" | cut -d' ' -f1)" = "$ntok" ] \
    && ok "$b: contagem de tokens bate ($ntok)" || ko "$b: contagem '$cnt' != '$ntok'"
  g=$(vm_run "$gen" lex_gate)
  if [ -n "$g" ] && [ "$(echo "$g" | cut -d' ' -f1)" = "1" ]; then
    ok "$b: lex_gate() do módulo gerado == 1 (auto-validação dentro da VM, $(echo "$g" | cut -d' ' -f2) passos)"
  else
    ko "$b: lex_gate() do módulo gerado != 1 ('$g')"
  fi
  "$LIN_C0" image "$gen" -o "$TMP/selflex_$b.linbc" >/dev/null 2>&1
  gi=$(img_run "$TMP/selflex_$b.linbc" lex_scan_embedded)
  if [ -n "$gi" ] && [ "$gi" = "$got" ]; then
    ok "$b: self-lex também roda a partir da IMAGEM congelada"
  else
    ko "$b: rota imagem do self-lex ('$gi') != rota fonte ('$got')"
  fi
done

echo "--- 6. oracle Stage0 quando existir (bônus, não precondição) ---"
if [ ! -x "$LIN_NATIVE" ]; then
  echo "     check/lint NÃO verificados (Stage0 ausente: $LIN_NATIVE)"
  echo "     nota: com Zig disponível, LIN_NATIVE=<caminho> cruza as rotas e roda check/lint"
else
  for m in "$LEX" "$EVL" "$LOW"; do
    fn=$(gate_of "$(basename "$m" .lin)")
    zv=$("$LIN_NATIVE" vm "$m" "$fn" 2>&1 | sed -n 's/.*value=\([-0-9]*\) steps=.*/\1/p')
    cv=$("$LIN_C0" vm "$m" "$fn" 2>&1 | sed -n 's/.*value=\([-0-9]*\) steps=.*/\1/p')
    if [ -n "$zv" ] && [ "$zv" = "$cv" ]; then ok "zig vm $(basename "$m") $fn == C11 vm (value=$zv)"
    else ko "zig vs C11 em $m $fn (zig='$zv' c11='$cv')"; fi
    "$LIN_NATIVE" check "$m" >/dev/null 2>&1 && ok "Stage0 check $(basename "$m")" || ko "Stage0 check $(basename "$m")"
    "$LIN_NATIVE" lint "$m"  >/dev/null 2>&1 && ok "Stage0 lint $(basename "$m")"  || ko "Stage0 lint $(basename "$m")"
  done
fi

echo
if [ "$fail" -ne 0 ]; then echo "C0-SELFHOST: FAIL ($fail de $((pass + fail)))"; exit 1; fi
echo "C0-SELFHOST: PASS ($pass verificações, sem Zig — front-end LIN roda na LinVM, congela em LINBC1 e se aplica ao próprio texto)"
