/* Independent C11 oracle (not TCB): 16-bit schoolbook == 64-bit __int128.
 * EXPERIMENTAL: FullMath width, not CRT/mulmod. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static void be32_to_l16(const uint8_t be[32], uint16_t l[16]) {
    for (int i = 0; i < 16; i++) l[i] = (uint16_t)((be[30 - 2 * i] << 8) | be[31 - 2 * i]);
}
static void l16_to_be32(const uint16_t l[16], uint8_t be[32]) {
    memset(be, 0, 32);
    for (int i = 0; i < 16; i++) {
        be[30 - 2 * i] = (uint8_t)(l[i] >> 8);
        be[31 - 2 * i] = (uint8_t)l[i];
    }
}
static void hex_of(const uint8_t *p, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) { out[2 * i] = H[p[i] >> 4]; out[2 * i + 1] = H[p[i] & 15]; }
    out[2 * n] = 0;
}
static void l16_to_w64(const uint16_t l[16], uint64_t w[4]) {
    for (int i = 0; i < 4; i++)
        w[i] = (uint64_t)l[4 * i] | ((uint64_t)l[4 * i + 1] << 16) |
               ((uint64_t)l[4 * i + 2] << 32) | ((uint64_t)l[4 * i + 3] << 48);
}
static void w64_to_l16(const uint64_t w[4], uint16_t l[16]) {
    for (int i = 0; i < 4; i++) {
        l[4 * i] = (uint16_t)(w[i] & 0xffff);
        l[4 * i + 1] = (uint16_t)((w[i] >> 16) & 0xffff);
        l[4 * i + 2] = (uint16_t)((w[i] >> 32) & 0xffff);
        l[4 * i + 3] = (uint16_t)((w[i] >> 48) & 0xffff);
    }
}

static int l16_zero(const uint16_t *l, int n) {
    for (int i = 0; i < n; i++) if (l[i]) return 0;
    return 1;
}
static int ge16(const uint16_t *a, const uint16_t *b, int n) {
    for (int j = n - 1; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static int mul16(const uint16_t a[16], const uint16_t b[16], uint16_t n[32]) {
    memset(n, 0, 32 * sizeof(uint16_t));
    for (int i = 0; i < 16; i++) {
        uint32_t carry = 0;
        for (int j = 0; j < 16; j++) {
            int k = i + j;
            uint32_t t = (uint32_t)n[k] + (uint32_t)a[i] * (uint32_t)b[j] + carry;
            n[k] = (uint16_t)(t & 0xffff);
            carry = t >> 16;
        }
        int k = i + 16;
        while (k < 32 && carry) {
            uint32_t t = (uint32_t)n[k] + carry;
            n[k] = (uint16_t)(t & 0xffff);
            carry = t >> 16;
            k++;
        }
        if (carry) return -2;
    }
    return 1;
}

static int div16(const uint16_t n[32], const uint16_t d[16],
                 uint16_t q[16], uint16_t rem[32]) {
    memset(q, 0, 16 * sizeof(uint16_t));
    memset(rem, 0, 32 * sizeof(uint16_t));
    if (l16_zero(d, 16)) return -1;
    for (int bit = 511; bit >= 0; bit--) {
        int limb = bit >> 4, pos = bit & 15;
        uint32_t carry = (uint32_t)((n[limb] >> pos) & 1);
        for (int j = 0; j < 32; j++) {
            uint32_t t = (uint32_t)rem[j] * 2u + carry;
            rem[j] = (uint16_t)(t & 0xffff);
            carry = t >> 16;
        }
        if (carry) return -2;
        int ge = 0;
        for (int j = 31; j >= 0; j--) {
            uint16_t dj = (j < 16) ? d[j] : 0;
            if (rem[j] > dj) { ge = 1; break; }
            if (rem[j] < dj) { ge = -1; break; }
        }
        if (ge >= 0) {
            if (bit >= 256) return -2;
            q[limb] |= (uint16_t)(1u << pos);
            uint32_t borrow = 0;
            for (int j = 0; j < 32; j++) {
                uint32_t dj = (j < 16) ? d[j] : 0;
                int32_t t = (int32_t)rem[j] - (int32_t)dj - (int32_t)borrow;
                if (t < 0) { rem[j] = (uint16_t)(t + 65536); borrow = 1; }
                else { rem[j] = (uint16_t)t; borrow = 0; }
            }
        }
    }
    return 1;
}

static int identity16(const uint16_t n[32], const uint16_t q[16],
                      const uint16_t d[16], const uint16_t rem[32]) {
    uint16_t qd[32];
    if (mul16(q, d, qd) != 1) return 0;
    uint32_t carry = 0;
    for (int i = 0; i < 32; i++) {
        uint32_t t = (uint32_t)qd[i] + (uint32_t)rem[i] + carry;
        qd[i] = (uint16_t)(t & 0xffff);
        carry = t >> 16;
    }
    if (carry) return 0;
    for (int i = 0; i < 32; i++) if (qd[i] != n[i]) return 0;
    uint16_t dext[32];
    memset(dext, 0, sizeof dext);
    memcpy(dext, d, 16 * sizeof(uint16_t));
    return !ge16(rem, dext, 32);
}

static int muldiv16(const uint16_t a[16], const uint16_t b[16], const uint16_t d[16],
                    uint16_t q[16], uint16_t rem[32], uint16_t n[32]) {
    int st = mul16(a, b, n);
    if (st != 1) return st;
    st = div16(n, d, q, rem);
    if (st != 1) return st;
    if (!identity16(n, q, d, rem)) return -2;
    return 1;
}

static int mul64(const uint64_t a[4], const uint64_t b[4], uint64_t p[8]) {
    memset(p, 0, 8 * sizeof(uint64_t));
    for (int i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (int j = 0; j < 4; j++) {
            unsigned __int128 t = (unsigned __int128)p[i + j] +
                                  (unsigned __int128)a[i] * b[j] + carry;
            p[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        int k = i + 4;
        while (k < 8 && carry) {
            unsigned __int128 t = (unsigned __int128)p[k] + carry;
            p[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
        if (carry) return -2;
    }
    return 1;
}

static int div64(const uint64_t n[8], const uint64_t d[4], uint64_t q[4], uint64_t rem[8]) {
    memset(q, 0, 4 * sizeof(uint64_t));
    memset(rem, 0, 8 * sizeof(uint64_t));
    if ((d[0] | d[1] | d[2] | d[3]) == 0) return -1;
    for (int bit = 511; bit >= 0; bit--) {
        int limb = bit >> 6, pos = bit & 63;
        unsigned __int128 carry = (n[limb] >> pos) & 1u;
        for (int j = 0; j < 8; j++) {
            unsigned __int128 t = ((unsigned __int128)rem[j] << 1) + carry;
            rem[j] = (uint64_t)t;
            carry = t >> 64;
        }
        if (carry) return -2;
        int ge = 0;
        for (int j = 7; j >= 0; j--) {
            uint64_t dj = (j < 4) ? d[j] : 0;
            if (rem[j] > dj) { ge = 1; break; }
            if (rem[j] < dj) { ge = -1; break; }
        }
        if (ge >= 0) {
            if (bit >= 256) return -2;
            q[limb] |= (1ULL << pos);
            unsigned borrow = 0;
            for (int j = 0; j < 8; j++) {
                unsigned __int128 sub = (unsigned __int128)((j < 4) ? d[j] : 0) + borrow;
                if (rem[j] < sub) {
                    rem[j] = (uint64_t)(((unsigned __int128)1 << 64) + rem[j] - sub);
                    borrow = 1;
                } else {
                    rem[j] = (uint64_t)(rem[j] - sub);
                    borrow = 0;
                }
            }
        }
    }
    return 1;
}

static int identity64(const uint64_t n[8], const uint64_t q[4],
                      const uint64_t d[4], const uint64_t rem[8]) {
    uint64_t qd[8];
    unsigned __int128 carry = 0;
    if (mul64(q, d, qd) != 1) return 0;
    for (int i = 0; i < 8; i++) {
        unsigned __int128 t = (unsigned __int128)qd[i] + rem[i] + carry;
        qd[i] = (uint64_t)t;
        carry = t >> 64;
    }
    if (carry) return 0;
    for (int i = 0; i < 8; i++) if (qd[i] != n[i]) return 0;
    if (rem[4] | rem[5] | rem[6] | rem[7]) return 0;
    for (int j = 3; j >= 0; j--) {
        if (rem[j] > d[j]) return 0;
        if (rem[j] < d[j]) return 1;
    }
    return 0;
}

static int muldiv64(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                    uint64_t q[4], uint64_t rem4[4]) {
    uint64_t p[8], rem[8];
    int st = mul64(a, b, p);
    if (st != 1) return st;
    st = div64(p, d, q, rem);
    if (st != 1) return st;
    if (!identity64(p, q, d, rem)) return -2;
    memcpy(rem4, rem, 4 * sizeof(uint64_t));
    return 1;
}

static int p512_eq_l16(const uint16_t n[32], const uint64_t p[8]) {
    uint16_t tmp[16];
    for (int half = 0; half < 2; half++) {
        w64_to_l16(p + half * 4, tmp);
        for (int i = 0; i < 16; i++)
            if (n[half * 16 + i] != tmp[i]) return 0;
    }
    return 1;
}

static void fill_u64(uint16_t l[16], uint64_t v) {
    memset(l, 0, 16 * sizeof(uint16_t));
    uint64_t w[4] = {v, 0, 0, 0};
    w64_to_l16(w, l);
}
static void fill_max(uint16_t l[16]) {
    for (int i = 0; i < 16; i++) l[i] = 0xffff;
}
static int expect_st(int st, int want, const char *m) {
    if (st != want) {
        fprintf(stderr, "FAIL %s status=%d want=%d\n", m, st, want);
        return 1;
    }
    return 0;
}

static int selftest(void) {
    uint16_t a[16], b[16], d[16], q[16], rem[32], n[32];
    uint64_t a64[4], b64[4], d64[4], q64[4], r64[4], p64[8];
    int st, fail = 0;

    fill_u64(a, 7); fill_u64(b, 9); fill_u64(d, 2);
    st = muldiv16(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "7*9/2");
    if (q[0] != 31 || rem[0] != 1) {
        fprintf(stderr, "FAIL 7*9/2 q=%u r=%u\n", q[0], rem[0]);
        fail = 1;
    }
    l16_to_w64(a, a64); l16_to_w64(b, b64); l16_to_w64(d, d64);
    st = muldiv64(a64, b64, d64, q64, r64);
    fail |= expect_st(st, 1, "7*9/2 w64");
    if (q64[0] != 31 || r64[0] != 1) { fprintf(stderr, "FAIL 64 7*9/2\n"); fail = 1; }

    fill_max(a); fill_max(b);
    st = mul16(a, b, n);
    fail |= expect_st(st, 1, "max*max");
    if (n[0] != 1) { fprintf(stderr, "FAIL max^2 lo\n"); fail = 1; }
    if (n[16] != 0xfffe) { fprintf(stderr, "FAIL max^2 hi limb16\n"); fail = 1; }
    l16_to_w64(a, a64); l16_to_w64(b, b64);
    st = mul64(a64, b64, p64);
    fail |= expect_st(st, 1, "max*max 64");
    if (!p512_eq_l16(n, p64)) { fprintf(stderr, "FAIL max^2 width mismatch\n"); fail = 1; }
    if (p64[0] != 1 || p64[4] != ~0ULL - 1ULL) {
        fprintf(stderr, "FAIL max^2 64 words\n"); fail = 1;
    }

    memset(a, 0, sizeof a); a[15] = 0x8000; /* 2^255 */
    fill_u64(b, 2); fill_u64(d, 3);
    st = muldiv16(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "2^255*2/3");
    if (q[0] != 0x5555 || q[15] != 0x5555 || rem[0] != 1) {
        fprintf(stderr, "FAIL 2^255*2/3 pattern q0=%04x r0=%u\n", q[0], rem[0]);
        fail = 1;
    }
    if (!identity16(n, q, d, rem)) { fprintf(stderr, "FAIL identity 2^255*2/3\n"); fail = 1; }
    l16_to_w64(a, a64); l16_to_w64(b, b64); l16_to_w64(d, d64);
    st = muldiv64(a64, b64, d64, q64, r64);
    fail |= expect_st(st, 1, "2^255*2/3 w64");
    if (q64[0] != 0x5555555555555555ULL || r64[0] != 1) fail = 1;

    fill_u64(a, 1); fill_u64(b, 1); memset(d, 0, sizeof d);
    fail |= expect_st(muldiv16(a, b, d, q, rem, n), -1, "d=0");

    memset(a, 0, sizeof a); a[15] = 0x8000;
    fill_u64(b, 2); fill_u64(d, 1);
    fail |= expect_st(muldiv16(a, b, d, q, rem, n), -2, "q overflow");

    fill_u64(a, 997000); fill_u64(b, 20000); fill_u64(d, 10997000);
    st = muldiv16(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "getAmountOut");
    l16_to_w64(q, q64);
    if (q64[0] != 1813) { fprintf(stderr, "FAIL 1813 got %" PRIu64 "\n", q64[0]); fail = 1; }

    memset(a, 0, sizeof a); a[0] = 2;
    memset(b, 0, sizeof b); b[15] = 0x8000;
    fill_max(d);
    st = muldiv16(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "2*2^255/(2^256-1) 16");
    l16_to_w64(a, a64); l16_to_w64(b, b64); l16_to_w64(d, d64);
    st = muldiv64(a64, b64, d64, q64, r64);
    fail |= expect_st(st, 1, "2*2^255/(2^256-1) 64");
    if (q[0] != 1 || rem[0] != 1 || q64[0] != 1 || r64[0] != 1) {
        fprintf(stderr, "FAIL wrap-borrow q16=%u r16=%u q64=%" PRIu64 " r64=%" PRIu64 "\n",
                q[0], rem[0], q64[0], r64[0]);
        fail = 1;
    }
    {
        uint16_t A[32] = {0}, B[32] = {0};
        A[16] = 1;
        for (int i = 0; i < 16; i++) B[i] = 0xffff;
        if (!ge16(A, B, 32) || ge16(B, A, 32) || !ge16(A, A, 32)) fail = 1;
    }

    if (fail) return 1;
    printf("SELFTEST_PASS identity_2_255_x2_div3 q*d+r==n\n");
    return 0;
}

static int run_batch(void) {
    char line[512], op[16], ha[130], hb[130], hd[130];
    uint8_t bea[32], beb[32], bed[32], beq[32], ber[32];
    uint16_t a[16], b[16], d[16], q[16], rem[32], n[32];
    uint64_t a64[4], b64[4], d64[4], q64[4], r64[4], p64[8];
    char qhex[65], rhex[65];
    int nvec = 0;
    while (fgets(line, sizeof line, stdin)) {
        int nf = sscanf(line, "%15s %129s %129s %129s", op, ha, hb, hd);
        if (nf < 3) continue;
        if (parse_hex_be(ha, bea, 32) || parse_hex_be(hb, beb, 32)) return 1;
        be32_to_l16(bea, a); be32_to_l16(beb, b);
        l16_to_w64(a, a64); l16_to_w64(b, b64);
        if (strcmp(op, "MUL") == 0) {
            int st16 = mul16(a, b, n);
            int st64 = mul64(a64, b64, p64);
            if (st16 != st64) { fprintf(stderr, "DIVERGE MUL status\n"); return 1; }
            if (st16 == 1 && !p512_eq_l16(n, p64)) { fprintf(stderr, "DIVERGE MUL\n"); return 1; }
            l16_to_be32(n, beq); l16_to_be32(n + 16, ber);
            hex_of(beq, 32, qhex); hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st16, qhex, rhex);
        } else if (strcmp(op, "MULDIV") == 0) {
            if (nf < 4 || parse_hex_be(hd, bed, 32)) return 1;
            be32_to_l16(bed, d); l16_to_w64(d, d64);
            int st16 = muldiv16(a, b, d, q, rem, n);
            int st64 = muldiv64(a64, b64, d64, q64, r64);
            if (st16 != st64) {
                fprintf(stderr, "DIVERGE MULDIV status 16=%d 64=%d a=%s b=%s d=%s\n",
                        st16, st64, ha, hb, hd);
                return 1;
            }
            if (st16 == 1) {
                uint16_t qchk[16], rchk[16];
                w64_to_l16(q64, qchk); w64_to_l16(r64, rchk);
                for (int i = 0; i < 16; i++)
                    if (q[i] != qchk[i] || rem[i] != rchk[i]) {
                        fprintf(stderr, "DIVERGE MULDIV words\n"); return 1;
                    }
            }
            l16_to_be32(q, beq); l16_to_be32(rem, ber);
            hex_of(beq, 32, qhex); hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st16, qhex, rhex);
        } else {
            fprintf(stderr, "unknown op %s\n", op);
            return 1;
        }
        nvec++;
    }
    fprintf(stderr, "BATCH_N=%d WIDTH_CONSENSUS\n", nvec);
    return 0;
}
int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return selftest();
    if (argc >= 2 && strcmp(argv[1], "--batch") == 0) return run_batch();
    fprintf(stderr, "usage: u512_coprocessor_c11 --self-test | --batch\n");
    return 2;
}
