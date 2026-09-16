/*
 * Independent C11 oracle for the LIN u512 numeric coprocessor.
 * Not linked into the LIN compiler TCB.
 *
 * Two multiplies must agree before any LIN comparison:
 *   1. 64-bit limbs with unsigned __int128 (GCC/Clang)
 *   2. Portable 32-bit limbs, carry in uint64 only (no __int128)
 *
 * Division is restoring 512/256 on 32-bit limbs (different radix than LIN's
 * 16-bit engine). Status: 1 approved, -1 d=0, -2 quotient >= 2^256.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define U64MASK 0xffffffffffffffffULL
#define U32MASK 0xffffffffULL

static int hex_nibble(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_be(const char *s, uint8_t *out, size_t nbytes) {
    size_t n = strlen(s), i;
    if (n != nbytes * 2) return 0;
    for (i = 0; i < nbytes; i++) {
        int a = hex_nibble((unsigned char)s[2 * i]);
        int b = hex_nibble((unsigned char)s[2 * i + 1]);
        if (a < 0 || b < 0) return 0;
        out[i] = (uint8_t)((a << 4) | b);
    }
    return 1;
}

static void be_to_u64le(const uint8_t *be, size_t nbytes, uint64_t *w, size_t nw) {
    size_t i;
    memset(w, 0, nw * sizeof(uint64_t));
    (void)nw;
    for (i = 0; i < nbytes; i++) {
        size_t bit = (nbytes - 1 - i) * 8;
        w[bit / 64] |= ((uint64_t)be[i]) << (bit % 64);
    }
}

static void u64le_to_be(const uint64_t *w, size_t nw, uint8_t *be, size_t nbytes) {
    size_t i;
    for (i = 0; i < nbytes; i++) {
        size_t bit = (nbytes - 1 - i) * 8;
        be[i] = (uint8_t)((w[bit / 64] >> (bit % 64)) & 0xffu);
    }
    (void)nw;
}

static void print_be(const uint8_t *p, size_t n) {
    size_t i;
    for (i = 0; i < n; i++) printf("%02x", p[i]);
}

static void mul_i128(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    int i, j, k;
    memset(p, 0, 8 * sizeof(uint64_t));
    for (i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (j = 0; j < 4; j++) {
            unsigned __int128 t = (unsigned __int128)p[i + j]
                + (unsigned __int128)a[i] * b[j] + carry;
            p[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (carry && k < 8) {
            unsigned __int128 t = (unsigned __int128)p[k] + carry;
            p[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}

static void u64_to_u32(const uint64_t *w, size_t nw, uint32_t *l) {
    size_t i;
    for (i = 0; i < nw; i++) {
        l[2 * i] = (uint32_t)(w[i] & U32MASK);
        l[2 * i + 1] = (uint32_t)(w[i] >> 32);
    }
}

static void u32_to_u64(const uint32_t *l, size_t nl, uint64_t *w) {
    size_t i;
    for (i = 0; i < nl / 2; i++)
        w[i] = (uint64_t)l[2 * i] | ((uint64_t)l[2 * i + 1] << 32);
}

static void mul_u32(const uint32_t a[8], const uint32_t b[8], uint32_t p[16]) {
    int i, j, k;
    memset(p, 0, 16 * sizeof(uint32_t));
    for (i = 0; i < 8; i++) {
        uint64_t carry = 0;
        for (j = 0; j < 8; j++) {
            uint64_t prod = (uint64_t)a[i] * (uint64_t)b[j];
            uint64_t t = (uint64_t)p[i + j] + (prod & U32MASK) + (carry & U32MASK);
            p[i + j] = (uint32_t)(t & U32MASK);
            carry = (prod >> 32) + (t >> 32) + (carry >> 32);
        }
        k = i + 8;
        while (carry && k < 16) {
            uint64_t t = (uint64_t)p[k] + carry;
            p[k] = (uint32_t)(t & U32MASK);
            carry = t >> 32;
            k++;
        }
    }
}

static int ge_u32(const uint32_t *x, const uint32_t *y, int n) {
    int j;
    for (j = n - 1; j >= 0; j--) {
        if (x[j] > y[j]) return 1;
        if (x[j] < y[j]) return 0;
    }
    return 1;
}

static int ge_u64_8(const uint64_t x[8], const uint64_t y[8]) {
    int j;
    for (j = 7; j >= 0; j--) {
        if (x[j] > y[j]) return 1;
        if (x[j] < y[j]) return 0;
    }
    return 1;
}

/* Restoring 512/256. n[16] and d[8] are 32-bit limbs, little-endian. */
static int div_u32(const uint32_t n[16], const uint32_t d[8],
                   uint32_t q[8], uint32_t r[8]) {
    uint32_t rem[16];
    int bit, j, ge, dzero;
    uint32_t dj;
    memset(q, 0, 8 * sizeof(uint32_t));
    memset(r, 0, 8 * sizeof(uint32_t));
    memset(rem, 0, sizeof(rem));
    dzero = 1;
    for (j = 0; j < 8; j++) if (d[j]) dzero = 0;
    if (dzero) return -1;
    for (bit = 511; bit >= 0; bit--) {
        int limb = bit / 32;
        int pos = bit & 31;
        uint32_t in_bit = (n[limb] >> pos) & 1u;
        uint64_t carry = in_bit;
        for (j = 0; j < 16; j++) {
            uint64_t t = ((uint64_t)rem[j] << 1) + carry;
            rem[j] = (uint32_t)(t & U32MASK);
            carry = t >> 32;
        }
        ge = (carry != 0);
        if (!ge) {
            uint32_t dp[16];
            memset(dp, 0, sizeof(dp));
            memcpy(dp, d, 8 * sizeof(uint32_t));
            ge = ge_u32(rem, dp, 16);
        }
        if (ge) {
            uint64_t borrow = 0;
            if (bit >= 256) return -2;
            q[bit / 32] |= (1u << (bit & 31));
            for (j = 0; j < 16; j++) {
                dj = (j < 8) ? d[j] : 0;
                uint64_t sub = (uint64_t)dj + borrow;
                if ((uint64_t)rem[j] < sub) {
                    rem[j] = (uint32_t)(((uint64_t)rem[j] + (1ULL << 32)) - sub);
                    borrow = 1;
                } else {
                    rem[j] = (uint32_t)((uint64_t)rem[j] - sub);
                    borrow = 0;
                }
            }
        }
    }
    memcpy(r, rem, 8 * sizeof(uint32_t));
    return 1;
}

static int muldiv_status(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                         uint64_t q[4], uint64_t r[4], int limbs) {
    uint64_t p64[8];
    uint32_t a32[8], b32[8], d32[8], p32[16], q32[8], r32[8], p32b[16];
    int st, i;
    memset(q, 0, 4 * sizeof(uint64_t));
    memset(r, 0, 4 * sizeof(uint64_t));
    u64_to_u32(a, 4, a32);
    u64_to_u32(b, 4, b32);
    u64_to_u32(d, 4, d32);
    mul_i128(a, b, p64);
    mul_u32(a32, b32, p32);
    u64_to_u32(p64, 8, p32b);
    for (i = 0; i < 16; i++) if (p32[i] != p32b[i]) return -3;
    (void)limbs;
    st = div_u32(p32, d32, q32, r32);
    if (st < 0) return st;
    u32_to_u64(q32, 8, q);
    u32_to_u64(r32, 8, r);
    return 1;
}

static int64_t fold_limbs16(const uint64_t *w, int nwords) {
    int i, li;
    uint64_t h = 0;
    for (i = 0; i < nwords; i++) {
        for (li = 0; li < 4; li++) {
            uint64_t limb = (w[i] >> (16 * li)) & 65535ULL;
            h = h * 65537ULL + limb;
        }
    }
    return (int64_t)h;
}

static int64_t fold_qr(const uint64_t q[4], const uint64_t r[4]) {
    int i, li;
    uint64_t h = 0;
    for (i = 0; i < 4; i++)
        for (li = 0; li < 4; li++)
            h = h * 65537ULL + ((q[i] >> (16 * li)) & 65535ULL);
    for (i = 0; i < 4; i++)
        for (li = 0; li < 4; li++)
            h = h * 65537ULL + ((r[i] >> (16 * li)) & 65535ULL);
    return (int64_t)h;
}

static int load256(const char *hex, uint64_t w[4]) {
    uint8_t be[32];
    if (!parse_hex_be(hex, be, 32)) return 0;
    be_to_u64le(be, 32, w, 4);
    return 1;
}

static int load512(const char *hex, uint64_t w[8]) {
    uint8_t be[64];
    if (!parse_hex_be(hex, be, 64)) return 0;
    be_to_u64le(be, 64, w, 8);
    return 1;
}

static void emit256(const uint64_t w[4]) {
    uint8_t be[32];
    u64le_to_be(w, 4, be, 32);
    print_be(be, 32);
}

static void emit512(const uint64_t w[8]) {
    uint8_t be[64];
    u64le_to_be(w, 8, be, 64);
    print_be(be, 64);
}

static int selftest(void) {
    uint64_t a[4] = {0}, b[4] = {0}, d[4] = {0}, q[4], r[4], p[8];
    uint32_t a32[8], b32[8], p32[16], p32b[16];
    int st, fail = 0, i;
    a[0] = 6; b[0] = 7; d[0] = 4;
    st = muldiv_status(a, b, d, q, r, 1);
    if (st != 1 || q[0] != 10 || r[0] != 2) fail++;
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b)); memset(d, 0, sizeof(d));
    a[3] = 1ULL << 63; /* 2^255 */
    b[0] = 2; d[0] = 3;
    st = muldiv_status(a, b, d, q, r, 1);
    if (st != 1 || r[0] != 1 || q[0] != 0x5555555555555555ULL) fail++;
    d[0] = 1;
    st = muldiv_status(a, b, d, q, r, 1);
    if (st != -2) fail++;
    d[0] = 0;
    st = muldiv_status(a, b, d, q, r, 1);
    if (st != -1) fail++;
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b));
    a[3] = 1ULL << 63; b[0] = 2;
    mul_i128(a, b, p);
    u64_to_u32(a, 4, a32); u64_to_u32(b, 4, b32);
    mul_u32(a32, b32, p32);
    u64_to_u32(p, 8, p32b);
    for (i = 0; i < 16; i++) if (p32[i] != p32b[i]) fail++;
    if (p[4] != 1 || p[0] || p[1] || p[2] || p[3] || p[5] || p[6] || p[7]) fail++;
    {
        uint64_t x[8] = {2}, y[8] = {3};
        if (ge_u64_8(x, y) != 0) fail++;
        if (ge_u64_8(y, x) != 1) fail++;
        if (ge_u64_8(y, y) != 1) fail++;
    }
    if (fail) {
        fprintf(stderr, "u512_coprocessor_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("u512_coprocessor_c11 selftest PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t a[4], b[4], d[4], q[4], r[4], p[8], x[8], y[8];
    int st;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | mul a b | ge x y | muldiv a b d\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "mul") == 0 && argc == 4) {
        uint32_t a32[8], b32[8], p32[16], p32b[16];
        int i;
        if (!load256(argv[2], a) || !load256(argv[3], b)) return 2;
        mul_i128(a, b, p);
        u64_to_u32(a, 4, a32); u64_to_u32(b, 4, b32);
        mul_u32(a32, b32, p32);
        u64_to_u32(p, 8, p32b);
        for (i = 0; i < 16; i++) if (p32[i] != p32b[i]) return 1;
        printf("prod="); emit512(p); printf("\n");
        printf("fold=%" PRId64 "\n", fold_limbs16(p, 8));
        return 0;
    }
    if (strcmp(argv[1], "ge") == 0 && argc == 4) {
        if (!load512(argv[2], x) || !load512(argv[3], y)) return 2;
        printf("%d\n", ge_u64_8(x, y));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc == 5) {
        if (!load256(argv[2], a) || !load256(argv[3], b) || !load256(argv[4], d)) return 2;
        st = muldiv_status(a, b, d, q, r, 1);
        printf("status=%d\n", st);
        if (st == 1) {
            printf("q="); emit256(q); printf("\n");
            printf("r="); emit256(r); printf("\n");
            printf("fold=%" PRId64 "\n", fold_qr(q, r));
        }
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
