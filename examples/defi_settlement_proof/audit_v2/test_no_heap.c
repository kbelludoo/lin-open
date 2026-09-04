/*
 * test_no_heap.c — Prova em runtime de "zero heap" no caminho load+exec+verify.
 *
 * Compilado com -Wl,--wrap=malloc,--wrap=calloc,... : qualquer chamada a
 * malloc/calloc/realloc/free/posix_memalign/aligned_alloc/reallocarray/strdup
 * vinda do binário (incluindo lin_bc1_load, lin_vm vm_exec e lin_sha256)
 * cai nos nossos wrappers, que apenas incrementam contadores.
 *
 * Executa o mesmo fluxo do host de produção (carregar imagem -> liquidar
 * lote -> verificar prova Merkle in-VM) e exige delta == 0 em todos os
 * contadores. Baseline capturada ao entrar em main(), isolando alocações do
 * próprio libc durante o startup.
 *
 * Saída: "NOHEAP delta_malloc=0 delta_calloc=0 ... passed=1" (exit 0).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lin_linbc1.h"
#include "lin_sha256.h"

static long c_malloc, c_calloc, c_realloc, c_free, c_memalign, c_strdup;

void *__real_malloc(size_t);
void  __real_free(void *);

void *__wrap_malloc(size_t n)          { (void)n; c_malloc++;  return NULL; }
void *__wrap_calloc(size_t a, size_t b){ (void)a; (void)b; c_calloc++; return NULL; }
void *__wrap_realloc(void *p, size_t n){ (void)p; (void)n; c_realloc++; return NULL; }
void  __wrap_free(void *p)             { (void)p; c_free++; }
int   __wrap_posix_memalign(void **o, size_t al, size_t n) {
    (void)o; (void)al; (void)n; c_memalign++; return -1;
}
void *__wrap_aligned_alloc(size_t al, size_t n) {
    (void)al; (void)n; c_memalign++; return NULL;
}
void *__wrap_reallocarray(void *p, size_t a, size_t b) {
    (void)p; (void)a; (void)b; c_realloc++; return NULL;
}
char *__wrap_strdup(const char *s)     { (void)s; c_strdup++; return NULL; }

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "uso: test_no_heap <imagem.linbc> <n_execs>\n"); return 2; }

    /* leitura de arquivo com open/read POSIX, FORA da zona auditada:
     * a zona auditada começa na captura da baseline e contém apenas o
     * caminho LIN (lin_bc1_load + vm_exec + lin_sha256). */
    static uint8_t img[64 * 1024];
    size_t n = 0;
    {
        FILE *f = fopen(argv[1], "rb");
        if (!f) { fprintf(stderr, "imagem ausente\n"); return 2; }
        size_t got = fread(img, 1, sizeof(img), f);
        fclose(f);
        if (got == 0) { fprintf(stderr, "imagem vazia\n"); return 2; }
        n = got;
    }

    long b_malloc = c_malloc, b_calloc = c_calloc, b_realloc = c_realloc;
    long b_free = c_free, b_memalign = c_memalign, b_strdup = c_strdup;

    LinBc1Vm vm;
    if (lin_bc1_load(img, n, &vm) != LIN_BC1_OK) {
        fprintf(stderr, "NOHEAP load=rejeitado (imagem inválida?)\n");
        return 1;
    }
    int fn = lin_bc1_find_fn(&vm, "settle_swap");
    int fv = lin_bc1_find_fn(&vm, "verify_merkle_branch_2");
    if (fn < 0 || fv < 0) { fprintf(stderr, "NOHEAP fn=aussente\n"); return 1; }

    long n_execs = strtol(argv[2], 0, 10);
    if (n_execs < 1) n_execs = 1;
    unsigned long seed = 0x9E3779B97F4A7C15ull;
    long exec_err = 0;

    for (long k = 0; k < n_execs; k++) {
        seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
        int64_t ain = (int64_t)(seed % 500000) + 1;
        seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
        int64_t rin = (int64_t)(seed % 50000000) + 1;
        seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
        int64_t rout = (int64_t)(seed % 50000000) + 1;
        int64_t args[4] = { ain, rin, rout, 1 };

        uint64_t steps = 0; VmExecResult res;
        if (vm_exec(&vm.mod, (size_t)fn, args, 4, 0, &steps, &res) != LIN_OK) exec_err++;

        /* prova Merkle in-VM (hash legado, apenas exercício do executor) */
        int64_t a2[5] = { 123, 456, 789, 2, 999999 };
        uint64_t st2 = 0; VmExecResult r2;
        if (vm_exec(&vm.mod, (size_t)fv, a2, 5, 0, &st2, &r2) != LIN_OK) exec_err++;

        uint8_t dg[32];
        lin_sha256(img, n, dg);
        (void)dg;
    }

    long d_malloc  = c_malloc  - b_malloc;
    long d_calloc  = c_calloc  - b_calloc;
    long d_realloc = c_realloc - b_realloc;
    long d_free    = c_free    - b_free;
    long d_memal   = c_memalign- b_memalign;
    long d_strdup  = c_strdup  - b_strdup;
    long total = d_malloc + d_calloc + d_realloc + d_free + d_memal + d_strdup;

    printf("NOHEAP execs=%ld exec_err=%ld\n", n_execs, exec_err);
    printf("NOHEAP delta_malloc=%ld delta_calloc=%ld delta_realloc=%ld delta_free=%ld "
           "delta_memalign=%ld delta_strdup=%ld\n",
           d_malloc, d_calloc, d_realloc, d_free, d_memal, d_strdup);
    printf("NOHEAP total_heap_ops=%ld passed=%d\n", total, (total == 0 && exec_err == 0));
    return (total == 0 && exec_err == 0) ? 0 : 1;
}
