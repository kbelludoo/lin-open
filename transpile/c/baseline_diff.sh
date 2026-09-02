#!/usr/bin/env bash
# baseline_diff.sh — diff byte-exact entre a suite original (Zig) e o port (C).
#
# RODE EM UMA MÁQUINA COM ZIG INSTALADO (esta sandbox não alcança o ziglang.org).
#
# O que ele faz:
#   1. builda o binário original (`make build` na raiz do repo)
#   2. roda `lin test` e isola APENAS o bloco da suite de expressões C:
#      do banner "REAL STAGE-0 C EXPRESSION" até o banner "FATIA C1 & C2",
#      removendo a linha de "=" e o branco que separam as duas suites
#   3. builda e roda o port C
#   4. diff -u dos dois blocos (stdout apenas; o resumo do port sai em stderr)
#
# Sucesso = saída idêntica nos 29 vetores (valores, estágios de rejeição,
# contagem de instruções e formatação).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "==> 1/4 build do binário original (Zig)"
cd "${REPO_ROOT}"
make build

echo "==> 2/4 rodando 'lin test' e isolando o bloco Stage-0 C-Expression"
ZIG_LOG="$(mktemp)"
trap 'rm -f "${ZIG_LOG}" "${C_LOG}"' EXIT
./bin/lin_native test > "${ZIG_LOG}" 2>/dev/null || true

ZIG_BLOCK="$(mktemp)"
awk '
    /STAGE-0 C EXPRESSION PARSER/ { f = 1 }
    f && /FATIA C1 & C2: CONTROL FLOW/ { exit }
    f { lines[++n] = $0 }
    END {
        # remove sufixo de separação (linha de "=" e linhas vazias)
        while (n > 0 && (lines[n] ~ /^=+$/ || lines[n] ~ /^[[:space:]]*$/)) n--
        for (i = 1; i <= n; i++) print lines[i]
    }
' "${ZIG_LOG}" > "${ZIG_BLOCK}"

if [ ! -s "${ZIG_BLOCK}" ]; then
    echo "ERRO: bloco Stage-0 não encontrado na saída de 'lin test'." >&2
    echo "(o formato do log pode ter mudado — ajuste o awk acima)" >&2
    exit 2
fi

echo "==> 3/4 build e execução do port C"
make -C "${SCRIPT_DIR}"
C_LOG="$(mktemp)"
"${SCRIPT_DIR}/bin/test_c_expr" > "${C_LOG}" 2>/dev/null || true
# normaliza o mesmo jeito: a partir do banner (remove o branco de cabeçalho)
awk '/STAGE-0 C EXPRESSION PARSER/ { f = 1 } f { print }' "${C_LOG}" > "${C_LOG}.n"
mv "${C_LOG}.n" "${C_LOG}"

echo "==> 4/4 diff (Zig original  vs  port C)"
if diff -u "${ZIG_BLOCK}" "${C_LOG}"; then
    echo
    echo "OK: saída do port C é byte-idêntica à suite Stage-0 do Zig."
else
    echo
    echo "MISMATCH: diferenças acima. Este é o bug que o oráculo encontrou." >&2
    exit 1
fi
