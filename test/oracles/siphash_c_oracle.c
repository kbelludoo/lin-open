#include <stdio.h>
#include <stdint.h>
#include <string.h>

/*
 * SipHash-2-4 reference C implementation (Jean-Philippe Aumasson & Daniel J. Bernstein)
 * Source: official 128-bit key, 64-bit tag reference implementation.
 */

#define ROTL64(x, b) (uint64_t)(((x) << (b)) | ((x) >> (64 - (b))))

#define SIPROUND \
    v0 += v1; v1 = ROTL64(v1, 13); v1 ^= v0; v0 = ROTL64(v0, 32); \
    v2 += v3; v3 = ROTL64(v3, 16); v3 ^= v2; \
    v0 += v3; v3 = ROTL64(v3, 21); v3 ^= v0; \
    v2 += v1; v1 = ROTL64(v1, 17); v1 ^= v2; v2 = ROTL64(v2, 32);

uint64_t siphash24(const uint8_t *in, size_t inlen, const uint8_t *k) {
    uint64_t k0 = 0, k1 = 0;
    memcpy(&k0, k, 8);
    memcpy(&k1, k + 8, 8);

    uint64_t v0 = k0 ^ 0x736f6d6570736575ULL;
    uint64_t v1 = k1 ^ 0x646f72616e646f6dULL;
    uint64_t v2 = k0 ^ 0x6c7967656e657261ULL;
    uint64_t v3 = k1 ^ 0x7465646279746573ULL;

    const uint8_t *end = in + inlen - (inlen % 8);
    const uint8_t *p = in;
    while (p < end) {
        uint64_t m = 0;
        memcpy(&m, p, 8);
        v3 ^= m;
        SIPROUND;
        SIPROUND;
        v0 ^= m;
        p += 8;
    }

    uint64_t b = ((uint64_t)inlen) << 56;
    int left = inlen & 7;
    for (int i = 0; i < left; i++) {
        b |= ((uint64_t)p[i]) << (8 * i);
    }

    v3 ^= b;
    SIPROUND;
    SIPROUND;
    v0 ^= b;

    v2 ^= 0xff;
    SIPROUND;
    SIPROUND;
    SIPROUND;
    SIPROUND;

    return v0 ^ v1 ^ v2 ^ v3;
}

int main(int argc, char **argv) {
    uint8_t k[16];
    for (int i = 0; i < 16; i++) k[i] = (uint8_t)i;

    if (argc > 1 && strcmp(argv[1], "vector") == 0) {
        // Gera os 64 vetores oficiais (mensagens de tamanho 0 a 63 onde byte[i] = i)
        uint8_t msg[64];
        for (int i = 0; i < 64; i++) msg[i] = (uint8_t)i;

        for (int len = 0; len < 64; len++) {
            uint64_t tag = siphash24(msg, len, k);
            printf("%d: %016llx\n", len, (unsigned long long)tag);
        }
        return 0;
    }

    // Default: imprime o digest da mensagem de 64 bytes
    uint8_t msg[64];
    for (int i = 0; i < 64; i++) msg[i] = (uint8_t)i;
    uint64_t tag = siphash24(msg, 64, k);
    printf("digest_64=%016llx\n", (unsigned long long)tag);
    return 0;
}
