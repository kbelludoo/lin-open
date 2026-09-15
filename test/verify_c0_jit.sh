#!/bin/sh
# ==============================================================================
# test/verify_c0_jit.sh — Gate de Verificação do JIT em Memória C11 do Compiler 0
#
# Valida a compilação 100% em memória RAM via libtcc:
#   1. Execução direta via JIT (`lin_c0 jit`)
#   2. Consenso estrito bit-a-bit contra a LinVM interpretada (`lin_c0 roundtrip-jit`)
#   3. Zero arquivos temporários criados em disco
#
# Sem nenhuma dependência de Zig. Fail-closed em qualquer divergência.
# ==============================================================================
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=${1:-$ROOT/transpile/c/bin/lin_c0}
if [ ! -x "$C0" ]; then
  printf 'verify_c0_jit: %s não existe — construa com `make -C transpile/c c0`\n' "$C0" >&2
  exit 2
fi

pass=0
fail=0

expect() {
  label=$1; want=$2; shift 2
  got=$("$@" 2>&1 | tr '\n' '|')
  case $got in
    *"$want"*) pass=$((pass + 1)); printf '  ok    %s\n' "$label" ;;
    *) fail=$((fail + 1))
       printf '  FAIL  %s\n        esperado: %s\n        obtido:   %s\n' "$label" "$want" "$got" ;;
  esac
}

printf '=== COMPILER 0 JIT: COMPILAÇÃO 100%% EM MEMÓRIA RAM VIA LIBTCC ===\n'
printf '  binário ...... %s\n' "$C0"
printf '  modo ......... C11 Native JIT (0 disk touching, pure heap)\n\n'

printf -- '-- 1. Módulos de Teste e Expressões Aritméticas --\n'
CORPUS="$ROOT/test/corpus/gpu_parallel_map_kernels.lin"
expect "jit: gpu_map_affine 21 == 43" \
       ".result{ fn=\"gpu_map_affine\" value=43" \
       "$C0" jit "$CORPUS" gpu_map_affine 21

expect "roundtrip-jit: gpu_map_affine 21 (LinVM == JIT)" \
       ".verdict{ status=\"CONSENSUS\" fn=\"gpu_map_affine\" value=43" \
       "$C0" roundtrip-jit "$CORPUS" gpu_map_affine 21

expect "roundtrip-jit: gpu_map_bitfold 8 == 72" \
       ".verdict{ status=\"CONSENSUS\" fn=\"gpu_map_bitfold\" value=72" \
       "$C0" roundtrip-jit "$CORPUS" gpu_map_bitfold 8

expect "roundtrip-jit: gpu_map_mix 5 == 8" \
       ".verdict{ status=\"CONSENSUS\" fn=\"gpu_map_mix\" value=8" \
       "$C0" roundtrip-jit "$CORPUS" gpu_map_mix 5

expect "roundtrip-jit: test_gpu_known_vectors == 1" \
       ".verdict{ status=\"CONSENSUS\" fn=\"test_gpu_known_vectors\" value=1" \
       "$C0" roundtrip-jit "$CORPUS" test_gpu_known_vectors

printf '\n-- 2. Motor de Auto-Hospedagem e Instruções LinVM (33 opcodes) --\n'
SELFHOST="$ROOT/src/linvm_selfhost.lin"
expect "roundtrip-jit: vms_udiv 10 3 == 3" \
       ".verdict{ status=\"CONSENSUS\" fn=\"vms_udiv\" value=3" \
       "$C0" roundtrip-jit "$SELFHOST" vms_udiv 10 3

expect "roundtrip-jit: vms_gate (33 opcodes, 88 sweeps, 8.5M steps) == 1" \
       ".verdict{ status=\"CONSENSUS\" fn=\"vms_gate\" value=1" \
       "$C0" roundtrip-jit "$SELFHOST" vms_gate

printf '\n-- 3. Emissor de Bytecode e Hashing Canônico --\n'
EMIT="$ROOT/src/lin_linbc_emit.lin"
expect "roundtrip-jit: lb_selfhash_fold == -178321285347216732" \
       ".verdict{ status=\"CONSENSUS\" fn=\"lb_selfhash_fold\" value=-178321285347216732" \
       "$C0" roundtrip-jit "$EMIT" lb_selfhash_fold

expect "roundtrip-jit: lb_selftest == 1" \
       ".verdict{ status=\"CONSENSUS\" fn=\"lb_selftest\" value=1" \
       "$C0" roundtrip-jit "$EMIT" lb_selftest

printf '\n-- 4. Motor AMM Uniswap v2 --\n'
AMM="$ROOT/examples/defi_settlement_proof/lin_amm_settler_app.lin"
expect "roundtrip-jit: amm_settler_app_gate == 1" \
       ".verdict{ status=\"CONSENSUS\" fn=\"amm_settler_app_gate\" value=1" \
       "$C0" roundtrip-jit "$AMM" amm_settler_app_gate

printf '\n-- 5. Verificação em Lote de Módulos (jit-verify) --\n'
expect "jit-verify: corpus map kernels (4/4 fns)" \
       ".summary{ total=4 compiled_and_run=4 }" \
       "$C0" jit-verify "$CORPUS"

printf '\n-- 6. Auditoria de Disco: Zero Arquivos Criados durante JIT --\n'
BEFORE=$(ls -1 /tmp | wc -l)
"$C0" jit "$CORPUS" gpu_map_affine 21 > /dev/null
AFTER=$(ls -1 /tmp | wc -l)
if [ "$BEFORE" -eq "$AFTER" ]; then
  pass=$((pass + 1))
  printf '  ok    zero arquivos criados em /tmp (compilação 100%% em memória RAM)\n'
else
  fail=$((fail + 1))
  printf '  FAIL  arquivos foram criados em /tmp durante compilação JIT!\n'
fi

printf '\n====================================================================\n'
printf '=== LIN-C0-JIT GATE: %d ok, %d falhas ===\n' "$pass" "$fail"
printf '====================================================================\n'

if [ "$fail" -eq 0 ]; then
  exit 0
else
  exit 1
fi
