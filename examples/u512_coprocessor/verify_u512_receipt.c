/* Independent LNR1 auditor — C11 + lin_sha256, no Python, no LinVM.
 * Reconstructs q*d+r==n with 64-bit schoolbook and recomputes Merkle.
 * Tamper-evidence + identity. Not zk. Not in the LIN TCB. */
#include "lin_sha256.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REC 240
static const uint8_t DOM_LEAF[] = "LIN:U512:LEAF:1";
static const uint8_t DOM_NODE[] = "LIN:U512:NODE:1";
static uint64_t u64le(const uint8_t *p) {
    uint64_t v = 0;
    int i;
    for (i = 0; i < 8; i++) v |= ((uint64_t)p[i]) << (8 * i);
    return v;
}
static int64_t i64le(const uint8_t *p) { return (int64_t)u64le(p); }
static void be32_words(const uint8_t *p, uint64_t w[4]) {
    int i, b;
    for (i = 0; i < 4; i++) {
        w[3 - i] = 0;
        for (b = 0; b < 8; b++) w[3 - i] = (w[3 - i] << 8) | p[i * 8 + b];
    }
}
static int hex_nibble(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static int hex_decode(const char *s, uint8_t *out, size_t n) {
    size_t i;
    for (i = 0; i < n; i++) {
        int hi = hex_nibble(s[2 * i]), lo = hex_nibble(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return 0;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 1;
}
static void leaf_hash(const uint8_t rec[REC], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_LEAF, sizeof(DOM_LEAF) - 1);
    lin_sha256_update(&ctx, rec, REC);
    lin_sha256_final(&ctx, out);
}
static void parent_hash(const uint8_t l[32], const uint8_t r[32], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_NODE, sizeof(DOM_NODE) - 1);
    lin_sha256_update(&ctx, l, 32);
    lin_sha256_update(&ctx, r, 32);
    lin_sha256_final(&ctx, out);
}
static void merkle_root(uint8_t (*leaves)[32], size_t n, uint8_t out[32]) {
    uint8_t cur[64][32];
    size_t count = n, i;
    if (n == 0 || n > 64) { memset(out, 0, 32); return; }
    memcpy(cur, leaves, n * 32);
    while (count > 1) {
        size_t nxt = 0;
        for (i = 0; i < count; i += 2) {
            const uint8_t *right = (i + 1 < count) ? cur[i + 1] : cur[i];
            parent_hash(cur[i], right, cur[nxt]);
            nxt++;
        }
        count = nxt;
    }
    memcpy(out, cur[0], 32);
}
static void mul64(uint64_t n[8], const uint64_t a[4], const uint64_t b[4]) {
    int i, j, k;
    unsigned __int128 carry, t;
    memset(n, 0, 8 * sizeof(uint64_t));
    for (i = 0; i < 4; i++) {
        carry = 0;
        for (j = 0; j < 4; j++) {
            t = (unsigned __int128)n[i + j] + (unsigned __int128)a[i] * b[j] + carry;
            n[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (k < 8 && carry != 0) {
            t = (unsigned __int128)n[k] + carry;
            n[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}
static int zero256(const uint64_t w[4]) { return (w[0] | w[1] | w[2] | w[3]) == 0; }
static int r_lt_d(const uint64_t r[4], const uint64_t d[4]) {
    int j;
    for (j = 3; j >= 0; j--) {
        if (r[j] < d[j]) return 1;
        if (r[j] > d[j]) return 0;
    }
    return 0;
}
static int q_fits_u256(const uint64_t n[8], const uint64_t d[4]) {
    /* q = n/d > 2^256-1  iff n >= d << 256 */
    uint64_t shifted[8];
    int j;
    if (zero256(d)) return 0;
    memset(shifted, 0, sizeof(shifted));
    memcpy(shifted + 4, d, 4 * sizeof(uint64_t));
    for (j = 7; j >= 0; j--) {
        if (n[j] > shifted[j]) return 0;
        if (n[j] < shifted[j]) return 1;
    }
    return 0; /* n == d<<256 => q == 2^256, overflow */
}
static int identity_ok(const uint8_t rec[REC]) {
    uint64_t a[4], b[4], d[4], q[4], r[4], n[8], recon[8];
    int64_t st;
    unsigned __int128 acc;
    int i;
    if (memcmp(rec, "LNR1", 4) != 0 || rec[4] != 1 || rec[5] != 1) return 0;
    be32_words(rec + 56, a);
    be32_words(rec + 88, b);
    be32_words(rec + 120, d);
    be32_words(rec + 152, q);
    be32_words(rec + 184, r);
    st = i64le(rec + 224);
    mul64(n, a, b);
    if (st == -1) return zero256(d);
    if (st == -2) return !zero256(d) && !q_fits_u256(n, d);
    if (st != 1) return 0;
    if (zero256(d) || !r_lt_d(r, d)) return 0;
    mul64(recon, q, d);
    acc = 0;
    for (i = 0; i < 8; i++) {
        acc += recon[i];
        if (i < 4) acc += r[i];
        recon[i] = (uint64_t)acc;
        acc >>= 64;
    }
    if (acc != 0) return 0;
    return memcmp(recon, n, sizeof(recon)) == 0;
}
static int verify_vec(FILE *fp) {
    char line[1024];
    uint8_t image[32], root[32], got[32];
    uint8_t recs[64][REC];
    uint8_t leaves[64][32];
    size_t n = 0;
    int have_img = 0, have_root = 0;
    memset(image, 0, 32);
    memset(root, 0, 32);
    while (fgets(line, sizeof(line), fp)) {
        size_t len = strlen(line);
        while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
        if (len == 0 || line[0] == '#') continue;
        if (strncmp(line, "IMAGE ", 6) == 0) {
            if (strlen(line + 6) != 64 || !hex_decode(line + 6, image, 32)) return 2;
            have_img = 1;
            continue;
        }
        if (strncmp(line, "ROOT ", 5) == 0) {
            if (strlen(line + 5) != 64 || !hex_decode(line + 5, root, 32)) return 2;
            have_root = 1;
            continue;
        }
        if (len != REC * 2) return 2;
        if (n >= 64) return 2;
        if (!hex_decode(line, recs[n], REC)) return 2;
        if (have_img && memcmp(recs[n] + 8, image, 32) != 0) {
            printf("FAIL BAD_IMAGE leaf=%zu\n", n);
            return 1;
        }
        if (!identity_ok(recs[n])) {
            printf("FAIL BAD_IDENTITY leaf=%zu\n", n);
            return 1;
        }
        leaf_hash(recs[n], leaves[n]);
        n++;
    }
    if (!have_root || n == 0) {
        printf("FAIL BAD_VEC\n");
        return 1;
    }
    merkle_root(leaves, n, got);
    if (memcmp(got, root, 32) != 0) {
        printf("FAIL BAD_ROOT\n");
        return 1;
    }
    printf("PASS LNR1 C11 leaves=%zu identity+merkle\n", n);
    return 0;
}
static void pack_demo(uint8_t rec[REC], uint64_t leaf, uint64_t a0, uint64_t b0, uint64_t d0) {
    uint64_t n, q, r;
    int64_t st;
    memset(rec, 0, REC);
    memcpy(rec, "LNR1", 4);
    rec[4] = 1;
    rec[5] = 1;
    rec[48] = (uint8_t)leaf;
    rec[87] = (uint8_t)a0;
    rec[119] = (uint8_t)b0;
    rec[151] = (uint8_t)d0;
    n = a0 * b0;
    if (d0 == 0) {
        st = -1; q = 0; r = 0;
    } else {
        q = n / d0;
        r = n % d0;
        st = 1;
    }
    rec[183] = (uint8_t)q;
    rec[215] = (uint8_t)r;
    rec[216] = 1;
    rec[224] = (uint8_t)(uint64_t)st;
    if (st < 0) memset(rec + 224, 0xff, 8);
}
static int selftest(void) {
    uint8_t r0[REC], r1[REC], bad[REC];
    uint8_t leaves[2][32], root[32];
    FILE *t;
    pack_demo(r0, 1, 7, 9, 2);
    pack_demo(r1, 2, 1, 1, 1);
    if (!identity_ok(r0) || !identity_ok(r1)) {
        printf("SELFTEST FAIL clean identity\n");
        return 1;
    }
    leaf_hash(r0, leaves[0]);
    leaf_hash(r1, leaves[1]);
    merkle_root(leaves, 2, root);
    t = tmpfile();
    if (!t) return 1;
    {
        char hex[REC * 2 + 1];
        size_t i;
        fprintf(t, "IMAGE ");
        for (i = 0; i < 32; i++) fprintf(t, "00");
        fprintf(t, "\nROOT ");
        for (i = 0; i < 32; i++) fprintf(t, "%02x", root[i]);
        fprintf(t, "\n");
        for (i = 0; i < REC; i++) sprintf(hex + 2 * i, "%02x", r0[i]);
        fprintf(t, "%s\n", hex);
        for (i = 0; i < REC; i++) sprintf(hex + 2 * i, "%02x", r1[i]);
        fprintf(t, "%s\n", hex);
    }
    rewind(t);
    if (verify_vec(t) != 0) {
        printf("SELFTEST FAIL clean vec\n");
        fclose(t);
        return 1;
    }
    fclose(t);
    memcpy(bad, r0, REC);
    bad[56] ^= 1;
    if (identity_ok(bad)) {
        printf("SELFTEST FAIL 1-bit tamper ACCEPTED\n");
        return 1;
    }
    printf("SELFTEST PASS LNR1 C11 identity + 1-bit tamper REJECT\n");
    return 0;
}
int main(int argc, char **argv) {
    FILE *fp;
    int rc;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | lnr1 <vec>\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "lnr1") == 0 && argc == 3) {
        fp = fopen(argv[2], "r");
        if (!fp) { perror(argv[2]); return 2; }
        rc = verify_vec(fp);
        fclose(fp);
        return rc;
    }
    fprintf(stderr, "unknown cmd\n");
    return 2;
}
