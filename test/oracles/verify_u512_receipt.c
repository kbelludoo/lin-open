/*
 * C11 auditor for LNR1 (240-byte) u512 coprocessor receipts.
 * Zero LIN VM: SHA-256 via transpile/c/lin_c/lin_sha256.c only.
 * Domains: LIN:U512:LEAF:1 / LIN:U512:NODE:1
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../../transpile/c/lin_c/lin_sha256.h"

#define LNR1_SIZE 240
static const uint8_t DOM_LEAF[] = "LIN:U512:LEAF:1";
static const uint8_t DOM_NODE[] = "LIN:U512:NODE:1";

static void leaf_hash(const uint8_t rec[LNR1_SIZE], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_LEAF, sizeof(DOM_LEAF) - 1);
    lin_sha256_update(&ctx, rec, LNR1_SIZE);
    lin_sha256_final(&ctx, out);
}

static void node_hash(const uint8_t l[32], const uint8_t r[32], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_NODE, sizeof(DOM_NODE) - 1);
    lin_sha256_update(&ctx, l, 32);
    lin_sha256_update(&ctx, r, 32);
    lin_sha256_final(&ctx, out);
}

static int merkle_root(const uint8_t *recs, size_t nbytes, uint8_t root[32]) {
    if (nbytes % LNR1_SIZE != 0 || nbytes == 0) return -1;
    size_t n = nbytes / LNR1_SIZE;
    uint8_t *nodes = (uint8_t *)malloc(n * 32);
    if (!nodes) return -1;
    for (size_t i = 0; i < n; i++) leaf_hash(recs + i * LNR1_SIZE, nodes + i * 32);
    while (n > 1) {
        size_t nn = (n + 1) / 2;
        for (size_t i = 0; i < n; i += 2) {
            const uint8_t *L = nodes + i * 32;
            const uint8_t *R = (i + 1 < n) ? nodes + (i + 1) * 32 : L;
            uint8_t tmp[32];
            node_hash(L, R, tmp);
            memcpy(nodes + (i / 2) * 32, tmp, 32);
        }
        n = nn;
    }
    memcpy(root, nodes, 32);
    free(nodes);
    return 0;
}

static void fill_dummy(uint8_t rec[LNR1_SIZE], uint8_t tag) {
    memset(rec, 0, LNR1_SIZE);
    memcpy(rec, "LNR1", 4);
    rec[4] = 1;
    rec[5] = 2; /* MULDIV */
    rec[56 + 31] = tag;
}

static int self_test(void) {
    uint8_t recs[2 * LNR1_SIZE], root[32], tamp[32], recs2[2 * LNR1_SIZE];
    char hex[65], hex2[65];
    fill_dummy(recs, 1);
    fill_dummy(recs + LNR1_SIZE, 2);
    if (merkle_root(recs, sizeof recs, root) != 0) return 1;
    memcpy(recs2, recs, sizeof recs);
    recs2[56 + 31] ^= 1;
    if (merkle_root(recs2, sizeof recs2, tamp) != 0) return 1;
    lin_sha256_hex(root, hex);
    lin_sha256_hex(tamp, hex2);
    if (memcmp(root, tamp, 32) == 0) {
        fprintf(stderr, "FAIL tamper root unchanged\n");
        return 1;
    }
    printf("AUDITOR_SELFTEST_PASS root=%s tamper=%s\n", hex, hex2);
    return 0;
}

static int load_file(const char *path, uint8_t **out, size_t *n) {
    FILE *f = fopen(path, "rb");
    long sz;
    if (!f) return -1;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -1; }
    sz = ftell(f);
    if (sz < 0) { fclose(f); return -1; }
    rewind(f);
    *out = (uint8_t *)malloc((size_t)sz);
    if (!*out) { fclose(f); return -1; }
    if (fread(*out, 1, (size_t)sz, f) != (size_t)sz) { free(*out); fclose(f); return -1; }
    fclose(f);
    *n = (size_t)sz;
    return 0;
}

int main(int argc, char **argv) {
    uint8_t *buf = NULL, root[32];
    size_t n = 0;
    char hex[65];
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return self_test();
    if (argc >= 3 && strcmp(argv[1], "--root") == 0) {
        if (load_file(argv[2], &buf, &n) != 0) return 1;
        if (merkle_root(buf, n, root) != 0) { free(buf); return 1; }
        lin_sha256_hex(root, hex);
        printf("%s\n", hex);
        free(buf);
        return 0;
    }
    fprintf(stderr, "usage: verify_u512_receipt --self-test | --root <lnr1.bin>\n");
    return 2;
}
