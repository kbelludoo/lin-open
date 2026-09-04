#!/bin/sh
# run_audit.sh — auditoria v2 completa do motor de liquidação LINBC1.
#
# Uso:  sh examples/defi_settlement_proof/audit_v2/run_audit.sh
#
# Camadas:
#   1. build das ferramentas C11 do repositório (só `cc`, sem Zig)
#   2. build do kit de auditoria v2 (legacy_attack, verify_batch_c, hardening, no_heap)
#   3. suíte Python v2 (determinismo, paridade, guardas, Merkle SHA-256,
#      matriz adversarial, estatística, auditor C, forense do hash legado)
#   4. camada ASan+UBSan (sem vazamentos, sem UB, zero-heap re-verificado)
#
# Exit 0 somente se TUDO passar. Relatório: audit_v2/audit_report_v2.json
set -e
cd "$(dirname "$0")/../.."          # raiz do repositório
AUD=examples/defi_settlement_proof/audit_v2
LINC=transpile/c/lin_c

echo "== [1/4] build ferramentas C11 do repositório =="
make -C transpile/c all >/dev/null
echo "ok"

echo "== [2/4] build kit de auditoria v2 =="
sh "$AUD/build.sh"

echo "== [3/4] suíte Python v2 =="
python3 "$AUD/benchmark_settlement_proof_v2.py"

echo "== [4/4] camada ASan+UBSan =="
SAN="-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1 -std=c11 -I$LINC"
BASE="$LINC/lin_common.c $LINC/lin_token.c $LINC/lin_ast.c $LINC/lin_parse.c $LINC/lin_vm.c $LINC/lin_str.c $LINC/lin_linbc1.c"
TMP=$(mktemp -d)
cc $SAN -o "$TMP/noheap" "$AUD/test_no_heap.c" $LINC/lin_sha256.c $BASE \
   -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc,--wrap=free \
   -Wl,--wrap=posix_memalign,--wrap=aligned_alloc,--wrap=reallocarray,--wrap=strdup
"$TMP/noheap" "$AUD/../settlement_engine.linbc" 2000
cc $SAN -o "$TMP/hard" "$AUD/test_image_hardening.c" $LINC/lin_sha256.c $BASE
"$TMP/hard" "$AUD/../settlement_engine.linbc" | tail -1
cc $SAN -o "$TMP/vb" "$AUD/verify_batch_c.c" $LINC/lin_sha256.c $BASE
"$TMP/vb" "$AUD/bin/batch.bin" "$AUD/../settlement_engine.linbc" | head -2
rm -rf "$TMP"

echo ""
echo "AUDITORIA v2: PASS (todas as camadas)"
