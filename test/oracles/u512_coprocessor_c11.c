/* Independent C11 oracle: 16-bit LIN-mirror limbs vs 64-bit __int128. Not TCB. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define U16MASK 65535u

static int ge16(const uint16_t a[32], const uint16_t b[32]) {
    int j;
    for (j = 31; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static int ge64(const uint64_t a[8], const uint64_t b[8]) {
    int j;
    for (j = 7; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static void u256_to16(const uint64_t w[4], uint16_t L[16]) {
    int i, k;
    for (k = 0; k < 4; k++) {
        for (i = 0; i < 4; i++) L[k * 4 + i] = (uint16_t)((w[k] >> (16 * i)) & 0xffffu);
    }
}

static void u512_to16(const uint64_t w[8], uint16_t L[32]) {
    int i, k;
    for (k = 0; k < 8; k++) {
        for (i = 0; i < 4; i++) L[k * 4 + i] = (uint16_t)((w[k] >> (16 * i)) & 0xffffu);
    }
}

static void from16_u256(const uint16_t L[16], uint64_t w[4]) {
    int k;
    for (k = 0; k < 4; k++) {
        w[k] = (uint64_t)L[k * 4] |
               ((uint64_t)L[k * 4 + 1] << 16) |
               ((uint64_t)L[k * 4 + 2] << 32) |
               ((uint64_t)L[k * 4 + 3] << 48);
    }
}

static void from16_u512(const uint16_t L[32], uint64_t w[8]) {
    int k;
    for (k = 0; k < 8; k++) {
        w[k] = (uint64_t)L[k * 4] |
               ((uint64_t)L[k * 4 + 1] << 16) |
               ((uint64_t)L[k * 4 + 2] << 32) |
               ((uint64_t)L[k * 4 + 3] << 48);
    }
}

static void mul16(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    uint16_t al[16], bl[16], pr[32];
    int i, j, k;
    uint32_t carry, t;
    u256_to16(a, al);
    u256_to16(b, bl);
    memset(pr, 0, sizeof(pr));
    for (i = 0; i < 16; i++) {
        carry = 0;
        for (j = 0; j < 16; j++) {
            k = i + j;
            t = (uint32_t)pr[k] + (uint32_t)al[i] * bl[j] + carry;
            pr[k] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
        }
        k = i + 16;
        while (k < 32 && carry) {
            t = (uint32_t)pr[k] + carry;
            pr[k] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
            k++;
        }
    }
    from16_u512(pr, p);
}

static int div16(const uint64_t n[8], const uint64_t d[4], uint64_t q[4], uint64_t r[4]) {
    uint16_t num[32], den[16], rem[32], quot[16], denp[32];
    int bit, limb, pos, j, take, cmp;
    uint32_t carry, t, hi, borrow, in_bit, dj;
    if ((d[0] | d[1] | d[2] | d[3]) == 0) return -1;
    u512_to16(n, num);
    u256_to16(d, den);
    memset(rem, 0, sizeof(rem));
    memset(quot, 0, sizeof(quot));
    memset(denp, 0, sizeof(denp));
    memcpy(denp, den, sizeof(den));
    hi = 0;
    for (bit = 511; bit >= 0; bit--) {
        limb = bit >> 4;
        pos = bit & 15;
        in_bit = (uint32_t)((num[limb] >> pos) & 1);
        carry = in_bit;
        for (j = 0; j < 32; j++) {
            t = (uint32_t)rem[j] * 2u + carry;
            rem[j] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
        }
        hi = hi * 2u + carry;
        cmp = 0;
        if (hi != 0) cmp = 1;
        if (cmp == 0) {
            for (j = 31; j >= 0; j--) {
                if (rem[j] > denp[j]) { cmp = 1; break; }
                if (rem[j] < denp[j]) { cmp = -1; break; }
            }
        }
        take = cmp >= 0;
        if (take) {
            if (bit >= 256) return -2;
            quot[limb] = (uint16_t)(quot[limb] | (uint16_t)(1u << pos));
            borrow = 0;
            for (j = 0; j < 32; j++) {
                dj = denp[j];
                t = (uint32_t)rem[j] - dj - borrow;
                if ((int32_t)t < 0) {
                    rem[j] = (uint16_t)(t + 65536u);
                    borrow = 1;
                } else {
                    rem[j] = (uint16_t)t;
                    borrow = 0;
                }
            }
            hi -= borrow;
        }
    }
    from16_u256(quot, q);
    from16_u256(rem, r);
    return 1;
}

static void mul64(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    int i, j, k;
    memset(p, 0, 8 * sizeof(uint64_t));
    for (i = 0; i < 4; i++) {
        __uint128_t carry = 0;
        for (j = 0; j < 4; j++) {
            __uint128_t t = (__uint128_t)p[i + j] + (__uint128_t)a[i] * b[j] + carry;
            p[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (k < 8 && carry) {
            __uint128_t t = (__uint128_t)p[k] + carry;
            p[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}

static int div64(const uint64_t n[8], const uint64_t d[4], uint64_t q[4], uint64_t r[4]) {
    uint64_t rem[8], denp[8];
    uint64_t hi = 0;
    int bit, w, pos, j, take;
    if ((d[0] | d[1] | d[2] | d[3]) == 0) return -1;
    memset(rem, 0, sizeof(rem));
    memset(q, 0, 4 * sizeof(uint64_t));
    memset(denp, 0, sizeof(denp));
    memcpy(denp, d, 4 * sizeof(uint64_t));
    for (bit = 511; bit >= 0; bit--) {
        w = bit >> 6;
        pos = bit & 63;
        uint64_t in_bit = (n[w] >> pos) & 1ull;
        uint64_t carry = in_bit;
        for (j = 0; j < 8; j++) {
            uint64_t newv = (rem[j] << 1) | carry;
            carry = rem[j] >> 63;
            rem[j] = newv;
        }
        hi = (hi << 1) | carry;
        take = (hi != 0) || ge64(rem, denp);
        if (take) {
            if (bit >= 256) return -2;
            q[w] |= (1ull << pos);
            uint64_t borrow = 0;
            for (j = 0; j < 8; j++) {
                __uint128_t acc = (__uint128_t)rem[j] - denp[j] - borrow;
                rem[j] = (uint64_t)acc;
                borrow = (acc >> 64) ? 1 : 0;
            }
            hi -= borrow;
        }
    }
    memcpy(r, rem, 4 * sizeof(uint64_t));
    return 1;
}

static int same256(const uint64_t a[4], const uint64_t b[4]) {
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3];
}

static int same512(const uint64_t a[8], const uint64_t b[8]) {
    int i;
    for (i = 0; i < 8; i++) if (a[i] != b[i]) return 0;
    return 1;
}

static int muldiv16(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                    uint64_t q[4], uint64_t r[4]) {
    uint64_t p[8];
    mul16(a, b, p);
    return div16(p, d, q, r);
}

static int muldiv64(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                    uint64_t q[4], uint64_t r[4]) {
    uint64_t p[8];
    mul64(a, b, p);
    return div64(p, d, q, r);
}

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_words(const char *s, uint64_t *w, int nwords) {
    size_t need = (size_t)nwords * 16;
    size_t len = strlen(s);
    char buf[257];
    size_t i;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) { s += 2; len -= 2; }
    if (len > need || need > 256) return -1;
    memset(buf, '0', need);
    memcpy(buf + (need - len), s, len);
    buf[need] = 0;
    for (i = 0; i < (size_t)nwords; i++) {
        uint64_t v = 0;
        size_t off = (size_t)(nwords - 1 - (int)i) * 16;
        int k;
        for (k = 0; k < 16; k++) {
            int h = hexval((unsigned char)buf[off + (size_t)k]);
            if (h < 0) return -1;
            v = (v << 4) | (uint64_t)h;
        }
        w[i] = v;
    }
    return 0;
}

static void print_hex_words(const uint64_t *w, int nwords) {
    int i, k;
    for (i = nwords - 1; i >= 0; i--) {
        for (k = 15; k >= 0; k--) putchar("0123456789abcdef"[(w[i] >> (k * 4)) & 0xf]);
    }
}

static uint64_t rng_state = 0x9e3779b97f4a7c15ull;
static uint64_t rng_u64(void) {
    uint64_t x = rng_state;
    x ^= x << 7;
    x ^= x >> 9;
    x ^= x << 8;
    rng_state = x;
    return x;
}

static void rand256(uint64_t w[4]) {
    w[0] = rng_u64(); w[1] = rng_u64(); w[2] = rng_u64(); w[3] = rng_u64();
}

static int selftest(void) {
    uint64_t a[4], b[4], d[4], q16[4], r16[4], q64[4], r64[4], p16[8], p64[8];
    int st16, st64, fail = 0, i;
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b)); memset(d, 0, sizeof(d));
    a[0] = 7; b[0] = 9; d[0] = 2;
    st16 = muldiv16(a, b, d, q16, r16);
    st64 = muldiv64(a, b, d, q64, r64);
    if (st16 != 1 || st64 != 1 || q16[0] != 31 || r16[0] != 1 || !same256(q16, q64) || !same256(r16, r64)) {
        fprintf(stderr, "selftest 7*9/2 failed\n");
        return 1;
    }
    d[0] = 0;
    if (muldiv16(a, b, d, q16, r16) != -1 || muldiv64(a, b, d, q64, r64) != -1) {
        fprintf(stderr, "selftest d=0 failed\n");
        return 1;
    }
    memset(a, 0xff, sizeof(a)); memset(b, 0xff, sizeof(b)); memset(d, 0, sizeof(d)); d[0] = 1;
    if (muldiv16(a, b, d, q16, r16) != -2 || muldiv64(a, b, d, q64, r64) != -2) {
        fprintf(stderr, "selftest overflow failed\n");
        return 1;
    }
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b));
    a[2] = 1; b[2] = 1;
    mul16(a, b, p16); mul64(a, b, p64);
    if (!same512(p16, p64) || p16[4] != 1 || p16[0] || p16[1] || p16[2] || p16[3]) {
        fprintf(stderr, "selftest 2^128 mul failed\n");
        return 1;
    }
    rng_state = 1;
    for (i = 0; i < 4000; i++) {
        rand256(a); rand256(b); rand256(d);
        mul16(a, b, p16); mul64(a, b, p64);
        if (!same512(p16, p64)) { fprintf(stderr, "mul diverge i=%d\n", i); fail++; break; }
        st16 = div16(p16, d, q16, r16);
        st64 = div64(p64, d, q64, r64);
        if (st16 != st64 || (st16 == 1 && (!same256(q16, q64) || !same256(r16, r64)))) {
            fprintf(stderr, "div diverge i=%d st=%d/%d\n", i, st16, st64);
            fail++;
            break;
        }
    }
    if (fail) return 1;
    printf("PASS selftest vectors=4000+edges 16bit==64bit\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t a[4], b[4], d[4], n[8], q[4], r[4], p[8];
    int st, i, nvec;
    const char *cmd;
    if (argc < 2) {
        fprintf(stderr, "usage: u512_coprocessor_c11 selftest|mul|ge|div|muldiv|random ...\n");
        return 2;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "random") == 0) {
        nvec = argc > 2 ? atoi(argv[2]) : 10000;
        rng_state = argc > 3 ? strtoull(argv[3], NULL, 0) : 0xc0ffeeull;
        for (i = 0; i < nvec; i++) {
            uint64_t q16[4], r16[4], q64[4], r64[4], p16[8], p64[8];
            int s16, s64;
            rand256(a); rand256(b); rand256(d);
            mul16(a, b, p16); mul64(a, b, p64);
            if (!same512(p16, p64)) { printf("FAIL mul i=%d\n", i); return 1; }
            s16 = div16(p16, d, q16, r16);
            s64 = div64(p64, d, q64, r64);
            if (s16 != s64 || (s16 == 1 && (!same256(q16, q64) || !same256(r16, r64)))) {
                printf("FAIL div i=%d\n", i);
                return 1;
            }
        }
        printf("PASS random n=%d seed=%" PRIu64 " 16bit==64bit\n", nvec, rng_state);
        return 0;
    }
    if (strcmp(cmd, "mul") == 0 && argc == 4) {
        if (parse_hex_words(argv[2], a, 4) || parse_hex_words(argv[3], b, 4)) return 2;
        mul16(a, b, p);
        printf("p="); print_hex_words(p, 8); printf("\n");
        return 0;
    }
    if (strcmp(cmd, "ge") == 0 && argc == 4) {
        uint64_t A[8], B[8];
        uint16_t Al[32], Bl[32];
        if (parse_hex_words(argv[2], A, 8) || parse_hex_words(argv[3], B, 8)) return 2;
        u512_to16(A, Al); u512_to16(B, Bl);
        printf("ge16=%d ge64=%d\n", ge16(Al, Bl), ge64(A, B));
        return ge16(Al, Bl) == ge64(A, B) ? 0 : 1;
    }
    if (strcmp(cmd, "div") == 0 && argc == 4) {
        if (parse_hex_words(argv[2], n, 8) || parse_hex_words(argv[3], d, 4)) return 2;
        st = div16(n, d, q, r);
        printf("status=%d q=", st); print_hex_words(q, 4);
        printf(" r="); print_hex_words(r, 4); printf("\n");
        return 0;
    }
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        if (parse_hex_words(argv[2], a, 4) || parse_hex_words(argv[3], b, 4) ||
            parse_hex_words(argv[4], d, 4)) return 2;
        st = muldiv16(a, b, d, q, r);
        printf("status=%d q=", st); print_hex_words(q, 4);
        printf(" r="); print_hex_words(r, 4); printf("\n");
        return 0;
    }
    if (strcmp(cmd, "batch") == 0) {
        char as[130], bs[130], ds[130];
        int n = 0;
        while (scanf("%129s %129s %129s", as, bs, ds) == 3) {
            if (parse_hex_words(as, a, 4) || parse_hex_words(bs, b, 4) ||
                parse_hex_words(ds, d, 4)) {
                printf("FAIL parse n=%d\n", n);
                return 1;
            }
            st = muldiv16(a, b, d, q, r);
            printf("%d ", st);
            print_hex_words(q, 4);
            printf(" ");
            print_hex_words(r, 4);
            printf("\n");
            n++;
        }
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
