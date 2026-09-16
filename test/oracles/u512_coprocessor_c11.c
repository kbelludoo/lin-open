/*
 * Independent C11 oracle for the LIN u512 numeric coprocessor.
 *
 * Two implementations that must agree before any LIN comparison:
 *   1. 16-bit schoolbook (same limb width as src/lin_u512_coprocessor.lin)
 *   2. 64-bit schoolbook with unsigned __int128 partial products
 *
 * Not linked into the LIN compiler TCB. Algorithm class: EXPERIMENTAL
 * FullMath *width* (256x256->512 then 512/256 restoring div). Not CRT/mulmod.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NL16 16
#define NL32 32

static int dec_to_u16(const char *s, uint16_t *L, int n) {
    memset(L, 0, (size_t)n * sizeof(uint16_t));
    if (s == NULL || s[0] == '\0' || s[0] == '-') return -1;
    for (; *s; s++) {
        unsigned carry;
        int i;
        if (*s < '0' || *s > '9') return -1;
        carry = (unsigned)(*s - '0');
        for (i = 0; i < n; i++) {
            unsigned t = (unsigned)L[i] * 10u + carry;
            L[i] = (uint16_t)(t & 0xffffu);
            carry = t >> 16;
        }
        if (carry) return -2;
    }
    return 0;
}

static void u16_to_dec(const uint16_t *L, int n, char *out, size_t cap) {
    uint16_t tmp[32];
    char buf[160];
    int bl = 0, allz, i;
    unsigned rem;
    if (n > 32 || cap < 2) { out[0] = '0'; out[1] = 0; return; }
    memcpy(tmp, L, (size_t)n * sizeof(uint16_t));
    do {
        rem = 0;
        allz = 1;
        for (i = n - 1; i >= 0; i--) {
            unsigned cur = (rem << 16) | tmp[i];
            tmp[i] = (uint16_t)(cur / 10u);
            rem = cur % 10u;
            if (tmp[i]) allz = 0;
        }
        if (bl < 159) buf[bl++] = (char)('0' + rem);
    } while (!allz && bl < 159);
    if ((size_t)bl + 1 > cap) bl = (int)cap - 1;
    for (i = 0; i < bl; i++) out[i] = buf[bl - 1 - i];
    out[bl] = 0;
}

static void mul16(const uint16_t a[NL16], const uint16_t b[NL16], uint16_t p[NL32]) {
    int i, j, k;
    memset(p, 0, NL32 * sizeof(uint16_t));
    for (i = 0; i < NL16; i++) {
        uint32_t carry = 0;
        for (j = 0; j < NL16; j++) {
            uint32_t t = (uint32_t)p[i + j] + (uint32_t)a[i] * (uint32_t)b[j] + carry;
            p[i + j] = (uint16_t)(t & 0xffffu);
            carry = t >> 16;
        }
        k = i + NL16;
        while (k < NL32 && carry) {
            uint32_t t = (uint32_t)p[k] + carry;
            p[k] = (uint16_t)(t & 0xffffu);
            carry = t >> 16;
            k++;
        }
    }
}

static int ge32(const uint16_t a[NL32], const uint16_t b[NL32]) {
    int j;
    for (j = 31; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static int u16_is_zero(const uint16_t *L, int n) {
    int i;
    for (i = 0; i < n; i++) if (L[i]) return 0;
    return 1;
}

/* status: 1 ok, -1 d=0, -2 q overflow. */
static int div512_16(const uint16_t n[NL32], const uint16_t d[NL16],
                     uint16_t q[NL16], uint16_t r[NL32]) {
    int bit, j;
    memset(q, 0, NL16 * sizeof(uint16_t));
    memset(r, 0, NL32 * sizeof(uint16_t));
    if (u16_is_zero(d, NL16)) return -1;
    for (bit = 511; bit >= 0; bit--) {
        int limb = bit >> 4;
        int pos = bit & 15;
        uint32_t carry = (uint32_t)((n[limb] >> pos) & 1u);
        uint16_t dpad[NL32];
        for (j = 0; j < NL32; j++) {
            uint32_t t = (uint32_t)r[j] * 2u + carry;
            r[j] = (uint16_t)(t & 0xffffu);
            carry = t >> 16;
        }
        memset(dpad, 0, sizeof(dpad));
        memcpy(dpad, d, NL16 * sizeof(uint16_t));
        /* carry==1 means shifted remainder >= 2^512 > any 256-bit d. */
        if (carry == 1 || ge32(r, dpad)) {
            uint32_t borrow = 0;
            if (bit >= 256) return -2;
            q[limb] = (uint16_t)(q[limb] | (uint16_t)(1u << pos));
            for (j = 0; j < NL32; j++) {
                uint32_t dj = (j < NL16) ? d[j] : 0;
                int32_t t = (int32_t)r[j] - (int32_t)dj - (int32_t)borrow;
                if (t < 0) {
                    r[j] = (uint16_t)(t + 65536);
                    borrow = 1;
                } else {
                    r[j] = (uint16_t)t;
                    borrow = 0;
                }
            }
        }
    }
    return 1;
}

static void u16_to_u64_4(const uint16_t s[NL16], uint64_t d[4]) {
    int i;
    for (i = 0; i < 4; i++) {
        d[i] = (uint64_t)s[i * 4]
            | ((uint64_t)s[i * 4 + 1] << 16)
            | ((uint64_t)s[i * 4 + 2] << 32)
            | ((uint64_t)s[i * 4 + 3] << 48);
    }
}

static void u16_to_u64_8(const uint16_t s[NL32], uint64_t d[8]) {
    int i;
    for (i = 0; i < 8; i++) {
        d[i] = (uint64_t)s[i * 4]
            | ((uint64_t)s[i * 4 + 1] << 16)
            | ((uint64_t)s[i * 4 + 2] << 32)
            | ((uint64_t)s[i * 4 + 3] << 48);
    }
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

static int ge64_8(const uint64_t a[8], const uint64_t b[8]) {
    int j;
    for (j = 7; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static int div512_64(const uint64_t n[8], const uint64_t d[4],
                     uint64_t q[4], uint64_t r[8]) {
    int bit, j;
    memset(q, 0, 4 * sizeof(uint64_t));
    memset(r, 0, 8 * sizeof(uint64_t));
    if (d[0] == 0 && d[1] == 0 && d[2] == 0 && d[3] == 0) return -1;
    for (bit = 511; bit >= 0; bit--) {
        int limb = bit >> 6;
        int pos = bit & 63;
        uint64_t inbit = (n[limb] >> pos) & 1ull;
        uint64_t carry = inbit;
        uint64_t dpad[8];
        for (j = 0; j < 8; j++) {
            uint64_t next = r[j] >> 63;
            r[j] = (r[j] << 1) | carry;
            carry = next;
        }
        memset(dpad, 0, sizeof(dpad));
        memcpy(dpad, d, 4 * sizeof(uint64_t));
        if (carry == 1 || ge64_8(r, dpad)) {
            uint64_t borrow = 0;
            if (bit >= 256) return -2;
            q[limb] |= (1ull << pos);
            for (j = 0; j < 8; j++) {
                uint64_t dj = (j < 4) ? d[j] : 0;
                uint64_t t = r[j];
                uint64_t b1 = t < dj;
                t -= dj;
                uint64_t b2 = t < borrow;
                t -= borrow;
                r[j] = t;
                borrow = (b1 || b2) ? 1ull : 0;
            }
        }
    }
    return 1;
}

static int limbs_eq16(const uint16_t *a, const uint16_t *b, int n) {
    return memcmp(a, b, (size_t)n * sizeof(uint16_t)) == 0;
}

static void u64_4_to_u16(const uint64_t s[4], uint16_t d[NL16]) {
    int i;
    for (i = 0; i < 4; i++) {
        d[i * 4] = (uint16_t)(s[i] & 0xffffu);
        d[i * 4 + 1] = (uint16_t)((s[i] >> 16) & 0xffffu);
        d[i * 4 + 2] = (uint16_t)((s[i] >> 32) & 0xffffu);
        d[i * 4 + 3] = (uint16_t)((s[i] >> 48) & 0xffffu);
    }
}

static void u64_8_to_u16(const uint64_t s[8], uint16_t d[NL32]) {
    int i;
    for (i = 0; i < 8; i++) {
        d[i * 4] = (uint16_t)(s[i] & 0xffffu);
        d[i * 4 + 1] = (uint16_t)((s[i] >> 16) & 0xffffu);
        d[i * 4 + 2] = (uint16_t)((s[i] >> 32) & 0xffffu);
        d[i * 4 + 3] = (uint16_t)((s[i] >> 48) & 0xffffu);
    }
}

static int do_muldiv(const char *as, const char *bs, const char *ds) {
    uint16_t a[NL16], b[NL16], d[NL16], p16[NL32], q16[NL16], r16[NL32];
    uint16_t q64l[NL16], r64l[NL32], p64l[NL32];
    uint64_t a64[4], b64[4], d64[4], p64[8], q64[4], r64[8];
    int st16, st64;
    char qdec[160], rdec[160], pdec[160];
    if (dec_to_u16(as, a, NL16) || dec_to_u16(bs, b, NL16) || dec_to_u16(ds, d, NL16)) {
        fprintf(stderr, "parse error\n");
        return 2;
    }
    mul16(a, b, p16);
    st16 = div512_16(p16, d, q16, r16);
    u16_to_u64_4(a, a64);
    u16_to_u64_4(b, b64);
    u16_to_u64_4(d, d64);
    mul64(a64, b64, p64);
    st64 = div512_64(p64, d64, q64, r64);
    u64_8_to_u16(p64, p64l);
    u64_4_to_u16(q64, q64l);
    u64_8_to_u16(r64, r64l);
    if (st16 != st64 || !limbs_eq16(p16, p64l, NL32) ||
        (st16 == 1 && (!limbs_eq16(q16, q64l, NL16) || !limbs_eq16(r16, r64l, NL32)))) {
        fprintf(stderr, "C11 16-bit vs 64-bit DIVERGENCE status %d/%d\n", st16, st64);
        return 3;
    }
    u16_to_dec(q16, NL16, qdec, sizeof(qdec));
    u16_to_dec(r16, NL32, rdec, sizeof(rdec));
    u16_to_dec(p16, NL32, pdec, sizeof(pdec));
    printf("status=%d q=%s r=%s prod=%s\n", st16, qdec, rdec, pdec);
    return 0;
}

static int do_mul(const char *as, const char *bs) {
    uint16_t a[NL16], b[NL16], p16[NL32], p64l[NL32];
    uint64_t a64[4], b64[4], p64[8];
    char pdec[160];
    if (dec_to_u16(as, a, NL16) || dec_to_u16(bs, b, NL16)) return 2;
    mul16(a, b, p16);
    u16_to_u64_4(a, a64);
    u16_to_u64_4(b, b64);
    mul64(a64, b64, p64);
    u64_8_to_u16(p64, p64l);
    if (!limbs_eq16(p16, p64l, NL32)) {
        fprintf(stderr, "C11 mul 16 vs 64 DIVERGENCE\n");
        return 3;
    }
    u16_to_dec(p16, NL32, pdec, sizeof(pdec));
    printf("status=1 prod=%s\n", pdec);
    return 0;
}

static int do_ge(const char *as, const char *bs) {
    uint16_t a[NL32], b[NL32];
    uint64_t a64[8], b64[8];
    int g16, g64;
    if (dec_to_u16(as, a, NL32) || dec_to_u16(bs, b, NL32)) return 2;
    g16 = ge32(a, b);
    u16_to_u64_8(a, a64);
    u16_to_u64_8(b, b64);
    g64 = ge64_8(a64, b64);
    if (g16 != g64) {
        fprintf(stderr, "C11 ge 16 vs 64 DIVERGENCE\n");
        return 3;
    }
    printf("status=1 ge=%d\n", g16);
    return 0;
}

static int do_div(const char *ns, const char *ds) {
    uint16_t n[NL32], d[NL16], q16[NL16], r16[NL32], q64l[NL16], r64l[NL32];
    uint64_t n64[8], d64[4], q64[4], r64[8];
    int st16, st64;
    char qdec[160], rdec[160];
    if (dec_to_u16(ns, n, NL32) || dec_to_u16(ds, d, NL16)) return 2;
    st16 = div512_16(n, d, q16, r16);
    u16_to_u64_8(n, n64);
    u16_to_u64_4(d, d64);
    st64 = div512_64(n64, d64, q64, r64);
    u64_4_to_u16(q64, q64l);
    u64_8_to_u16(r64, r64l);
    if (st16 != st64 || (st16 == 1 && (!limbs_eq16(q16, q64l, NL16) || !limbs_eq16(r16, r64l, NL32)))) {
        fprintf(stderr, "C11 div 16 vs 64 DIVERGENCE %d/%d\n", st16, st64);
        return 3;
    }
    u16_to_dec(q16, NL16, qdec, sizeof(qdec));
    u16_to_dec(r16, NL32, rdec, sizeof(rdec));
    printf("status=%d q=%s r=%s\n", st16, qdec, rdec);
    return 0;
}

static int do_selftest(void) {
    /* 2^255 * 2 / 3: product is 2^256 (bit 256 set). q = repeating 0x55, r=1. */
    uint16_t a[NL16], b[NL16], d[NL16], p[NL32], q[NL16], r[NL32];
    uint16_t expect_q[NL16];
    int i, st;
    memset(a, 0, sizeof(a));
    memset(b, 0, sizeof(b));
    memset(d, 0, sizeof(d));
    a[15] = 0x8000; /* bit 255 */
    b[0] = 2;
    d[0] = 3;
    mul16(a, b, p);
    if (p[16] != 1) {
        fprintf(stderr, "selftest: product is not 2^256\n");
        return 1;
    }
    for (i = 0; i < NL32; i++) {
        if (i != 16 && p[i] != 0) {
            fprintf(stderr, "selftest: product extra limb\n");
            return 1;
        }
    }
    st = div512_16(p, d, q, r);
    if (st != 1 || r[0] != 1) {
        fprintf(stderr, "selftest: status/r\n");
        return 1;
    }
    for (i = 1; i < NL32; i++) {
        if (r[i] != 0) {
            fprintf(stderr, "selftest: remainder high\n");
            return 1;
        }
    }
    for (i = 0; i < NL16; i++) expect_q[i] = 0x5555;
    if (!limbs_eq16(q, expect_q, NL16)) {
        fprintf(stderr, "selftest: q is not repeating 0x5555\n");
        return 1;
    }
    printf("status=1 selftest=PASS q_limb0=%u r=%u\n", (unsigned)q[0], (unsigned)r[0]);
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "selftest") == 0) return do_selftest();
    if (argc == 5 && strcmp(argv[1], "muldiv") == 0) return do_muldiv(argv[2], argv[3], argv[4]);
    if (argc == 4 && strcmp(argv[1], "mul") == 0) return do_mul(argv[2], argv[3]);
    if (argc == 4 && strcmp(argv[1], "ge") == 0) return do_ge(argv[2], argv[3]);
    if (argc == 4 && strcmp(argv[1], "div") == 0) return do_div(argv[2], argv[3]);
    fprintf(stderr, "usage: %s selftest | muldiv a b d | mul a b | ge a512 b512 | div n512 d256\n", argv[0]);
    return 2;
}
