/*
 * Independent C11 oracle for the LIN u512 numeric coprocessor.
 * Path A: 64-bit schoolbook via unsigned __int128.
 * Path B: 16-bit limbs matching src/lin_u512_coprocessor.lin.
 * Consensus A==B is required before any LIN comparison. Not in the TCB.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MASK16 65535u

typedef struct {
    int status;
    uint64_t q[4];
    uint64_t r[4];
    uint64_t n[8];
} U512Res;

static void z4(uint64_t w[4]) { memset(w, 0, 32); }
static void z8(uint64_t w[8]) { memset(w, 0, 64); }

static int hex_digit(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_u256(const char *s, uint64_t w[4]) {
    unsigned char b[32];
    int n, i, v;
    const char *p = s;
    memset(b, 0, 32);
    z4(w);
    if (p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) p += 2;
    n = (int)strlen(p);
    if (n == 0 || n > 64) return 0;
    for (i = 0; i < n; i++) {
        v = hex_digit(p[n - 1 - i]);
        if (v < 0) return 0;
        if ((i & 1) == 0) b[31 - i / 2] = (unsigned char)v;
        else b[31 - i / 2] |= (unsigned char)(v << 4);
    }
    for (i = 0; i < 4; i++) {
        int o = 24 - 8 * i;
        w[i] = ((uint64_t)b[o] << 56) | ((uint64_t)b[o + 1] << 48) |
               ((uint64_t)b[o + 2] << 40) | ((uint64_t)b[o + 3] << 32) |
               ((uint64_t)b[o + 4] << 24) | ((uint64_t)b[o + 5] << 16) |
               ((uint64_t)b[o + 6] << 8) | (uint64_t)b[o + 7];
    }
    return 1;
}

static void print_u256(const char *k, const uint64_t w[4]) {
    printf("%s=0x%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "\n",
           k, w[3], w[2], w[1], w[0]);
}

static void print_u512(const char *k, const uint64_t w[8]) {
    printf("%s=0x%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "%016" PRIx64
           "%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "%016" PRIx64 "\n",
           k, w[7], w[6], w[5], w[4], w[3], w[2], w[1], w[0]);
}

static int ge8(const uint64_t a[8], const uint64_t b[8]) {
    int i;
    for (i = 7; i >= 0; i--) {
        if (a[i] > b[i]) return 1;
        if (a[i] < b[i]) return 0;
    }
    return 1;
}

static void mul_wide(const uint64_t a[4], const uint64_t b[4], uint64_t n[8]) {
    int i, j, k;
    z8(n);
    for (i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (j = 0; j < 4; j++) {
            unsigned __int128 t =
                (unsigned __int128)n[i + j] + (unsigned __int128)a[i] * b[j] + carry;
            n[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        for (k = i + 4; carry && k < 8; k++) {
            unsigned __int128 t = (unsigned __int128)n[k] + carry;
            n[k] = (uint64_t)t;
            carry = t >> 64;
        }
    }
}

static void muldiv_wide(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                        U512Res *out) {
    uint64_t rem[8], dext[8];
    int bit, i, take;
    uint64_t inbit, br, dd, x;
    mul_wide(a, b, out->n);
    if ((d[0] | d[1] | d[2] | d[3]) == 0) {
        out->status = -1; z4(out->q); z4(out->r); return;
    }
    memset(rem, 0, sizeof(rem));
    memset(dext, 0, sizeof(dext));
    memcpy(dext, d, 32);
    z4(out->q);
    out->status = 1;
    for (bit = 511; bit >= 0; bit--) {
        inbit = (out->n[bit / 64] >> (bit & 63)) & 1ull;
        br = inbit;
        for (i = 0; i < 8; i++) {
            unsigned __int128 acc = ((unsigned __int128)rem[i] << 1) | br;
            rem[i] = (uint64_t)acc;
            br = (uint64_t)(acc >> 64);
        }
        take = ge8(rem, dext);
        if (!take) continue;
        if (bit >= 256) {
            out->status = -2; z4(out->q); z4(out->r); return;
        }
        out->q[bit / 64] |= 1ull << (bit & 63);
        br = 0;
        for (i = 0; i < 8; i++) {
            dd = dext[i];
            x = rem[i];
            rem[i] = x - dd - br;
            br = (x < dd) || (x - dd < br);
        }
    }
    memcpy(out->r, rem, 32);
}

static void w2l(const uint64_t w[4], uint32_t L[16]) {
    int i;
    for (i = 0; i < 16; i++) L[i] = (uint32_t)((w[i / 4] >> (16 * (i % 4))) & MASK16);
}

static void l2w16(const uint32_t L[16], uint64_t w[4]) {
    int i;
    z4(w);
    for (i = 0; i < 16; i++) w[i / 4] |= ((uint64_t)(L[i] & MASK16)) << (16 * (i % 4));
}

static void l2w32(const uint32_t L[32], uint64_t w[8]) {
    int i;
    z8(w);
    for (i = 0; i < 32; i++) w[i / 4] |= ((uint64_t)(L[i] & MASK16)) << (16 * (i % 4));
}

static void muldiv_limbs(const uint64_t a[4], const uint64_t b[4], const uint64_t d[4],
                         U512Res *out) {
    uint64_t t64;
    uint32_t A[16], B[16], D[16], N[32], R[32], Q[16];
    int i, j, k, bit, t, carry, borrow, cmp, dj, in_bit;
    memset(N, 0, sizeof(N)); memset(R, 0, sizeof(R)); memset(Q, 0, sizeof(Q));
    w2l(a, A); w2l(b, B); w2l(d, D);
    for (i = 0; i < 16; i++) {
        t64 = 0;
        for (j = 0; j < 16; j++) {
            k = i + j;
            t64 = (uint64_t)N[k] + (uint64_t)A[i] * (uint64_t)B[j] + t64;
            N[k] = (uint32_t)(t64 & MASK16);
            t64 >>= 16;
        }
        k = i + 16;
        while (k < 32 && t64) {
            t64 = (uint64_t)N[k] + t64;
            N[k] = (uint32_t)(t64 & MASK16);
            t64 >>= 16;
            k++;
        }
    }
    l2w32(N, out->n);
    if ((d[0] | d[1] | d[2] | d[3]) == 0) {
        out->status = -1; z4(out->q); z4(out->r); return;
    }
    out->status = 1;
    for (bit = 511; bit >= 0; bit--) {
        in_bit = (int)((N[bit >> 4] >> (bit & 15)) & 1u);
        carry = in_bit;
        for (j = 0; j < 32; j++) {
            t = (int)R[j] * 2 + carry;
            R[j] = (uint32_t)(t & (int)MASK16);
            carry = t >> 16;
        }
        cmp = 0;
        for (j = 31; j >= 0; j--) {
            dj = (j < 16) ? (int)D[j] : 0;
            if (cmp == 0) {
                if ((int)R[j] > dj) cmp = 1;
                else if ((int)R[j] < dj) cmp = -1;
            }
        }
        if (cmp < 0) continue;
        if (bit >= 256) {
            out->status = -2; z4(out->q); z4(out->r); return;
        }
        Q[bit >> 4] |= (uint32_t)(1u << (bit & 15));
        borrow = 0;
        for (j = 0; j < 32; j++) {
            dj = (j < 16) ? (int)D[j] : 0;
            t = (int)R[j] - dj - borrow;
            if (t < 0) { R[j] = (uint32_t)(t + 65536); borrow = 1; }
            else { R[j] = (uint32_t)t; borrow = 0; }
        }
    }
    l2w16(Q, out->q);
    l2w16(R, out->r);
}

static int res_eq(const U512Res *x, const U512Res *y) {
    return x->status == y->status && memcmp(x->q, y->q, 32) == 0 &&
           memcmp(x->r, y->r, 32) == 0 && memcmp(x->n, y->n, 64) == 0;
}

static void emit(const U512Res *r) {
    printf("status=%d\n", r->status);
    print_u256("q", r->q);
    print_u256("r", r->r);
    print_u512("n", r->n);
}

static uint64_t splitmix(uint64_t *s) {
    uint64_t z = (*s += 0x9e3779b97f4a7c15ull);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

static int add4(const uint64_t a[4], const uint64_t b[4], uint64_t s[4]) {
    unsigned __int128 c = 0;
    int i;
    for (i = 0; i < 4; i++) {
        c += (unsigned __int128)a[i] + b[i];
        s[i] = (uint64_t)c;
        c >>= 64;
    }
    return c != 0;
}

static void amm_out(const uint64_t ain[4], const uint64_t rin[4], const uint64_t rout[4],
                   U512Res *out) {
    uint64_t one[4] = {1, 0, 0, 0}, c997[4] = {997, 0, 0, 0}, c1000[4] = {1000, 0, 0, 0};
    uint64_t den[4];
    U512Res fee, rin1000;
    z4(out->q); z4(out->r); z8(out->n);
    if ((ain[0] | ain[1] | ain[2] | ain[3]) == 0 ||
        (rin[0] | rin[1] | rin[2] | rin[3]) == 0 ||
        (rout[0] | rout[1] | rout[2] | rout[3]) == 0) {
        out->status = -1; return;
    }
    muldiv_wide(ain, c997, one, &fee);
    if (fee.status != 1) { out->status = -2; return; }
    muldiv_wide(rin, c1000, one, &rin1000);
    if (rin1000.status != 1) { out->status = -2; return; }
    if (add4(rin1000.q, fee.q, den)) { out->status = -2; return; }
    muldiv_wide(fee.q, rout, den, out);
}

static int selftest(void) {
    struct { const char *a, *b, *d; } vec[] = {
        {"3", "5", "1"}, {"7", "9", "2"}, {"64", "c8", "32"},
        {"1", "1", "0"},
        {"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
         "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "1"},
        {"8000000000000000000000000000000000000000000000000000000000000000", "2", "3"},
        {"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
         "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
         "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
        {"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "1",
         "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
    };
    int i, fail = 0;
    uint64_t seed = 0x5125125125125125ull;
    for (i = 0; i < (int)(sizeof(vec) / sizeof(vec[0])); i++) {
        uint64_t a[4], b[4], d[4];
        U512Res w, l;
        if (!parse_hex_u256(vec[i].a, a) || !parse_hex_u256(vec[i].b, b) ||
            !parse_hex_u256(vec[i].d, d)) return 1;
        muldiv_wide(a, b, d, &w);
        muldiv_limbs(a, b, d, &l);
        if (!res_eq(&w, &l)) fail++;
    }
    for (i = 0; i < 256; i++) {
        uint64_t a[4], b[4], d[4];
        U512Res w, l;
        int k;
        for (k = 0; k < 4; k++) {
            a[k] = splitmix(&seed); b[k] = splitmix(&seed); d[k] = splitmix(&seed);
        }
        if ((i % 17) == 0) z4(d);
        if ((i % 19) == 0) { a[3] |= (1ull << 63); b[0] = 2; }
        muldiv_wide(a, b, d, &w);
        muldiv_limbs(a, b, d, &l);
        if (!res_eq(&w, &l)) { fail++; break; }
    }
    {
        uint64_t ain[4] = {1000, 0, 0, 0}, rin[4] = {10000, 0, 0, 0}, rout[4] = {20000, 0, 0, 0};
        U512Res a;
        amm_out(ain, rin, rout, &a);
        if (a.status != 1 || a.q[0] != 1813ull || a.q[1] || a.q[2] || a.q[3]) fail++;
    }
    if (fail) {
        fprintf(stderr, "u512_coprocessor_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("u512_coprocessor_c11 selftest PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t a[4], b[4], d[4];
    U512Res w, l;
    const char *cmd;
    int use_limbs = 0;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | muldiv a b d | mul a b | ge lo hi lo hi | amm ain rin rout\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        use_limbs = 1; argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        if (!parse_hex_u256(argv[2], a) || !parse_hex_u256(argv[3], b) ||
            !parse_hex_u256(argv[4], d)) return 2;
        if (use_limbs) muldiv_limbs(a, b, d, &l); else muldiv_wide(a, b, d, &l);
        if (use_limbs) muldiv_wide(a, b, d, &w); else muldiv_limbs(a, b, d, &w);
        if (!res_eq(&l, &w)) { fprintf(stderr, "internal wide/limbs diverge\n"); return 1; }
        emit(&l);
        return 0;
    }
    if (strcmp(cmd, "mul") == 0 && argc == 4) {
        uint64_t one[4] = {1, 0, 0, 0};
        if (!parse_hex_u256(argv[2], a) || !parse_hex_u256(argv[3], b)) return 2;
        mul_wide(a, b, w.n);
        muldiv_limbs(a, b, one, &l);
        if (memcmp(w.n, l.n, 64) != 0) return 1;
        print_u512("n", w.n);
        return 0;
    }
    if (strcmp(cmd, "ge") == 0 && argc == 6) {
        uint64_t ah[4], bh[4], ax[8], bx[8];
        if (!parse_hex_u256(argv[2], a) || !parse_hex_u256(argv[3], ah) ||
            !parse_hex_u256(argv[4], b) || !parse_hex_u256(argv[5], bh)) return 2;
        z8(ax); z8(bx);
        memcpy(ax, a, 32); memcpy(ax + 4, ah, 32);
        memcpy(bx, b, 32); memcpy(bx + 4, bh, 32);
        printf("ge=%d\n", ge8(ax, bx));
        return 0;
    }
    if (strcmp(cmd, "amm") == 0 && argc == 5) {
        if (!parse_hex_u256(argv[2], a) || !parse_hex_u256(argv[3], b) ||
            !parse_hex_u256(argv[4], d)) return 2;
        amm_out(a, b, d, &l);
        emit(&l);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
