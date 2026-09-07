#define QOI_IMPLEMENTATION
#include "../fixtures/external_proof/qoi.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

/*
 * Oraculo de referencia oficial compilado a partir de test/fixtures/external_proof/qoi.h
 * Executa encode e decode sobre padroes conhecidos de pixels RGBA e emite saidas em hexadecimal.
 */

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Uso: %s [encode_test | decode_test]\n", argv[0]);
        return 1;
    }

    /* Padrao de teste 1: 4x4 pixels RGBA (16 pixels, 64 bytes) */
    /* Contem repeticoes (RUN), variacoes sutis (DIFF/LUMA), cores repetidas (INDEX) e novas cores (RGB) */
    uint8_t pixels[64] = {
        // Linha 0: 4 pixels vermelhos solidos (testa QOI_OP_RUN)
        255, 0, 0, 255,   255, 0, 0, 255,   255, 0, 0, 255,   255, 0, 0, 255,
        // Linha 1: variacoes sutis de vermelho (testa QOI_OP_DIFF)
        254, 0, 0, 255,   253, 1, 0, 255,   255, 0, 0, 255,   0, 255, 0, 255,
        // Linha 2: alternancia de cores ja vistas (testa QOI_OP_INDEX)
        255, 0, 0, 255,   0, 255, 0, 255,   255, 0, 0, 255,   0, 0, 255, 255,
        // Linha 3: pixel com alpha variavel (testa QOI_OP_RGBA)
        0, 0, 255, 128,   0, 0, 255, 128,   255, 255, 255, 255, 0, 0, 0, 255
    };

    if (strcmp(argv[1], "encode_test") == 0) {
        qoi_desc desc = {
            .width = 4,
            .height = 4,
            .channels = 4,
            .colorspace = QOI_SRGB
        };
        int out_len = 0;
        void *encoded = qoi_encode(pixels, &desc, &out_len);
        if (!encoded) {
            fprintf(stderr, "Falha no encode\n");
            return 1;
        }

        uint8_t *b = (uint8_t *)encoded;
        printf("len=%d hex=", out_len);
        for (int i = 0; i < out_len; i++) {
            printf("%02x", b[i]);
        }
        printf("\n");
        free(encoded);
        return 0;
    }

    if (strcmp(argv[1], "decode_test") == 0) {
        qoi_desc desc = {
            .width = 4,
            .height = 4,
            .channels = 4,
            .colorspace = QOI_SRGB
        };
        int enc_len = 0;
        void *encoded = qoi_encode(pixels, &desc, &enc_len);
        if (!encoded) return 1;

        qoi_desc dec_desc;
        void *decoded = qoi_decode(encoded, enc_len, &dec_desc, 4);
        if (!decoded) {
            fprintf(stderr, "Falha no decode\n");
            free(encoded);
            return 1;
        }

        int px_len = dec_desc.width * dec_desc.height * 4;
        uint8_t *p = (uint8_t *)decoded;
        printf("w=%u h=%u px_len=%d hex=", dec_desc.width, dec_desc.height, px_len);
        for (int i = 0; i < px_len; i++) {
            printf("%02x", p[i]);
        }
        printf("\n");

        free(encoded);
        free(decoded);
        return 0;
    }

    fprintf(stderr, "Comando desconhecido: %s\n", argv[1]);
    return 1;
}
