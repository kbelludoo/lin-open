/*
 * Independent C11 oracle for 512-bit coprocessor math.
 *
 * Width matches Uniswap v3 FullMath (floor(a*b/d) with 512-bit product).
 * Algorithm is NOT CRT/mulmod: 64-bit schoolbook + restoring division.
 * Consensus with Python int is required before any LIN comparison.
 *
 * This file is not linked into the LIN compiler TCB.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WMASK 0xffffffffffffffffULL

static void zero8(uint64_t x[8]) {
    memset(x, 0, 8 * sizeof(uint64_t));
}

static void zero4(uint64_t x[4]) {
    memset(x, 0, 4 * sizeof(uint64_t));
}

static int is_zero4(const uint64_t x[4]) {
    return x[0] == 0 && x[1] == 0 && x[2] == 0 && x[3] == 0;
}

static int ge512(const uint64_t a[8], const uint64_t b[8]) {
    int i;
    for (i = 7; i >= 0; i--) {
        if (a[i] > b[i]) return 1;
        if (a[i] < b[i]) return 0;
    }
    return 1;
}

static void mul256(const uint64_t a[4], const uint64_t b[4], uint64_t r[8]) {
    int i, j, k;
    zero8(r);
    for (i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (j = 0; j < 4; j++) {
            unsigned __int128 t = (unsigned __int128)r[i + j]
                + (unsigned __int128)a[i] * b[j] + carry;
            r[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (carry != 0 && k < 8) {
            unsigned __int128 t = (unsigned __int128)r[k] + carry;
            r[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}

static void sub_den(uint64_t rem[8], const uint64_t d[4]) {
    unsigned __int128 borrow = 0;
    int i;
    for (i = 0; i < 8; i++) {
        unsigned __int128 dv = (i < 4) ? d[i] : 0;
        unsigned __int128 left = rem[i];
        unsigned __int128 right = dv + borrow;
        if (left < right) {
            rem[i] = (uint64_t)(left + (((unsigned __int128)1) << 64) - right);
            borrow = 1;
        } else {
            rem[i] = (uint64_t)(left - right);
            borrow = 0;
        }
    }
}

/* Restoring 512/256. status: 1 ok, -1 d=0, -2 q overflow. */
static int div512(const uint64_t n[8], const uint64_t d[4],
                  uint64_t q[4], uint64_t r[4]) {
    uint64_t rem[8];
    uint64_t den[8];
    int bit, i;
    zero4(q);
    zero4(r);
    if (is_zero4(d)) return -1;
    zero8(rem);
    zero8(den);
    den[0] = d[0]; den[1] = d[1]; den[2] = d[2]; den[3] = d[3];
    for (bit = 511; bit >= 0; bit--) {
        uint64_t inbit = (n[bit / 64] >> (bit % 64)) & 1ULL;
        uint64_t c = inbit;
        for (i = 0; i < 8; i++) {
            uint64_t newc = rem[i] >> 63;
            rem[i] = (rem[i] << 1) | c;
            c = newc;
        }
        if (c != 0 || ge512(rem, den)) {
            if (bit >= 256) return -2;
            sub_den(rem, d);
            q[bit / 64] |= 1ULL << (bit % 64);
        }
    }
    r[0] = rem[0]; r[1] = rem[1]; r[2] = rem[2]; r[3] = rem[3];
    return 1;
}

static int muldiv(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                  uint64_t q[4], uint64_t r[4]) {
    uint64_t n[8];
    if (is_zero4(d)) {
        zero4(q);
        zero4(r);
        return -1;
    }
    mul256(a, b, n);
    return div512(n, d, q, r);
}

static int amm(const uint64_t ain[4], const uint64_t rin[4], const uint64_t rout[4],
               uint64_t q[4], uint64_t r[4]) {
    uint64_t fee[4], den[4];
    unsigned __int128 carry;
    int i;
    zero4(q);
    zero4(r);
    if (is_zero4(ain) || is_zero4(rin) || is_zero4(rout)) return -1;
    carry = 0;
    for (i = 0; i < 4; i++) {
        unsigned __int128 t = (unsigned __int128)ain[i] * 997u + carry;
        fee[i] = (uint64_t)t;
        carry = t >> 64;
    }
    if (carry != 0) return -2;
    carry = 0;
    for (i = 0; i < 4; i++) {
        unsigned __int128 t = (unsigned __int128)rin[i] * 1000u + fee[i] + carry;
        den[i] = (uint64_t)t;
        carry = t >> 64;
    }
    if (carry != 0) return -2;
    return muldiv(fee, rout, den, q, r);
}

static int parse_u64(const char *s, uint64_t *out) {
    char *end = NULL;
    unsigned long long v;
    if (!s || !*s) return 0;
    v = strtoull(s, &end, 0);
    if (end == s || (end && *end != '\0')) return 0;
    *out = (uint64_t)v;
    return 1;
}

static int parse_n(char **argv, int n, uint64_t *out) {
    int i;
    for (i = 0; i < n; i++) {
        if (!parse_u64(argv[i], &out[i])) return 0;
    }
    return 1;
}

static void print_words(const char *tag, const uint64_t *w, int n) {
    int i;
    printf("%s", tag);
    for (i = 0; i < n; i++) {
        printf("%s%" PRIu64, i ? " " : "", w[i]);
    }
    printf("\n");
}

static int selftest(void) {
    uint64_t a[4], b[4], d[4], n[8], q[4], r[4];
    int st, fail = 0;
    zero4(a); zero4(b); zero4(d);
    a[0] = 2; b[0] = 3;
    mul256(a, b, n);
    if (n[0] != 6 || n[1] || n[2] || n[3] || n[4] || n[5] || n[6] || n[7]) fail++;
    a[0] = 7; b[0] = 9; d[0] = 2;
    st = muldiv(a, b, d, q, r);
    if (st != 1 || q[0] != 31 || r[0] != 1) fail++;
    zero4(d);
    st = muldiv(a, b, d, q, r);
    if (st != -1) fail++;
    a[0] = a[1] = a[2] = a[3] = WMASK;
    b[0] = b[1] = b[2] = b[3] = WMASK;
    d[0] = 1; d[1] = d[2] = d[3] = 0;
    st = muldiv(a, b, d, q, r);
    if (st != -2) fail++;
    {
        uint64_t hi[8] = {0, 0, 0, 0, 0, 0, 0, 1};
        uint64_t lo[8] = {1, 0, 0, 0, 0, 0, 0, 0};
        if (!ge512(hi, lo) || ge512(lo, hi)) fail++;
        if (!ge512(lo, lo)) fail++;
    }
    if (fail) {
        fprintf(stderr, "u512_coprocessor_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("u512_coprocessor_c11 selftest PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t a[4], b[4], d[4], n[8], q[4], r[4];
    int st;
    const char *cmd;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest|mul|ge|div|muldiv|amm ...\n", argv[0]);
        return 2;
    }
    cmd = argv[1];
    zero4(a); zero4(b); zero4(d); zero8(n); zero4(q); zero4(r);
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "mul") == 0 && argc == 10) {
        if (!parse_n(argv + 2, 4, a) || !parse_n(argv + 6, 4, b)) return 2;
        mul256(a, b, n);
        print_words("p=", n, 8);
        return 0;
    }
    if (strcmp(cmd, "ge") == 0 && argc == 18) {
        uint64_t aa[8], bb[8];
        if (!parse_n(argv + 2, 8, aa) || !parse_n(argv + 10, 8, bb)) return 2;
        printf("ge=%d\n", ge512(aa, bb));
        return 0;
    }
    if (strcmp(cmd, "div") == 0 && argc == 14) {
        if (!parse_n(argv + 2, 8, n) || !parse_n(argv + 10, 4, d)) return 2;
        st = div512(n, d, q, r);
        printf("status=%d\n", st);
        print_words("q=", q, 4);
        print_words("r=", r, 4);
        return 0;
    }
    if (strcmp(cmd, "muldiv") == 0 && argc == 14) {
        if (!parse_n(argv + 2, 4, a) || !parse_n(argv + 6, 4, b) || !parse_n(argv + 10, 4, d))
            return 2;
        st = muldiv(a, b, d, q, r);
        printf("status=%d\n", st);
        print_words("q=", q, 4);
        print_words("r=", r, 4);
        return 0;
    }
    if (strcmp(cmd, "amm") == 0 && argc == 14) {
        if (!parse_n(argv + 2, 4, a) || !parse_n(argv + 6, 4, b) || !parse_n(argv + 10, 4, d))
            return 2;
        st = amm(a, b, d, q, r);
        printf("status=%d\n", st);
        print_words("q=", q, 4);
        print_words("r=", r, 4);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
