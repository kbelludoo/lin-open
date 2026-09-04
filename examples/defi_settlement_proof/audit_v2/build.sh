#!/bin/sh
# build.sh — compila as ferramentas C11 do kit de auditoria v2.
# Sem dependências externas: apenas cc + os fontes lin_c do repositório.
set -e
cd "$(dirname "$0")"
LINC=../../../transpile/c/lin_c
CC=${CC:-cc}
CFLAGS="-O3 -std=c11 -Wall -Wextra -I$LINC"
mkdir -p bin

$CC $CFLAGS -o bin/legacy_attack legacy_attack.c
$CC $CFLAGS -o bin/verify_batch_c verify_batch_c.c \
    $LINC/lin_sha256.c $LINC/lin_common.c $LINC/lin_token.c $LINC/lin_ast.c \
    $LINC/lin_parse.c $LINC/lin_vm.c $LINC/lin_str.c $LINC/lin_linbc1.c

# test_image_hardening: -O1 para manter o loop exaustivo rápido e rastreável
$CC -O1 -std=c11 -Wall -Wextra -I$LINC -o bin/test_image_hardening test_image_hardening.c \
    $LINC/lin_common.c $LINC/lin_token.c $LINC/lin_ast.c $LINC/lin_sha256.c \
    $LINC/lin_parse.c $LINC/lin_vm.c $LINC/lin_str.c $LINC/lin_linbc1.c

# test_no_heap: interceptação de heap via --wrap (o caminho LIN não pode alocar)
$CC -O2 -std=c11 -Wall -Wextra -I$LINC -o bin/test_no_heap test_no_heap.c \
    $LINC/lin_common.c $LINC/lin_token.c $LINC/lin_ast.c \
    $LINC/lin_parse.c $LINC/lin_vm.c $LINC/lin_sha256.c $LINC/lin_str.c $LINC/lin_linbc1.c \
    -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc,--wrap=free \
    -Wl,--wrap=posix_memalign,--wrap=aligned_alloc,--wrap=reallocarray,--wrap=strdup

echo "audit_v2: ferramentas compiladas em bin/"
