/*
 * Independent OpenSSL BIGNUM oracle (not TCB).
 * Binds libcrypto.so.3 at runtime (dlopen) so this file does not need
 * OpenSSL headers and is not linked into the LIN compiler TCB.
 * EXPERIMENTAL: FullMath width (512-bit product), not CRT/mulmod.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void BN;
typedef void BN_CTX;
typedef BN *(*fn_BN_new)(void);
typedef void (*fn_BN_free)(BN *);
typedef BN *(*fn_BN_bin2bn)(const unsigned char *, int, BN *);
typedef int (*fn_BN_bn2binpad)(const BN *, unsigned char *, int);
typedef int (*fn_BN_mul)(BN *, const BN *, const BN *, BN_CTX *);
typedef int (*fn_BN_div)(BN *, BN *, const BN *, const BN *, BN_CTX *);
typedef int (*fn_BN_add)(BN *, const BN *, const BN *);
typedef int (*fn_BN_ucmp)(const BN *, const BN *);
typedef int (*fn_BN_is_zero)(const BN *);
typedef BN_CTX *(*fn_BN_CTX_new)(void);
typedef void (*fn_BN_CTX_free)(BN_CTX *);

static fn_BN_new p_BN_new;
static fn_BN_free p_BN_free;
static fn_BN_bin2bn p_BN_bin2bn;
static fn_BN_bn2binpad p_BN_bn2binpad;
static fn_BN_mul p_BN_mul;
static fn_BN_div p_BN_div;
static fn_BN_add p_BN_add;
static fn_BN_ucmp p_BN_ucmp;
static fn_BN_is_zero p_BN_is_zero;
static fn_BN_CTX_new p_BN_CTX_new;
static fn_BN_CTX_free p_BN_CTX_free;
static void *lib;

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_be(const char *s, uint8_t *out, size_t n) {
    size_t len;
    memset(out, 0, n);
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    len = strlen(s);
    if (len > n * 2) return -1;
    for (size_t i = 0; i < len; i++) {
        int v = hexval((unsigned char)s[len - 1 - i]);
        if (v < 0) return -1;
        if ((i & 1u) == 0) out[n - 1 - (i / 2)] = (uint8_t)v;
        else out[n - 1 - (i / 2)] |= (uint8_t)(v << 4);
    }
    return 0;
}

static void hex_of(const uint8_t *p, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[2 * i] = H[p[i] >> 4];
        out[2 * i + 1] = H[p[i] & 15];
    }
    out[2 * n] = 0;
}

static int load_crypto(void) {
    lib = dlopen("libcrypto.so.3", RTLD_NOW);
    if (!lib) lib = dlopen("libcrypto.so", RTLD_NOW);
    if (!lib) {
        fprintf(stderr, "dlopen libcrypto: %s\n", dlerror());
        return -1;
    }
#define SYM(name) do { p_##name = (fn_##name)dlsym(lib, #name); if (!p_##name) return -1; } while (0)
    SYM(BN_new); SYM(BN_free); SYM(BN_bin2bn); SYM(BN_bn2binpad);
    SYM(BN_mul); SYM(BN_div); SYM(BN_add); SYM(BN_ucmp); SYM(BN_is_zero);
    SYM(BN_CTX_new); SYM(BN_CTX_free);
#undef SYM
    return 0;
}

static BN *bn_be(const uint8_t *be, int n) {
    return p_BN_bin2bn(be, n, NULL);
}

static int bn_out32(const BN *x, uint8_t be[32]) {
    return p_BN_bn2binpad(x, be, 32) == 32;
}

static int ge512(const uint8_t a[64], const uint8_t b[64]) {
    BN *A = bn_be(a, 64), *B = bn_be(b, 64);
    int g;
    if (!A || !B) return -2;
    g = p_BN_ucmp(A, B) >= 0 ? 1 : 0;
    p_BN_free(A);
    p_BN_free(B);
    return g;
}

static int mul512(const uint8_t a[32], const uint8_t b[32], uint8_t lo[32], uint8_t hi[32]) {
    BN_CTX *ctx = p_BN_CTX_new();
    BN *A = bn_be(a, 32), *B = bn_be(b, 32), *N = p_BN_new();
    uint8_t full[64];
    int rc = -2;
    if (!ctx || !A || !B || !N) goto done;
    if (p_BN_mul(N, A, B, ctx) != 1) goto done;
    if (p_BN_bn2binpad(N, full, 64) != 64) goto done;
    memcpy(hi, full, 32);
    memcpy(lo, full + 32, 32);
    rc = 1;
done:
    if (N) p_BN_free(N);
    if (A) p_BN_free(A);
    if (B) p_BN_free(B);
    if (ctx) p_BN_CTX_free(ctx);
    return rc;
}

static int muldiv256(const uint8_t a[32], const uint8_t b[32], const uint8_t d[32],
                     uint8_t q[32], uint8_t r[32]) {
    BN_CTX *ctx = p_BN_CTX_new();
    BN *A = bn_be(a, 32), *B = bn_be(b, 32), *D = bn_be(d, 32);
    BN *N = p_BN_new(), *Q = p_BN_new(), *R = p_BN_new();
    BN *QD = p_BN_new(), *SUM = p_BN_new(), *MAX = p_BN_new();
    uint8_t maxb[32];
    int rc = -2;
    memset(q, 0, 32);
    memset(r, 0, 32);
    if (!ctx || !A || !B || !D || !N || !Q || !R || !QD || !SUM || !MAX) goto done;
    if (p_BN_is_zero(D)) { rc = -1; goto done; }
    if (p_BN_mul(N, A, B, ctx) != 1) goto done;
    if (p_BN_div(Q, R, N, D, ctx) != 1) goto done;
    memset(maxb, 0xff, 32);
    if (!p_BN_bin2bn(maxb, 32, MAX)) goto done;
    if (p_BN_ucmp(Q, MAX) > 0) { rc = -2; goto done; }
    if (p_BN_mul(QD, Q, D, ctx) != 1) goto done;
    if (p_BN_add(SUM, QD, R) != 1) goto done;
    if (p_BN_ucmp(SUM, N) != 0) goto done;
    if (p_BN_ucmp(R, D) >= 0) goto done;
    if (!bn_out32(Q, q) || !bn_out32(R, r)) goto done;
    rc = 1;
done:
    if (A) p_BN_free(A);
    if (B) p_BN_free(B);
    if (D) p_BN_free(D);
    if (N) p_BN_free(N);
    if (Q) p_BN_free(Q);
    if (R) p_BN_free(R);
    if (QD) p_BN_free(QD);
    if (SUM) p_BN_free(SUM);
    if (MAX) p_BN_free(MAX);
    if (ctx) p_BN_CTX_free(ctx);
    return rc;
}

static int expect_st(int st, int want, const char *m) {
    if (st != want) {
        fprintf(stderr, "FAIL %s status=%d want=%d\n", m, st, want);
        return 1;
    }
    return 0;
}

static int selftest(void) {
    uint8_t a[32], b[32], d[32], q[32], r[32], lo[32], hi[32], A[64], B[64];
    char qhex[65];
    int fail = 0, st;
    memset(a, 0, 32); memset(b, 0, 32); memset(d, 0, 32);
    a[31] = 7; b[31] = 9; d[31] = 2;
    st = muldiv256(a, b, d, q, r);
    fail |= expect_st(st, 1, "7*9/2");
    if (q[31] != 31 || r[31] != 1) {
        fprintf(stderr, "FAIL 7*9/2 bytes\n");
        fail = 1;
    }
    memset(a, 0xff, 32); memset(b, 0xff, 32);
    st = mul512(a, b, lo, hi);
    fail |= expect_st(st, 1, "max*max");
    if (lo[31] != 1 || hi[31] != 0xfe) {
        fprintf(stderr, "FAIL max^2 lo/hi\n");
        fail = 1;
    }
    memset(a, 0, 32); a[0] = 0x80;
    memset(b, 0, 32); b[31] = 2;
    memset(d, 0, 32); d[31] = 3;
    st = muldiv256(a, b, d, q, r);
    fail |= expect_st(st, 1, "2^255*2/3");
    if (r[31] != 1 || q[31] != 0x55) {
        hex_of(q, 32, qhex);
        fprintf(stderr, "FAIL 2^255*2/3 q=%s r0=%u\n", qhex, r[31]);
        fail = 1;
    }
    memset(d, 0, 32);
    memset(a, 0, 32); a[31] = 1;
    memset(b, 0, 32); b[31] = 1;
    fail |= expect_st(muldiv256(a, b, d, q, r), -1, "d=0");
    memset(a, 0, 32); a[0] = 0x80;
    memset(b, 0, 32); b[31] = 2;
    memset(d, 0, 32); d[31] = 1;
    fail |= expect_st(muldiv256(a, b, d, q, r), -2, "q overflow");
    memset(A, 0, 64); A[31] = 1; /* 2^256 */
    memset(B, 0, 64); memset(B + 32, 0xff, 32); /* 2^256-1 */
    if (ge512(A, B) != 1 || ge512(B, A) != 0 || ge512(A, A) != 1) {
        fprintf(stderr, "FAIL ge512 2^256 vs 2^256-1\n");
        fail = 1;
    }
    if (fail) return 1;
    printf("SELFTEST_PASS openssl_bn q*d+r==n ge512\n");
    return 0;
}

static int run_batch(void) {
    char line[1024], op[16], ha[260], hb[260], hd[130];
    uint8_t bea[64], beb[64], bed[32], beq[32], ber[32];
    char qhex[129], rhex[65];
    int nvec = 0;
    while (fgets(line, sizeof line, stdin)) {
        int nf = sscanf(line, "%15s %259s %259s %129s", op, ha, hb, hd);
        if (nf < 3) continue;
        if (strcmp(op, "MUL") == 0) {
            if (parse_hex_be(ha, bea, 32) || parse_hex_be(hb, beb, 32)) return 1;
            int st = mul512(bea, beb, beq, ber);
            hex_of(beq, 32, qhex); hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st, qhex, rhex);
        } else if (strcmp(op, "MULDIV") == 0) {
            if (nf < 4 || parse_hex_be(ha, bea, 32) || parse_hex_be(hb, beb, 32)
                || parse_hex_be(hd, bed, 32)) return 1;
            int st = muldiv256(bea, beb, bed, beq, ber);
            hex_of(beq, 32, qhex); hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st, qhex, rhex);
        } else if (strcmp(op, "GE") == 0) {
            if (parse_hex_be(ha, bea, 64) || parse_hex_be(hb, beb, 64)) return 1;
            printf("%d\n", ge512(bea, beb));
        } else {
            fprintf(stderr, "unknown op %s\n", op);
            return 1;
        }
        nvec++;
    }
    fprintf(stderr, "BATCH_N=%d OPENSSL_BN_CONSENSUS\n", nvec);
    return 0;
}

int main(int argc, char **argv) {
    if (load_crypto() != 0) {
        fprintf(stderr, "FAIL load libcrypto BN symbols\n");
        return 2;
    }
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return selftest();
    if (argc >= 2 && strcmp(argv[1], "--batch") == 0) return run_batch();
    fprintf(stderr, "usage: u512_openssl_bn --self-test | --batch\n");
    return 2;
}
