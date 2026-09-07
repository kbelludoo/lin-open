#!/bin/sh
# verify_c0.sh — gate do Compilador 0 da LinVM num ambiente SEM Zig.
#
# O que ele mede: o host C11 (`transpile/c/bin/lin_c0`) compila os módulos LIN
# do repositório e tem que reproduzir, bit a bit, os valores publicados pelos
# gates do Stage0 Zig (docs/P1_LINVM_SELFHOST.rulel §3, docs/R2B_...rulel,
# docs/V1_LINBC1_HOST_EVIDENCE.rulel §2, docs/P2_CORPUS_HYGIENE.rulel §2).
#
# Nada aqui chama `zig`, `zig build`, `lin_native` ou OpenCL. Só `cc` e shell.
# Saída não-zero em qualquer divergência — fail-closed, como o resto do repo.
#
# Uso:  ./test/verify_c0.sh [caminho-para-lin_c0]
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=${1:-$ROOT/transpile/c/bin/lin_c0}
if [ ! -x "$C0" ]; then
  printf 'verify_c0: %s não existe — construa com `make -C transpile/c c0`\n' "$C0" >&2
  exit 2
fi

pass=0
fail=0

# expect <rótulo> <saída-esperada> <comando...>
expect() {
  label=$1; want=$2; shift 2
  got=$("$@" 2>&1 | tr '\n' '|')
  case $got in
    *"$want"*) pass=$((pass + 1)); printf '  ok    %s\n' "$label" ;;
    *) fail=$((fail + 1))
       printf '  FAIL  %s\n        esperado: %s\n        obtido:   %s\n' "$label" "$want" "$got" ;;
  esac
}

# expect_fail <rótulo> <trecho-esperado> <comando...>  (o comando DEVE falhar)
expect_fail() {
  label=$1; want=$2; shift 2
  raw=$("$@" 2>&1); rc=$?
  got=$(printf '%s' "$raw" | tr '\n' '|')
  if [ "$rc" -eq 0 ]; then
    fail=$((fail + 1)); printf '  FAIL  %s — aceito onde devia recusar (rc=0)\n' "$label"; return
  fi
  case $got in
    *"$want"*) pass=$((pass + 1)); printf '  ok    %s (recusada em falso-fechado)\n' "$label" ;;
    *) fail=$((fail + 1))
       printf '  FAIL  %s\n        esperado recusa: %s\n        obtido:           %s\n' "$label" "$want" "$got" ;;
  esac
}

printf '=== COMPILER 0 = LinVM (host C11) — gate sem Zig ===\n'
printf '  binário ...... %s\n' "$C0"
if command -v zig >/dev/null 2>&1; then
  printf '  zig no PATH .. SIM (este gate roda mesmo assim, sem usá-lo)\n'
else
  printf '  zig no PATH .. NÃO (nenhum Zig é necessário abaixo)\n'
fi
printf '  host ......... %s\n' "$("$C0" --version | tr '\n' ' ')"

printf '\n-- cobertura publicada (docs/P1_LINVM_SELFHOST.rulel §3) --\n'
expect "linvm_selfhost: 21/21 fns status=OK" \
       ".coverage{ total=21 eligible=21 rejected=0 }" \
       "$C0" info "$ROOT/src/linvm_selfhost.lin"

printf '\n-- goldens bit-exact do Stage0 --\n'
expect "vms_gate (33 opcodes, 32 sels, 88 sweeps)" \
       ".result{ fn=\"vms_gate\" value=1 steps=8511500 }" \
       "$C0" vm "$ROOT/src/linvm_selfhost.lin" vms_gate
expect "lb_selfhash_fold == fold publicado do loader C11" \
       ".result{ fn=\"lb_selfhash_fold\" value=-178321285347216732" \
       "$C0" vm "$ROOT/src/lin_linbc_emit.lin" lb_selfhash_fold
expect "lb_selftest" \
       ".result{ fn=\"lb_selftest\" value=1 steps=" \
       "$C0" vm "$ROOT/src/lin_linbc_emit.lin" lb_selftest

printf '\n-- corpus GPU do P2 (docs/P2_CORPUS_HYGIENE.rulel §2) --\n'
CORPUS="$ROOT/test/corpus/gpu_parallel_map_kernels.lin"
expect "cobertura do corpus" \
       ".coverage{ total=4 eligible=4 rejected=0 }" \
       "$C0" info "$CORPUS"
expect "test_gpu_known_vectors" \
       ".result{ fn=\"test_gpu_known_vectors\" value=1 steps=49 }" \
       "$C0" vm "$CORPUS" test_gpu_known_vectors
expect "gpu_map_bitfold 8" \
       ".result{ fn=\"gpu_map_bitfold\" value=72 steps=12 }" \
       "$C0" vm "$CORPUS" gpu_map_bitfold 8
expect "gpu_map_affine 21" \
       ".result{ fn=\"gpu_map_affine\" value=43 steps=" \
       "$C0" vm "$CORPUS" gpu_map_affine 21
expect "gpu_map_mix 5" \
       ".result{ fn=\"gpu_map_mix\" value=8 steps=" \
       "$C0" vm "$CORPUS" gpu_map_mix 5

printf '\n-- fonte -> imagem LINBC1 -> loader -> execução (mesmo resultado) --\n'
expect "roundtrip: exec direto == exec via imagem" \
       ".verdict{ status=\"CONSENSUS\"" \
       "$C0" roundtrip "$ROOT/src/linvm_selfhost.lin" vms_udiv 10 3
H1=$("$C0" image "$ROOT/src/linvm_selfhost.lin" | sed -n 's/.*img="\([0-9a-f]*\)".*/\1/p')
H2=$("$C0" image "$ROOT/src/linvm_selfhost.lin" | sed -n 's/.*img="\([0-9a-f]*\)".*/\1/p')
if [ -n "$H1" ] && [ "$H1" = "$H2" ]; then
  pass=$((pass + 1)); printf '  ok    imagem é byte-reproduzível (img_sha256=%s…)\n' "$(printf %s "$H1" | cut -c1-16)"
else
  fail=$((fail + 1)); printf '  FAIL  imagem não reproduz: %s vs %s\n' "$H1" "$H2"
fi

printf '\n-- fail-closed e extensões C11 do frontend --\n'
TMP=$(mktemp -d)
printf '!f(a: int) -> int {\n  ^a / 2;\n}\n' > "$TMP/div.lin"
expect "divisão inteira C11" ".result{ fn=\"f\" value=2" "$C0" vm "$TMP/div.lin" f 4
printf '!f() -> int {\n  ^9223372036854775808;\n}\n' > "$TMP/range.lin"
expect_fail "literal fora de i64" "VM_REJ_LITERAL_RANGE" "$C0" vm "$TMP/range.lin" f
printf '!f(x: nope) -> int {\n  ^0;\n}\n' > "$TMP/type.lin"
expect_fail "parâmetro não-inteiro" "VM_REJ_PARAM_NOT_INT" "$C0" vm "$TMP/type.lin" f
printf '!ok(a: int) -> int {\n  ^a;\n}\n!bad(x: int) -> int {\n  ^\"unsupported\";\n}\n' > "$TMP/mixed.lin"
expect_fail "módulo com fn rejeitada não vira imagem" "C0_REJ_MODULE_NOT_PURE" "$C0" image "$TMP/mixed.lin"
rm -rf "$TMP"

printf '\n-- varredura de robustez: todo .lin do repo passa pelo front-end --\n'
# Não asserts de valor (a maior parte do corpus usa construções fora do
# subconjunto e DEVE ser recusada). As asserts são: nenhuma execução morre por
# sinal e a saída é sempre um registro LIN_VM bem-formado. Fail-closed, não
# crash — e SAN=1 refaz a varredura com ASan+UBSan.
SAN=${SAN:-}
CC=${CC:-cc}
SWEEP_TMP=""
if [ -n "$SAN" ]; then
  SWEEP_TMP=$(mktemp -d)/lin_c0_san
  $CC -O1 -g -std=c11 -fsanitize=address,undefined -fno-sanitize-recover=all \
      -I "$ROOT/transpile/c" -I "$ROOT/transpile/c/lin_c" -o "$SWEEP_TMP" \
      "$ROOT/transpile/c/tool/lin_c0.c" "$ROOT/transpile/c/tool/lin_c0_front.c" \
      "$ROOT/transpile/c/tool/lin_c0_check.c" \
      "$ROOT"/transpile/c/lin_c/*.c || { printf '  FAIL  build com sanitizers\n'; exit 1; }
  printf '  sanitizers ..... ASan+UBSan ativos na varredura\n'
  C0RUN=$SWEEP_TMP
else
  C0RUN=$C0
fi
files=0; crashes=0; malformed=0; covered=0; tot_fn=0; ok_fn=0
for f in $(find "$ROOT/src" "$ROOT/examples" "$ROOT/test/corpus" -name '*.lin' | sort); do
  files=$((files + 1))
  out=$("$C0RUN" info "$f" 2>&1); rc=$?
  if [ "$rc" -ge 128 ]; then crashes=$((crashes + 1)); printf '  FAIL  sinal %s em %s\n' "$rc" "$f"; fi
  case $out in
    @RULEL:LIN_VM:1.0.0*) : ;;
    *) malformed=$((malformed + 1)); printf '  FAIL  saída malformada em %s\n' "$f" ;;
  esac
  line=$(printf '%s' "$out" | sed -n 's/.*total=\([0-9]*\) eligible=\([0-9]*\) rejected=\([0-9]*\).*/\1 \2/p' | head -1)
  if [ -n "$line" ]; then
    t=$(printf '%s' "$line" | cut -d' ' -f1); e=$(printf '%s' "$line" | cut -d' ' -f2)
    tot_fn=$((tot_fn + t)); ok_fn=$((ok_fn + e))
    [ "$t" = "$e" ] && [ "$t" != 0 ] && covered=$((covered + 1))
  fi
done
[ -n "$SWEEP_TMP" ] && rm -f "$SWEEP_TMP"
printf '  corpus ......... %d arquivos .lin, %d funções, %d elegíveis (%d com cobertura 100%%)\n' \
       "$files" "$tot_fn" "$ok_fn" "$covered"
if [ "$crashes" -eq 0 ] && [ "$malformed" -eq 0 ]; then
  pass=$((pass + 1)); printf '  ok    varredura sem crash e com saída sempre bem-formada\n'
else
  fail=$((fail + 1)); printf '  FAIL  varredura: %d crashes, %d saídas malformadas\n' "$crashes" "$malformed"
fi

printf '\n=== LINVM0-NOZIG: %d ok, %d falhas ===\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
printf 'COMPILER_0=linvm-host-C11 (subconjunto LINVM-1/i64) — ver docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel\n'
