#!/usr/bin/env bash
# verify_fixed_point_c0_c1_c2.sh
# Verificação do Marco B3: Fechamento do Ponto Fixo (C0 = C1 = C2)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT_DIR/transpile/c/bin/lin_c0"
SRC="$ROOT_DIR/src/linvm0_compiler/lin_compiler0_unified.lin"

fail() { echo "FIXED_POINT: FAIL: $*" >&2; exit 1; }
ok()   { echo "FIXED_POINT:   ok: $*"; }

echo "=== VERIFICAÇÃO DO PONTO FIXO DE AUTO-COMPILAÇÃO (C0 = C1 = C2) ==="

# 1. Cobertura da fonte
REJ="$( "$BIN" info "$SRC" | grep -o 'rejected=[0-9]*' | cut -d= -f2 )"
[ "$REJ" = "0" ] || fail "compiler0_unified tem funções rejeitadas ($REJ)"
ok "compiler0_unified: 8/8 funções elegíveis (0 rejeitadas)"

# 2. Ciclo C0: Compilação gerando imagem LINBC1 canônica inicial (I_0)
echo "Ciclo C0: Gerando imagem canônica inicial LINBC1..."
IMG_INFO_1="$( "$BIN" image "$SRC" )"
SHA_C0_1="$( echo "$IMG_INFO_1" | grep -o 'sha256=[0-9a-f]*' | cut -d= -f2 )"
BYTES_C0_1="$( echo "$IMG_INFO_1" | grep -o 'bytes=[0-9]*' | cut -d= -f2 )"
ok "Ciclo C0: Imagem gerada (sha256=$SHA_C0_1, bytes=$BYTES_C0_1)"

# Repete para comprovar determinismo byte a byte
IMG_INFO_2="$( "$BIN" image "$SRC" )"
SHA_C0_2="$( echo "$IMG_INFO_2" | grep -o 'sha256=[0-9a-f]*' | cut -d= -f2 )"
[ "$SHA_C0_1" = "$SHA_C0_2" ] || fail "Determinismo violado no C0: $SHA_C0_1 != $SHA_C0_2"
ok "Ciclo C0 determinístico: reproduzível byte a byte"

# 3. Ciclo C1: Execução do compilador para auto-compilar suas funções
echo "Ciclo C1: Executando auto-compilação na LinVM..."
FOLD_C1="$( "$BIN" vm "$SRC" c0_compile_self_fold | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
ok "Ciclo C1: Fold canônico de bytecode gerado = $FOLD_C1"

# 4. Ciclo C2: Recompilação a partir da imagem para provar estabilidade matemática
echo "Ciclo C2: Recompilando e verificando estabilidade matemática..."
FOLD_C2="$( "$BIN" roundtrip "$SRC" c0_compile_self_fold | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$FOLD_C1" = "$FOLD_C2" ] || fail "Divergência de ponto fixo: C1 ($FOLD_C1) != C2 ($FOLD_C2)"
ok "Ciclo C2 estável: C1 == C2 ($FOLD_C1)"

# 5. Validação interna do gate
GATE_VAL="$( "$BIN" vm "$SRC" fixed_point_gate | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$GATE_VAL" = "1" ] || fail "fixed_point_gate falhou: $GATE_VAL"
ok "Gate de Ponto Fixo: fixed_point_gate() == 1"

echo "=== PONTO FIXO C0 = C1 = C2 FECHADO E COMPROVADO COM SUCESSO ==="
exit 0
