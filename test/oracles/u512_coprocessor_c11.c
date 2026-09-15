/*
 * Independent C11 oracle for 256x256->512 mul, 512-bit cmp, 512/256 div.
 *
 * Two limb widths (not the LIN 16-bit engine):
 *   1. 64-bit limbs + unsigned __int128 limb products
 *   2. 32-bit limbs + uint64 limb products
 * Consensus between (1) and (2) is required before any LIN comparison.
 * Python arbitrary-precision int is the third oracle (harness).
 *
 * This file is not linked into the LIN compiler TCB.
 * Spec: Uniswap v3 FullMath.mulDiv 512-bit intermediate (MIT).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W64MASK 0xffffffffffffffffULL
#define LIMB32  0xffffffffULL

static void zero8(uint64_t x[8]) {
    memset(x, 0, 8 * sizeof(uint64_t));
}

static int words_zero4(const uint64_t d[4]) {
    return d[0] == 0 && d[1] == 0 && d[2] == 0 && d[3] == 0;
}

static void mul256_64(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    int i, j, k;
    zero8(p);
    for (i = 0; i < 4; i++) {
        __uint128_t carry = 0;
        for (j = 0; j < 4; j++) {
            __uint128_t t = (__uint128_t)p[i + j] + (__uint128_t)a[i] * b[j] + carry;
            p[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (carry != 0 && k < 8) {
            __uint128_t t = (__uint128_t)p[k] + carry;
            p[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
        if (carry != 0) {
            zero8(p); /* should be unreachable for 256x256 */
        }
    }
}

static int cmp512_64(const uint64_t a[8], const uint64_t b[8]) {
    int i;
    for (i = 7; i >= 0; i--) {
        if (a[i] > b[i]) return 1;
        if (a[i] < b[i]) return -1;
    }
    return 0;
}

/* Restoring 512/256. status: 1 ok, -1 div0, -2 quotient does not fit uint256. */
static int div512_256_64(const uint64_t n[8], const uint64_t d4[4],
                         uint64_t q[4], uint64_t r[4]) {
    uint64_t d[8], rem[8];
    int bit, i;

    memset(q, 0, 4 * sizeof(uint64_t));
    memset(r, 0, 4 * sizeof(uint64_t));
    if (words_zero4(d4)) return -1;
    zero8(d);
    zero8(rem);
    d[0] = d4[0]; d[1] = d4[1]; d[2] = d4[2]; d[3] = d4[3];

    for (bit = 511; bit >= 0; bit--) {
        unsigned nlimb = (unsigned)bit / 64;
        unsigned npos = (unsigned)bit % 64;
        uint64_t in_bit = (n[nlimb] >> npos) & 1ULL;
        uint64_t carry = in_bit;
        for (i = 0; i < 8; i++) {
            uint64_t next = rem[i] >> 63;
            rem[i] = (rem[i] << 1) | carry;
            carry = next;
        }
        if (carry != 0) return -2;
        if (cmp512_64(rem, d) >= 0) {
            uint64_t borrow = 0;
            if (bit >= 256) return -2;
            q[bit / 64] |= (1ULL << (bit % 64));
            for (i = 0; i < 8; i++) {
                uint64_t dd = d[i];
                uint64_t val = rem[i];
                uint64_t nb = (val < dd) || ((val - dd) < borrow);
                rem[i] = val - dd - borrow;
                borrow = nb;
            }
        }
    }
    r[0] = rem[0]; r[1] = rem[1]; r[2] = rem[2]; r[3] = rem[3];
    return 1;
}

static void u256_to_u32(const uint64_t w[4], uint32_t o[8]) {
    int i;
    for (i = 0; i < 4; i++) {
        o[2 * i] = (uint32_t)(w[i] & LIMB32);
        o[2 * i + 1] = (uint32_t)(w[i] >> 32);
    }
}

static void u512_to_u32(const uint64_t w[8], uint32_t o[16]) {
    int i;
    for (i = 0; i < 8; i++) {
        o[2 * i] = (uint32_t)(w[i] & LIMB32);
        o[2 * i + 1] = (uint32_t)(w[i] >> 32);
    }
}

static void u32_to_u512(const uint32_t in[16], uint64_t w[8]) {
    int i;
    for (i = 0; i < 8; i++)
        w[i] = (uint64_t)in[2 * i] | ((uint64_t)in[2 * i + 1] << 32);
}

static void mul256_32(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    uint32_t aa[8], bb[8], pp[16];
    int i, j, k;
    u256_to_u32(a, aa);
    u256_to_u32(b, bb);
    memset(pp, 0, sizeof(pp));
    for (i = 0; i < 8; i++) {
        uint64_t carry = 0;
        for (j = 0; j < 8; j++) {
            uint64_t t = (uint64_t)pp[i + j] + (uint64_t)aa[i] * bb[j] + carry;
            pp[i + j] = (uint32_t)(t & LIMB32);
            carry = t >> 32;
        }
        k = i + 8;
        while (carry != 0 && k < 16) {
            uint64_t t = (uint64_t)pp[k] + carry;
            pp[k] = (uint32_t)(t & LIMB32);
            carry = t >> 32;
            k++;
        }
    }
    u32_to_u512(pp, p);
}

static int cmp512_32(const uint64_t a[8], const uint64_t b[8]) {
    uint32_t aa[16], bb[16];
    int i;
    u512_to_u32(a, aa);
    u512_to_u32(b, bb);
    for (i = 15; i >= 0; i--) {
        if (aa[i] > bb[i]) return 1;
        if (aa[i] < bb[i]) return -1;
    }
    return 0;
}

static int parse_i64(const char *s, uint64_t *out) {
    char *end = NULL;
    long long v;
    if (s == NULL || s[0] == '\0') return 0;
    v = strtoll(s, &end, 10);
    if (end == NULL || *end != '\0') return 0;
    *out = (uint64_t)(int64_t)v;
    return 1;
}

static void print8(const uint64_t w[8]) {
    int i;
    for (i = 0; i < 8; i++) {
        if (i) putchar(' ');
        printf("%lld", (long long)(int64_t)w[i]);
    }
    putchar('\n');
}

static void print4(const uint64_t w[4]) {
    int i;
    for (i = 0; i < 4; i++) {
        if (i) putchar(' ');
        printf("%lld", (long long)(int64_t)w[i]);
    }
}

static int loadn(char **argv, int start, uint64_t *dst, int n) {
    int i;
    for (i = 0; i < n; i++) {
        if (!parse_i64(argv[start + i], &dst[i])) return 0;
    }
    return 1;
}

static int selftest(void) {
    uint64_t a[4], b[4], d[4], n[8], p64[8], p32[8], q[4], r[4];
    uint64_t max = W64MASK;
    int st, i;

    memset(a, 0, sizeof(a));
    memset(b, 0, sizeof(b));
    a[0] = 3; b[0] = 5;
    mul256_64(a, b, p64);
    mul256_32(a, b, p32);
    if (p64[0] != 15 || p32[0] != 15) return 1;
    for (i = 1; i < 8; i++) if (p64[i] || p32[i]) return 1;

    a[3] = 1ULL << 63; a[0] = a[1] = a[2] = 0;
    b[0] = 2; b[1] = b[2] = b[3] = 0;
    mul256_64(a, b, p64);
    mul256_32(a, b, p32);
    for (i = 0; i < 8; i++) if (p64[i] != p32[i]) return 2;
    if (p64[0] != 0 || p64[4] != 1) return 2;

    zero8(n);
    n[4] = 1;
    d[0] = 3; d[1] = d[2] = d[3] = 0;
    st = div512_256_64(n, d, q, r);
    if (st != 1 || q[0] != 0x5555555555555555ULL || r[0] != 1) return 3;
    if (cmp512_64(p64, n) != 0 || cmp512_32(p64, n) != 0) return 3;

    d[0] = 1;
    st = div512_256_64(n, d, q, r);
    if (st != -2) return 4;

    d[0] = 0;
    st = div512_256_64(n, d, q, r);
    if (st != -1) return 5;

    a[0] = a[1] = a[2] = a[3] = max;
    b[0] = b[1] = b[2] = b[3] = max;
    mul256_64(a, b, p64);
    mul256_32(a, b, p32);
    for (i = 0; i < 8; i++) if (p64[i] != p32[i]) return 6;
    d[0] = d[1] = d[2] = d[3] = max;
    st = div512_256_64(p64, d, q, r);
    if (st != 1 || q[0] != max || q[1] != max || q[2] != max || q[3] != max) return 6;
    if (r[0] | r[1] | r[2] | r[3]) return 6;

    printf("PASS\n");
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: u512_coprocessor_c11 selftest\n"
            "       u512_coprocessor_c11 mul a0..a3 b0..b3\n"
            "       u512_coprocessor_c11 cmp a0..a7 b0..b7\n"
            "       u512_coprocessor_c11 div n0..n7 d0..d3\n"
            "       u512_coprocessor_c11 muldiv a0..a3 b0..b3 d0..d3\n");
}

int main(int argc, char **argv) {
    uint64_t a[4], b[4], d[4], n[8], p[8], q[4], r[4], aa[8], bb[8];
    int st;

    if (argc < 2) { usage(); return 2; }
    if (strcmp(argv[1], "selftest") == 0) return selftest();

    if (strcmp(argv[1], "mul") == 0 && argc == 10) {
        if (!loadn(argv, 2, a, 4) || !loadn(argv, 6, b, 4)) return 2;
        mul256_64(a, b, p);
        print8(p);
        return 0;
    }
    if (strcmp(argv[1], "cmp") == 0 && argc == 18) {
        if (!loadn(argv, 2, aa, 8) || !loadn(argv, 10, bb, 8)) return 2;
        printf("%d\n", cmp512_64(aa, bb));
        return 0;
    }
    if (strcmp(argv[1], "div") == 0 && argc == 14) {
        if (!loadn(argv, 2, n, 8) || !loadn(argv, 10, d, 4)) return 2;
        st = div512_256_64(n, d, q, r);
        printf("%d ", st);
        print4(q);
        putchar(' ');
        print4(r);
        putchar('\n');
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc == 14) {
        if (!loadn(argv, 2, a, 4) || !loadn(argv, 6, b, 4) || !loadn(argv, 10, d, 4))
            return 2;
        mul256_64(a, b, p);
        st = div512_256_64(p, d, q, r);
        printf("%d ", st);
        print4(q);
        putchar(' ');
        print4(r);
        putchar('\n');
        return 0;
    }
    usage();
    return 2;
}
