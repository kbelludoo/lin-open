// Runner CPU de referência para u256_opencl_kernel.cl.
//
// Compila o MESMO código-fonte do kernel OpenCL como C11 (os qualificadores
// __kernel/__global e get_global_id são mapeados por macro) e o executa
// sequencialmente sobre um buffer de 128 B/registro. Objetivo: tornar o
// resultado de paridade do kernel reproduzível sem GPU/ROCm, e permitir que
// um lote adversarial mostre divergências de verdade em vez de um printf fixo.
//
//   cc -O2 -std=c11 -o /tmp/u256_cpu_ref examples/defi_settlement_proof/u256_kernel_cpu_ref.c
//   /tmp/u256_cpu_ref /tmp/swaps.bin
//
// Este runner NÃO mede throughput de GPU; o tempo impresso é de CPU single-thread.
#define _POSIX_C_SOURCE 199309L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef uint8_t uchar;
typedef uint16_t ushort;
typedef uint32_t uint;
typedef int bool;
#define true 1
#define false 0
#define __kernel
#define __global
static uint g_gid;
static inline uint get_global_id(int d) { (void)d; return g_gid; }

#include "u256_opencl_kernel.cl"

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/tmp/swaps.bin";
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); return 2; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz <= 0 || sz % 128) { fprintf(stderr, "tamanho invalido: %ld (esperado multiplo de 128)\n", sz); return 2; }
    size_t n = (size_t)sz / 128;
    uchar *in = malloc(sz);
    if (fread(in, 1, sz, f) != (size_t)sz) { fprintf(stderr, "leitura falhou\n"); return 2; }
    fclose(f);
    uchar *out = calloc(n, 32);
    int *match = calloc(n, sizeof(int));

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (size_t i = 0; i < n; i++) {
        g_gid = (uint)i;
        settle_u256_batch(in, out, match, (uint)n);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double el = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;

    size_t ok = 0;
    for (size_t i = 0; i < n; i++) ok += match[i] == 1;
    size_t bad = n - ok;
    printf("kernel_cpu_ref: registros=%zu concordam=%zu divergem=%zu tempo=%.4fs (%.1f swaps/s CPU 1 thread)\n",
           n, ok, bad, el, n / el);
    if (bad) {
        size_t shown = 0;
        for (size_t i = 0; i < n && shown < 5; i++) if (!match[i]) {
            printf("  divergencia #%zu: expected=0x", i);
            for (int b = 0; b < 32; b++) printf("%02x", in[i * 128 + 96 + b]);
            printf(" kernel=0x");
            for (int b = 0; b < 32; b++) printf("%02x", out[i * 32 + b]);
            printf("\n");
            shown++;
        }
    }
    free(in); free(out); free(match);
    return bad ? 1 : 0;
}
