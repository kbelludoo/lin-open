/*
 * Independent GNU MP oracle (not TCB).
 * Binds libgmp.so.10 at runtime (dlopen) so this file does not need
 * gmp.h and is not linked into the LIN compiler TCB.
 * EXPERIMENTAL: FullMath width (512-bit product), not CRT/mulmod.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int alloc;
    int size;
    unsigned long *d;
} mpz_s;

typedef void (*fn_init)(mpz_s *);
typedef void (*fn_clear)(mpz_s *);
typedef void (*fn_import)(mpz_s *, size_t, int, size_t, int, size_t, const void *);
typedef void *(*fn_export)(void *, size_t *, int, size_t, int, size_t, const mpz_s *);
typedef void (*fn_mul)(mpz_s *, const mpz_s *, const mpz_s *);
typedef void (*fn_tdiv_qr)(mpz_s *, mpz_s *, const mpz_s *, const mpz_s *);
typedef void (*fn_add)(mpz_s *, const mpz_s *, const mpz_s *);
typedef int (*fn_cmp)(const mpz_s *, const mpz_s *);

static fn_init p_init;
static fn_clear p_clear;
static fn_import p_import;
static fn_export p_export;
static fn_mul p_mul;
static fn_tdiv_qr p_tdiv_qr;
static fn_add p_add;
static fn_cmp p_cmp;
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

static int load_gmp(void) {
    lib = dlopen("libgmp.so.10", RTLD_NOW);
    if (!lib) lib = dlopen("libgmp.so", RTLD_NOW);
    if (!lib) {
        fprintf(stderr, "dlopen libgmp: %s\n", dlerror());
        return -1;
    }
#define SYM(dst, typ, name) do { \
    dst = (typ)dlsym(lib, name); \
    if (!dst) { fprintf(stderr, "dlsym %s\n", name); return -1; } \
} while (0)
    SYM(p_init, fn_init, "__gmpz_init");
    SYM(p_clear, fn_clear, "__gmpz_clear");
    SYM(p_import, fn_import, "__gmpz_import");
    SYM(p_export, fn_export, "__gmpz_export");
    SYM(p_mul, fn_mul, "__gmpz_mul");
    SYM(p_tdiv_qr, fn_tdiv_qr, "__gmpz_tdiv_qr");
    SYM(p_add, fn_add, "__gmpz_add");
    SYM(p_cmp, fn_cmp, "__gmpz_cmp");
#undef SYM
    return 0;
}

static void mpz_from_be(mpz_s *z, const uint8_t *be, int n) {
    p_init(z);
    p_import(z, (size_t)n, 1, 1, 1, 0, be);
}

static int mpz_to_be(const mpz_s *z, uint8_t *be, int n) {
    uint8_t tmp[128];
    size_t count = 0;
    memset(be, 0, (size_t)n);
    if (z->size == 0) return 1;
    if (z->size < 0) return 0;
    memset(tmp, 0, sizeof tmp);
    p_export(tmp, &count, 1, 1, 1, 0, z);
    if (count > (size_t)n) return 0;
    memcpy(be + n - (int)count, tmp, count);
    return 1;
}

static int ge512(const uint8_t a[64], const uint8_t b[64]) {
    mpz_s A, B;
    int g;
    mpz_from_be(&A, a, 64);
    mpz_from_be(&B, b, 64);
    g = p_cmp(&A, &B) >= 0 ? 1 : 0;
    p_clear(&A);
    p_clear(&B);
    return g;
}

static int mul512(const uint8_t a[32], const uint8_t b[32], uint8_t lo[32], uint8_t hi[32]) {
    mpz_s A, B, N;
    uint8_t full[64];
    int rc = -2;
    mpz_from_be(&A, a, 32);
    mpz_from_be(&B, b, 32);
    p_init(&N);
    p_mul(&N, &A, &B);
    if (!mpz_to_be(&N, full, 64)) goto done;
    memcpy(hi, full, 32);
    memcpy(lo, full + 32, 32);
    rc = 1;
done:
    p_clear(&A); p_clear(&B); p_clear(&N);
    return rc;
}

static int muldiv256(const uint8_t a[32], const uint8_t b[32], const uint8_t d[32],
                     uint8_t q[32], uint8_t r[32]) {
    mpz_s A, B, D, N, Q, R, QD, SUM, MAX;
    uint8_t maxb[32];
    int rc = -2;
    memset(q, 0, 32);
    memset(r, 0, 32);
    mpz_from_be(&A, a, 32);
    mpz_from_be(&B, b, 32);
    mpz_from_be(&D, d, 32);
    p_init(&N); p_init(&Q); p_init(&R); p_init(&QD); p_init(&SUM); p_init(&MAX);
    if (D.size == 0) { rc = -1; goto done; }
    p_mul(&N, &A, &B);
    p_tdiv_qr(&Q, &R, &N, &D);
    memset(maxb, 0xff, 32);
    p_import(&MAX, 32, 1, 1, 1, 0, maxb);
    if (p_cmp(&Q, &MAX) > 0) { rc = -2; goto done; }
    p_mul(&QD, &Q, &D);
    p_add(&SUM, &QD, &R);
    if (p_cmp(&SUM, &N) != 0) goto done;
    if (p_cmp(&R, &D) >= 0) goto done;
    if (!mpz_to_be(&Q, q, 32) || !mpz_to_be(&R, r, 32)) goto done;
    rc = 1;
done:
    p_clear(&A); p_clear(&B); p_clear(&D); p_clear(&N);
    p_clear(&Q); p_clear(&R); p_clear(&QD); p_clear(&SUM); p_clear(&MAX);
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
    memset(A, 0, 64); A[31] = 1;
    memset(B, 0, 64); memset(B + 32, 0xff, 32);
    if (ge512(A, B) != 1 || ge512(B, A) != 0 || ge512(A, A) != 1) {
        fprintf(stderr, "FAIL ge512 2^256 vs 2^256-1\n");
        fail = 1;
    }
    if (fail) return 1;
    printf("SELFTEST_PASS gmp_mpz q*d+r==n ge512\n");
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
    fprintf(stderr, "BATCH_N=%d GMP_MPZ_CONSENSUS\n", nvec);
    return 0;
}

int main(int argc, char **argv) {
    if (load_gmp() != 0) {
        fprintf(stderr, "FAIL load libgmp mpz symbols\n");
        return 2;
    }
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return selftest();
    if (argc >= 2 && strcmp(argv[1], "--batch") == 0) return run_batch();
    fprintf(stderr, "usage: u512_gmp_oracle --self-test | --batch\n");
    return 2;
}
