/* Independent C11 oracle: schoolbook in radix 2^32 (not TCB).
 * 8 x uint32 = 256 bits, 16 x uint32 = 512 bits.
 * Carry of a*b+acc fits exactly in uint64: (2^32-1)^2 + 2(2^32-1) = 2^64-1.
 * EXPERIMENTAL: FullMath width, not CRT/mulmod. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
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

static void be_to_u32(const uint8_t *be, size_t nbe, uint32_t *l, int nl) {
    memset(l, 0, (size_t)nl * sizeof(uint32_t));
    for (int i = 0; i < nl; i++) {
        size_t o = nbe - 4 * (size_t)(i + 1);
        if (o + 4 > nbe) break;
        l[i] = ((uint32_t)be[o] << 24) | ((uint32_t)be[o + 1] << 16) |
               ((uint32_t)be[o + 2] << 8) | (uint32_t)be[o + 3];
    }
}

static void u32_to_be32(const uint32_t l[8], uint8_t be[32]) {
    memset(be, 0, 32);
    for (int i = 0; i < 8; i++) {
        size_t o = 32 - 4 * (size_t)(i + 1);
        be[o] = (uint8_t)(l[i] >> 24);
        be[o + 1] = (uint8_t)(l[i] >> 16);
        be[o + 2] = (uint8_t)(l[i] >> 8);
        be[o + 3] = (uint8_t)l[i];
    }
}

static void hex_of(const uint8_t *p, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[2 * i] = H[p[i] >> 4];
        out[2 * i + 1] = H[p[i] & 15];
    }
    out[2 * n] = 0;
}

static int z32(const uint32_t *l, int n) {
    for (int i = 0; i < n; i++) if (l[i]) return 0;
    return 1;
}

static int ge32(const uint32_t *a, const uint32_t *b, int n) {
    for (int j = n - 1; j >= 0; j--) {
        if (a[j] > b[j]) return 1;
        if (a[j] < b[j]) return 0;
    }
    return 1;
}

static int mul32(const uint32_t a[8], const uint32_t b[8], uint32_t n[16]) {
    memset(n, 0, 16 * sizeof(uint32_t));
    for (int i = 0; i < 8; i++) {
        uint64_t carry = 0;
        for (int j = 0; j < 8; j++) {
            int k = i + j;
            uint64_t t = (uint64_t)n[k] + (uint64_t)a[i] * (uint64_t)b[j] + carry;
            n[k] = (uint32_t)t;
            carry = t >> 32;
        }
        int k = i + 8;
        while (k < 16 && carry) {
            uint64_t t = (uint64_t)n[k] + carry;
            n[k] = (uint32_t)t;
            carry = t >> 32;
            k++;
        }
        if (carry) return -2;
    }
    return 1;
}

static int div32(const uint32_t n[16], const uint32_t d[8],
                 uint32_t q[8], uint32_t rem[16]) {
    memset(q, 0, 8 * sizeof(uint32_t));
    memset(rem, 0, 16 * sizeof(uint32_t));
    if (z32(d, 8)) return -1;
    for (int bit = 511; bit >= 0; bit--) {
        int limb = bit >> 5, pos = bit & 31;
        uint64_t carry = (n[limb] >> pos) & 1u;
        for (int j = 0; j < 16; j++) {
            uint64_t t = ((uint64_t)rem[j] << 1) + carry;
            rem[j] = (uint32_t)t;
            carry = t >> 32;
        }
        if (carry) return -2;
        int ge = 0;
        for (int j = 15; j >= 0; j--) {
            uint32_t dj = (j < 8) ? d[j] : 0;
            if (rem[j] > dj) { ge = 1; break; }
            if (rem[j] < dj) { ge = -1; break; }
        }
        if (ge >= 0) {
            if (bit >= 256) return -2;
            q[limb] |= (1u << pos);
            unsigned borrow = 0;
            for (int j = 0; j < 16; j++) {
                uint64_t sub = (uint64_t)((j < 8) ? d[j] : 0) + borrow;
                if (rem[j] < sub) {
                    rem[j] = (uint32_t)(((uint64_t)1 << 32) + rem[j] - sub);
                    borrow = 1;
                } else {
                    rem[j] = (uint32_t)(rem[j] - sub);
                    borrow = 0;
                }
            }
        }
    }
    return 1;
}

static int identity32(const uint32_t n[16], const uint32_t q[8],
                      const uint32_t d[8], const uint32_t rem[16]) {
    uint32_t qd[16];
    if (mul32(q, d, qd) != 1) return 0;
    uint64_t carry = 0;
    for (int i = 0; i < 16; i++) {
        uint64_t t = (uint64_t)qd[i] + rem[i] + carry;
        qd[i] = (uint32_t)t;
        carry = t >> 32;
    }
    if (carry) return 0;
    for (int i = 0; i < 16; i++) if (qd[i] != n[i]) return 0;
    uint32_t dext[16];
    memset(dext, 0, sizeof dext);
    memcpy(dext, d, 8 * sizeof(uint32_t));
    return !ge32(rem, dext, 16);
}

static int muldiv32(const uint32_t a[8], const uint32_t b[8], const uint32_t d[8],
                    uint32_t q[8], uint32_t rem[16], uint32_t n[16]) {
    int st = mul32(a, b, n);
    if (st != 1) return st;
    st = div32(n, d, q, rem);
    if (st != 1) return st;
    if (!identity32(n, q, d, rem)) return -2;
    return 1;
}

static void fill_u64(uint32_t l[8], uint64_t v) {
    memset(l, 0, 8 * sizeof(uint32_t));
    l[0] = (uint32_t)v;
    l[1] = (uint32_t)(v >> 32);
}

static int expect_st(int st, int want, const char *m) {
    if (st != want) {
        fprintf(stderr, "FAIL %s status=%d want=%d\n", m, st, want);
        return 1;
    }
    return 0;
}

static int selftest(void) {
    uint32_t a[8], b[8], d[8], q[8], rem[16], n[16];
    int st, fail = 0;

    fill_u64(a, 7); fill_u64(b, 9); fill_u64(d, 2);
    st = muldiv32(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "7*9/2");
    if (q[0] != 31 || rem[0] != 1) { fprintf(stderr, "FAIL 7*9/2 words\n"); fail = 1; }

    memset(a, 0xff, sizeof a); memset(b, 0xff, sizeof b);
    st = mul32(a, b, n);
    fail |= expect_st(st, 1, "max*max");
    if (n[0] != 1) { fprintf(stderr, "FAIL max^2 lo\n"); fail = 1; }
    if (n[8] != 0xfffffffeu) { fprintf(stderr, "FAIL max^2 hi limb8\n"); fail = 1; }

    memset(a, 0, sizeof a); a[7] = 0x80000000u;
    fill_u64(b, 2); fill_u64(d, 3);
    st = muldiv32(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "2^255*2/3");
    if (q[0] != 0x55555555u || q[7] != 0x55555555u || rem[0] != 1) {
        fprintf(stderr, "FAIL 2^255*2/3 pattern\n"); fail = 1;
    }
    if (!identity32(n, q, d, rem)) { fprintf(stderr, "FAIL identity 2^255*2/3\n"); fail = 1; }

    fill_u64(a, 1); fill_u64(b, 1); memset(d, 0, sizeof d);
    fail |= expect_st(muldiv32(a, b, d, q, rem, n), -1, "d=0");

    memset(a, 0, sizeof a); a[7] = 0x80000000u;
    fill_u64(b, 2); fill_u64(d, 1);
    fail |= expect_st(muldiv32(a, b, d, q, rem, n), -2, "q overflow");

    fill_u64(a, 997000); fill_u64(b, 20000); fill_u64(d, 10997000);
    st = muldiv32(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "getAmountOut");
    if (q[0] != 1813) { fprintf(stderr, "FAIL 1813\n"); fail = 1; }

    memset(a, 0, sizeof a); a[0] = 2;
    memset(b, 0, sizeof b); b[7] = 0x80000000u;
    memset(d, 0xff, sizeof d);
    st = muldiv32(a, b, d, q, rem, n);
    fail |= expect_st(st, 1, "wrap-borrow");
    if (q[0] != 1 || rem[0] != 1) { fprintf(stderr, "FAIL wrap-borrow words\n"); fail = 1; }

    {
        uint32_t A[16] = {0}, B[16] = {0};
        A[8] = 1;
        memset(B, 0xff, 8 * sizeof(uint32_t));
        if (!ge32(A, B, 16) || ge32(B, A, 16) || !ge32(A, A, 16)) fail = 1;
    }

    if (fail) return 1;
    printf("SELFTEST_PASS radix32 q*d+r==n ge512 carry_fits_u64\n");
    return 0;
}

static int run_batch(void) {
    char line[512], op[16], ha[260], hb[260], hd[130];
    uint8_t bea[64], beb[64], bed[32], beq[32], ber[32];
    uint32_t a[8], b[8], d[8], q[8], rem[16], n[16];
    uint32_t A[16], B[16];
    char qhex[65], rhex[65];
    int nvec = 0;
    while (fgets(line, sizeof line, stdin)) {
        int nf = sscanf(line, "%15s %259s %259s %129s", op, ha, hb, hd);
        if (nf < 3) continue;
        if (strcmp(op, "GE") == 0) {
            if (parse_hex_be(ha, bea, 64) || parse_hex_be(hb, beb, 64)) return 1;
            be_to_u32(bea, 64, A, 16);
            be_to_u32(beb, 64, B, 16);
            printf("%d\n", ge32(A, B, 16));
        } else if (strcmp(op, "MUL") == 0) {
            if (parse_hex_be(ha, bea, 32) || parse_hex_be(hb, beb, 32)) return 1;
            be_to_u32(bea, 32, a, 8);
            be_to_u32(beb, 32, b, 8);
            int st = mul32(a, b, n);
            u32_to_be32(n, beq);
            u32_to_be32(n + 8, ber);
            hex_of(beq, 32, qhex);
            hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st, qhex, rhex);
        } else if (strcmp(op, "MULDIV") == 0) {
            if (nf < 4 || parse_hex_be(ha, bea, 32) || parse_hex_be(hb, beb, 32) ||
                parse_hex_be(hd, bed, 32)) return 1;
            be_to_u32(bea, 32, a, 8);
            be_to_u32(beb, 32, b, 8);
            be_to_u32(bed, 32, d, 8);
            int st = muldiv32(a, b, d, q, rem, n);
            u32_to_be32(q, beq);
            u32_to_be32(rem, ber);
            hex_of(beq, 32, qhex);
            hex_of(ber, 32, rhex);
            printf("%d %s %s\n", st, qhex, rhex);
        } else {
            fprintf(stderr, "unknown op %s\n", op);
            return 1;
        }
        nvec++;
    }
    fprintf(stderr, "BATCH_N=%d RADIX32_CONSENSUS\n", nvec);
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "--self-test") == 0) return selftest();
    if (argc >= 2 && strcmp(argv[1], "--batch") == 0) return run_batch();
    fprintf(stderr, "usage: u512_radix32_oracle --self-test | --batch\n");
    return 2;
}
