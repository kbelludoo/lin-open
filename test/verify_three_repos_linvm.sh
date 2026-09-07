#!/usr/bin/env bash
# verify_three_repos_linvm.sh
# Verificação de ponta a ponta dos 3 repositórios transpilados para LIN e compilados na LinVM:
#   1. phoboslab/qoi (src/lin_qoi_codec.lin)
#   2. codeplea/tinyexpr (src/lin_tinyexpr_unified.lin)
#   3. Uniswap/v2-core (src/lin_uniswap_v2_core.lin)
#
# Sem nenhuma dependência de Zig em runtime. Usa apenas o compilador LinVM (C11 host lin_c0).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT_DIR/transpile/c/bin/lin_c0"

fail() { echo "THREE_REPOS_LINVM: FAIL: $*" >&2; exit 1; }
ok()   { echo "THREE_REPOS_LINVM:   ok: $*"; }

echo "=== VERIFICAÇÃO LINVM: 3 REPOSITÓRIOS NO COMPILADOR 0 ==="

# 1. Garante que o binário lin_c0 existe
if [ ! -x "$BIN" ]; then
    echo "Compilando lin_c0..."
    make -C "$ROOT_DIR/transpile/c" c0 >/dev/null || fail "Falha ao compilar lin_c0"
fi

# -----------------------------------------------------------------------------
# REPO 1: phoboslab/qoi
# -----------------------------------------------------------------------------
echo "--- 1. phoboslab/qoi (Codec de Imagem Sem Perdas) ---"
QOI_SRC="$ROOT_DIR/src/lin_qoi_codec.lin"
[ -f "$QOI_SRC" ] || fail "Arquivo não encontrado: $QOI_SRC"

# 1.1 Cobertura de funções
QOI_REJ="$( "$BIN" info "$QOI_SRC" | grep -o 'rejected=[0-9]*' | cut -d= -f2 )"
[ "$QOI_REJ" = "0" ] || fail "qoi_codec tem funções rejeitadas ($QOI_REJ)"
ok "qoi_codec: 10/10 funções elegíveis (0 rejeitadas)"

# 1.2 Execução direta na LinVM
QOI_VAL="$( "$BIN" vm "$QOI_SRC" qoi_test_suite | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$QOI_VAL" = "1" ] || fail "qoi_test_suite falhou (esperado 1, obteve $QOI_VAL)"
ok "qoi_codec: qoi_test_suite() == 1 (execução direta)"

# 1.3 Roundtrip: Fonte -> Bytecode LINBC1 -> Execução
QOI_CONS="$( "$BIN" roundtrip "$QOI_SRC" qoi_test_suite | grep -o 'status="[^"]*"' | cut -d\" -f2 )"
[ "$QOI_CONS" = "CONSENSUS" ] || fail "qoi_codec roundtrip falhou: $QOI_CONS"
ok "qoi_codec: consenso total entre código-fonte e imagem LINBC1"

# -----------------------------------------------------------------------------
# REPO 2: codeplea/tinyexpr
# -----------------------------------------------------------------------------
echo "--- 2. codeplea/tinyexpr (Parser e Avaliador Matemático AST / Q32.32) ---"
TE_SRC="$ROOT_DIR/src/lin_tinyexpr_unified.lin"
[ -f "$TE_SRC" ] || fail "Arquivo não encontrado: $TE_SRC"

TE_REJ="$( "$BIN" info "$TE_SRC" | grep -o 'rejected=[0-9]*' | cut -d= -f2 )"
[ "$TE_REJ" = "0" ] || fail "tinyexpr_unified tem funções rejeitadas ($TE_REJ)"
ok "tinyexpr_unified: 8/8 funções elegíveis (0 rejeitadas)"

TE_VAL="$( "$BIN" vm "$TE_SRC" te_test_suite | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$TE_VAL" = "1" ] || fail "te_test_suite falhou (esperado 1, obteve $TE_VAL)"
ok "tinyexpr_unified: te_test_suite() == 1 (execução direta)"

TE_CONS="$( "$BIN" roundtrip "$TE_SRC" te_test_suite | grep -o 'status="[^"]*"' | cut -d\" -f2 )"
[ "$TE_CONS" = "CONSENSUS" ] || fail "tinyexpr_unified roundtrip falhou: $TE_CONS"
ok "tinyexpr_unified: consenso total entre código-fonte e imagem LINBC1"

# -----------------------------------------------------------------------------
# REPO 3: Uniswap/v2-core (FullMath & UniswapV2Library)
# -----------------------------------------------------------------------------
echo "--- 3. Uniswap/v2-core (Matemática Financeira e Invariantes AMM) ---"
UNI_SRC="$ROOT_DIR/src/lin_uniswap_v2_core.lin"
[ -f "$UNI_SRC" ] || fail "Arquivo não encontrado: $UNI_SRC"

UNI_REJ="$( "$BIN" info "$UNI_SRC" | grep -o 'rejected=[0-9]*' | cut -d= -f2 )"
[ "$UNI_REJ" = "0" ] || fail "uniswap_v2_core tem funções rejeitadas ($UNI_REJ)"
ok "uniswap_v2_core: 8/8 funções elegíveis (0 rejeitadas)"

UNI_VAL="$( "$BIN" vm "$UNI_SRC" u2_test_suite | grep -o 'value=[-0-9]*' | cut -d= -f2 )"
[ "$UNI_VAL" = "1" ] || fail "u2_test_suite falhou (esperado 1, obteve $UNI_VAL)"
ok "uniswap_v2_core: u2_test_suite() == 1 (execução direta)"

UNI_CONS="$( "$BIN" roundtrip "$UNI_SRC" u2_test_suite | grep -o 'status="[^"]*"' | cut -d\" -f2 )"
[ "$UNI_CONS" = "CONSENSUS" ] || fail "uniswap_v2_core roundtrip falhou: $UNI_CONS"
ok "uniswap_v2_core: consenso total entre código-fonte e imagem LINBC1"

echo "=== TODOS OS 3 REPOSITÓRIOS COMPILADOS E EXECUTADOS COM SUCESSO NA LINVM ==="
exit 0
