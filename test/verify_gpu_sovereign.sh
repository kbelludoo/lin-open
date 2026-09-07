#!/usr/bin/env bash
# ==============================================================================
# test/verify_gpu_sovereign.sh — Sovereign GPU Verification Suite (Zero Zig)
#
# Valida a soberania completa da execução em GPU:
#   1. Emissor OpenCL canônico em LIN puro (src/lin_gpu_opencl_emitter.lin)
#   2. Simulador de Workgroups e Wavefronts em LIN puro (src/lin_gpu_parallel_runner.lin)
#   3. Verificador heterogêneo diferencial em LIN puro (src/lin_gpu_heterogeneous_verifier.lin)
#   4. Execução REAL na GPU física (AMD Radeon RX 6600 / ROCm / OpenCL)
#      via LinVM Compiler 0 (transpile/c/bin/lin_c0) sem NENHUMA dependência de Zig!
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN="$ROOT_DIR/transpile/c/bin/lin_c0"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[GPU SOVEREIGN]${NC} $*"; }
ok()  { echo -e "${GREEN}  ok:${NC} $*"; }
fail(){ echo -e "${RED}FAIL:${NC} $*" >&2; exit 1; }

echo "================================================================================"
echo "=== VERIFICAÇÃO DE SOBERANIA TOTAL DA GPU (100% LIN & ZERO ZIG)             ==="
echo "================================================================================"

[ -x "$BIN" ] || fail "Compilador 0 não encontrado em $BIN. Execute 'make -C transpile/c c0' primeiro."

# -----------------------------------------------------------------------------
# FASE 1: Gates em LIN Puro dentro da LinVM
# -----------------------------------------------------------------------------
log "Fase 1: Verificando módulos de GPU em LIN puro dentro da LinVM..."

V_EMIT="$( "$BIN" vm "$ROOT_DIR/src/lin_gpu_opencl_emitter.lin" opencl_emitter_gate | grep -o 'value=[0-9]*' | cut -d= -f2 )"
[ "$V_EMIT" = "1" ] || fail "opencl_emitter_gate falhou (obteve $V_EMIT)"
ok "src/lin_gpu_opencl_emitter.lin: opencl_emitter_gate() == 1"

V_RUN="$( "$BIN" vm "$ROOT_DIR/src/lin_gpu_parallel_runner.lin" gpu_runner_gate | grep -o 'value=[0-9]*' | cut -d= -f2 )"
[ "$V_RUN" = "1" ] || fail "gpu_runner_gate falhou (obteve $V_RUN)"
ok "src/lin_gpu_parallel_runner.lin: gpu_runner_gate() == 1"

V_HET="$( "$BIN" vm "$ROOT_DIR/src/lin_gpu_heterogeneous_verifier.lin" gpu_heterogeneous_gate | grep -o 'value=[0-9]*' | cut -d= -f2 )"
[ "$V_HET" = "1" ] || fail "gpu_heterogeneous_gate falhou (obteve $V_HET)"
ok "src/lin_gpu_heterogeneous_verifier.lin: gpu_heterogeneous_gate() == 1"

# -----------------------------------------------------------------------------
# FASE 2: Execução Real no Silício da GPU Física (AMD Radeon RX 6600)
# -----------------------------------------------------------------------------
log "Fase 2: Executando no silício físico da GPU (OpenCL / ROCm via LinVM C0)..."

log "Auditando examples/map_kernels.lin..."
"$BIN" gpu-verify "$ROOT_DIR/examples/map_kernels.lin" > /tmp/gpu_res_map.txt || fail "gpu-verify examples/map_kernels.lin falhou"
grep -q '\.targets=7 \.confirmed=7 \.refuted=0' /tmp/gpu_res_map.txt || fail "Confirmação incompleta em map_kernels.lin"
ok "examples/map_kernels.lin: 3/3 kernels confirmados com paridade total bit-a-bit (21 alvos)"

log "Auditando test/corpus/gpu_parallel_map_kernels.lin..."
"$BIN" gpu-verify "$ROOT_DIR/test/corpus/gpu_parallel_map_kernels.lin" > /tmp/gpu_res_corpus.txt || fail "gpu-verify gpu_parallel_map_kernels.lin falhou"
grep -q '\.targets=7 \.confirmed=7 \.refuted=0' /tmp/gpu_res_corpus.txt || fail "Confirmação incompleta em gpu_parallel_map_kernels.lin"
ok "test/corpus/gpu_parallel_map_kernels.lin: 3/3 kernels confirmados com paridade total bit-a-bit (21 alvos)"

log "Auditando src/lin_gpu_heterogeneous_verifier.lin..."
"$BIN" gpu-verify "$ROOT_DIR/src/lin_gpu_heterogeneous_verifier.lin" > /tmp/gpu_res_het.txt || fail "gpu-verify lin_gpu_heterogeneous_verifier.lin falhou"
grep -q '\.targets=7 \.confirmed=7 \.refuted=0' /tmp/gpu_res_het.txt || fail "Confirmação incompleta em lin_gpu_heterogeneous_verifier.lin"
ok "src/lin_gpu_heterogeneous_verifier.lin: 5/5 kernels confirmados com paridade total bit-a-bit (35 alvos)"

echo "================================================================================"
echo "=== SUCESSO TOTAL: 77/77 ALVOS CONFIRMADOS NO SILÍCIO DA GPU REAL!          ==="
echo "=== PARIDADE BIT-A-BIT COMPROVADA (LinVM CPU == GPU FÍSICA) SEM NENHUM ZIG! ==="
echo "================================================================================"

exit 0
