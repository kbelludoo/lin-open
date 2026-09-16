/*
 * C11 auditor for LNR1 (240B) and LCR2 (208B) receipts. Zero LIN VM.
 * LNR1 domains: LIN:U512:LEAF:1 / LIN:U512:NODE:1
 * LCR2 domains: LIN:LEAF:1 / LIN:NODE:1
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../../transpile/c/lin_c/lin_sha256.h"

static const uint8_t DOM_LNR_L[] = "LIN:U512:LEAF:1";
static const uint8_t DOM_LNR_N[] = "LIN:U512:NODE:1";
static const uint8_t DOM_LCR_L[] = "LIN:LEAF:1";
static const uint8_t DOM_LCR_N[] = "LIN:NODE:1";
static const uint8_t DOM_GE_L[] = "LIN:U512:GE:LEAF:1";
static const uint8_t DOM_GE_N[] = "LIN:U512:GE:NODE:1";
static const uint8_t DOM_RI_L[] = "LIN:U512:RI:LEAF:1";
static const uint8_t DOM_RI_N[] = "LIN:U512:RI:NODE:1";

static void h_leaf(const uint8_t *dom, size_t dlen, const uint8_t *rec, size_t rsz, uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, dom, dlen);
    lin_sha256_update(&ctx, rec, rsz);
    lin_sha256_final(&ctx, out);
}

static void h_node(const uint8_t *dom, size_t dlen, const uint8_t l[32], const uint8_t r[32], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, dom, dlen);
    lin_sha256_update(&ctx, l, 32);
    lin_sha256_update(&ctx, r, 32);
    lin_sha256_final(&ctx, out);
}

static int merkle_root(const uint8_t *recs, size_t nbytes, size_t rsz,
                       const uint8_t *dl, size_t dll, const uint8_t *dn, size_t dnl,
                       uint8_t root[32]) {
    if (rsz == 0 || nbytes % rsz != 0 || nbytes == 0) return -1;
    size_t n = nbytes / rsz;
    uint8_t *nodes = (uint8_t *)malloc(n * 32);
    if (!nodes) return -1;
    for (size_t i = 0; i < n; i++) h_leaf(dl, dll, recs + i * rsz, rsz, nodes + i * 32);
    while (n > 1) {
        size_t nn = (n + 1) / 2;
        for (size_t i = 0; i < n; i += 2) {
            const uint8_t *L = nodes + i * 32;
            const uint8_t *R = (i + 1 < n) ? nodes + (i + 1) * 32 : L;
            uint8_t tmp[32];
            h_node(dn, dnl, L, R, tmp);
            memcpy(nodes + (i / 2) * 32, tmp, 32);
        }
        n = nn;
    }
    memcpy(root, nodes, 32);
    free(nodes);
    return 0;
}

static void fill_dummy(uint8_t rec[240], uint8_t tag) {
    memset(rec, 0, 240);
    memcpy(rec, "LNR1", 4);
    rec[4] = 1;
    rec[5] = 2;
    rec[56 + 31] = tag;
}

static int self_test(void) {
    uint8_t recs[2 * 240], root[32], tamp[32], recs2[2 * 240];
    char hex[65], hex2[65];
    fill_dummy(recs, 1);
    fill_dummy(recs + 240, 2);
    if (merkle_root(recs, sizeof recs, 240, DOM_LNR_L, sizeof(DOM_LNR_L) - 1,
                    DOM_LNR_N, sizeof(DOM_LNR_N) - 1, root) != 0) return 1;
    memcpy(recs2, recs, sizeof recs);
    recs2[56 + 31] ^= 1;
    if (merkle_root(recs2, sizeof recs2, 240, DOM_LNR_L, sizeof(DOM_LNR_L) - 1,
                    DOM_LNR_N, sizeof(DOM_LNR_N) - 1, tamp) != 0) return 1;
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

static int dump_root(const char *path, size_t rsz, const uint8_t *dl, size_t dll,
                     const uint8_t *dn, size_t dnl) {
    uint8_t *buf = NULL, root[32];
    size_t n = 0;
    char hex[65];
    if (load_file(path, &buf, &n) != 0) return 1;
    if (merkle_root(buf, n, rsz, dl, dll, dn, dnl, root) != 0) { free(buf); return 1; }
    lin_sha256_hex(root, hex);
    printf("%s\n", hex);
    free(buf);
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return self_test();
    if (argc >= 3 && strcmp(argv[1], "--root") == 0)
        return dump_root(argv[2], 240, DOM_LNR_L, sizeof(DOM_LNR_L) - 1,
                         DOM_LNR_N, sizeof(DOM_LNR_N) - 1);
    if (argc >= 3 && strcmp(argv[1], "--lcr2-root") == 0)
        return dump_root(argv[2], 208, DOM_LCR_L, sizeof(DOM_LCR_L) - 1,
                         DOM_LCR_N, sizeof(DOM_LCR_N) - 1);
    if (argc >= 3 && strcmp(argv[1], "--lge1-root") == 0)
        return dump_root(argv[2], 208, DOM_GE_L, sizeof(DOM_GE_L) - 1,
                         DOM_GE_N, sizeof(DOM_GE_N) - 1);
    if (argc >= 3 && strcmp(argv[1], "--lri1-root") == 0)
        return dump_root(argv[2], 240, DOM_RI_L, sizeof(DOM_RI_L) - 1,
                         DOM_RI_N, sizeof(DOM_RI_N) - 1);
    fprintf(stderr,
            "usage: verify_u512_receipt --self-test | --root <lnr1.bin> "
            "| --lcr2-root <lcr2.bin> | --lge1-root <lge1.bin> | --lri1-root <lri1.bin>\n");
    return 2;
}
