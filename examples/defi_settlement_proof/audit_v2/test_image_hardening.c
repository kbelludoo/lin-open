/*
 * test_image_hardening.c — Endurecimento da imagem LINBC1, exaustivo e in-process.
 *
 * Para CADA bit da imagem settlement_engine.linbc (3.098 bytes × 8 = 24.784
 * mutações), carrega a imagem mutada com lin_bc1_load e exige rejeição.
 * Também testa todos os 3.098 truncamentos e a corrupção de cada byte da
 * cauda (self-hash embutido).
 *
 * Propriedade provada: o loader é fail-closed contra qualquer adulteração de
 * 1 bit — nenhuma mutação single-bit é aceita e executada.
 *
 * Saída: "HARDENING mutations=<N> rejected=<M> truncations=<T> rejected_trunc=<U> passed=1"
 * Exit code 0 somente se TODAS as mutações forem rejeitadas.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lin_linbc1.h"

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "uso: test_image_hardening <imagem.linbc>\n"); return 2; }

    static uint8_t img[64 * 1024];
    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "imagem ausente\n"); return 2; }
    size_t n = fread(img, 1, sizeof(img), f); fclose(f);

    LinBc1Vm vm;
    if (lin_bc1_load(img, n, &vm) != LIN_BC1_OK) {
        fprintf(stderr, "SANIDADE FALHOU: imagem original nao carrega\n");
        return 1;
    }
    printf("HARDENING sanity=1 imagem original aceita (%zu bytes)\n", n);

    static uint8_t mut[64 * 1024];
    long mutations = 0, rejected = 0, accepted = 0;
    for (size_t i = 0; i < n; i++) {
        for (int bit = 0; bit < 8; bit++) {
            memcpy(mut, img, n);
            mut[i] ^= (uint8_t)(1u << bit);
            mutations++;
            if (lin_bc1_load(mut, n, &vm) != LIN_BC1_OK) rejected++;
            else accepted++;
        }
    }

    long truncations = 0, rejected_trunc = 0;
    for (size_t len = 0; len < n; len++) {
        truncations++;
        if (lin_bc1_load(img, len, &vm) != LIN_BC1_OK) rejected_trunc++;
    }

    /* bytes extras ao final (trailing) */
    long trailing = 0, rejected_trailing = 0;
    memcpy(mut, img, n);
    for (int extra = 1; extra <= 64; extra++) {
        mut[n + extra - 1] = 0x41;
        trailing++;
        if (lin_bc1_load(mut, n + (size_t)extra, &vm) != LIN_BC1_OK) rejected_trailing++;
    }

    printf("HARDENING mutations=%ld rejected=%ld accepted=%ld\n",
           mutations, rejected, accepted);
    printf("HARDENING truncations=%ld rejected=%ld\n", truncations, rejected_trunc);
    printf("HARDENING trailing=%ld rejected=%ld\n", trailing, rejected_trailing);
    printf("HARDENING passed=%d\n",
           (accepted == 0 && rejected_trunc == truncations && rejected_trailing == trailing));
    return (accepted == 0 && rejected_trunc == truncations && rejected_trailing == trailing) ? 0 : 1;
}
