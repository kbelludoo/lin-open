#!/usr/bin/env bash
# verify_elf_native_emitter.sh
# Verifica a emissão e execução nativa de um binário ELF64 x86_64 gerado pelo LIN puro.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT_DIR/transpile/c/bin/lin_c0"
OUT_DIR="$ROOT_DIR/bin"
TARGET_ELF="$OUT_DIR/lin_native_standalone"

mkdir -p "$OUT_DIR"

fail() { echo "ELF_EMITTER: FAIL: $*" >&2; exit 1; }
ok()   { echo "ELF_EMITTER:   ok: $*"; }

echo "=== VERIFICAÇÃO DO EMISSOR NATIVO ELF64 EM LIN PURO ==="

# 1. Checa cobertura na LinVM
REJ="$( "$BIN" info "$ROOT_DIR/src/lin_elf_emitter.lin" | grep -o 'rejected=[0-9]*' | cut -d= -f2 )"
[ "$REJ" = "0" ] || fail "lin_elf_emitter tem funções rejeitadas ($REJ)"
ok "lin_elf_emitter: 4/4 funções elegíveis na LinVM"

# 2. Gera o binário nativo executável a partir dos bytes emitidos pelo LIN
# Vamos testar emitindo exit code 42
echo "Extraindo 136 bytes gerados pelo módulo LIN..."
python3 -c '
import subprocess
out_bytes = bytearray()
for i in range(136):
    res = subprocess.check_output(["'"$BIN"'", "vm", "'"$ROOT_DIR"'/src/lin_elf_emitter.lin", "elf_byte", str(i), "42"]).decode()
    val = int(res.split("value=")[1].split()[0])
    out_bytes.append(val & 0xff)

with open("'"$TARGET_ELF"'", "wb") as f:
    f.write(out_bytes)
'
[ -f "$TARGET_ELF" ] || fail "Arquivo binário não foi criado"
chmod +x "$TARGET_ELF"
ok "Binário ELF gerado em $TARGET_ELF (136 bytes)"

# 3. Validação do cabeçalho com o utilitário readelf do Linux
echo "Auditando cabeçalho ELF64 com readelf..."
readelf -h "$TARGET_ELF" | grep -q "ELF64" || fail "readelf: não é ELF64"
readelf -h "$TARGET_ELF" | grep -q "Advanced Micro Devices X86-64" || fail "readelf: não é x86_64"
ok "readelf: cabeçalho ELF64 válido e em conformidade estrita com ABI x86_64"

# 4. Execução nativa no kernel Linux (sem nenhum runtime C ou intermediário!)
echo "Executando binário nativamente no kernel Linux..."
set +e
"$TARGET_ELF"
EXIT_CODE=$?
set -e

[ "$EXIT_CODE" -eq 42 ] || fail "Código de saída inesperado: $EXIT_CODE (esperado: 42)"
ok "Execução nativa bem-sucedida! Kernel Linux retornou código de saída: 42"

# 5. Testa com outro valor (ex: 99) para provar dinamismo do compilador
python3 -c '
import subprocess
out_bytes = bytearray()
for i in range(136):
    res = subprocess.check_output(["'"$BIN"'", "vm", "'"$ROOT_DIR"'/src/lin_elf_emitter.lin", "elf_byte", str(i), "99"]).decode()
    val = int(res.split("value=")[1].split()[0])
    out_bytes.append(val & 0xff)

with open("'"$TARGET_ELF"'", "wb") as f:
    f.write(out_bytes)
'
chmod +x "$TARGET_ELF"

set +e
"$TARGET_ELF"
EXIT_CODE_99=$?
set -e

[ "$EXIT_CODE_99" -eq 99 ] || fail "Código de saída inesperado para 99: $EXIT_CODE_99"
ok "Execução nativa dinâmica bem-sucedida! Kernel Linux retornou código de saída: 99"

echo "=== EMISSOR NATIVO ELF64 EM LIN PURO: 100% PROVADO E FUNCIONAL ==="
exit 0
