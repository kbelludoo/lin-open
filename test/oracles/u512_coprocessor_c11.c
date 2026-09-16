/*
 * Independent C11 oracle for the LIN u512 numeric coprocessor.
 *
 * Two implementations that must agree before any LIN comparison:
 *   1. Portable 32-bit limbs (uint32 x uint32 -> uint64), 8 limbs / 256 bits
 *   2. 64-bit limbs with unsigned __int128 limb products (GCC/Clang)
 *
 * This file is a test oracle. It is not linked into the LIN compiler TCB.
 *
 * Spec width: Uniswap v3 FullMath.mulDiv (floor(a*b/d), 512-bit product,
 * revert if d==0 or q does not fit uint256). Algorithm here is restoring
 * division, not the Solidity CRT/Newton path.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define U32MASK 0xffffffffu
#define LIMB32 8
#define PROD32 16

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex_be(const char *s, uint8_t *out, size_t nbytes) {
    size_t n;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    n = strlen(s);
    memset(out, 0, nbytes);
    if (n > nbytes * 2) return 0;
    {
        size_t pad = nbytes * 2 - n;
        size_t i;
        for (i = 0; i < n; i++) {
            int v = hexval((unsigned char)s[i]);
            size_t pos;
            if (v < 0) return 0;
            pos = pad + i;
            if ((pos & 1u) == 0) out[pos / 2] = (uint8_t)(v << 4);
            else out[pos / 2] |= (uint8_t)v;
        }
    }
    return 1;
}

static void bytes_be_to_u32le(const uint8_t *be, size_t nbytes, uint32_t *limbs, int nlim) {
    int i;
    memset(limbs, 0, (size_t)nlim * sizeof(uint32_t));
    for (i = 0; i < nlim; i++) {
        int base = (int)nbytes - 4 * (i + 1);
        if (base < 0) break;
        limbs[i] = ((uint32_t)be[base] << 24) | ((uint32_t)be[base + 1] << 16) |
                   ((uint32_t)be[base + 2] << 8) | (uint32_t)be[base + 3];
    }
}

static void u32le_to_bytes_be(const uint32_t *limbs, int nlim, uint8_t *be, size_t nbytes) {
    int i;
    memset(be, 0, nbytes);
    for (i = 0; i < nlim; i++) {
        int base = (int)nbytes - 4 * (i + 1);
        uint32_t w;
        if (base < 0) break;
        w = limbs[i];
        be[base] = (uint8_t)(w >> 24);
        be[base + 1] = (uint8_t)(w >> 16);
        be[base + 2] = (uint8_t)(w >> 8);
        be[base + 3] = (uint8_t)w;
    }
}

static void print_hex(const uint8_t *p, size_t n) {
    size_t i;
    for (i = 0; i < n; i++) printf("%02x", p[i]);
}

static void mul32(const uint32_t a[LIMB32], const uint32_t b[LIMB32], uint32_t n[PROD32]) {
    int i, j, k;
    memset(n, 0, PROD32 * sizeof(uint32_t));
    for (i = 0; i < LIMB32; i++) {
        uint64_t carry = 0;
        for (j = 0; j < LIMB32; j++) {
            uint64_t t = (uint64_t)n[i + j] + (uint64_t)a[i] * (uint64_t)b[j] + carry;
            n[i + j] = (uint32_t)t;
            carry = t >> 32;
        }
        k = i + LIMB32;
        while (k < PROD32 && carry) {
            uint64_t t = (uint64_t)n[k] + carry;
            n[k] = (uint32_t)t;
            carry = t >> 32;
            k++;
        }
    }
}

static int ge32(const uint32_t a[], const uint32_t b[], int nlim) {
    int i;
    for (i = nlim - 1; i >= 0; i--) {
        if (a[i] > b[i]) return 1;
        if (a[i] < b[i]) return 0;
    }
    return 1;
}

static int eq32(const uint32_t a[], const uint32_t b[], int nlim) {
    return memcmp(a, b, (size_t)nlim * sizeof(uint32_t)) == 0;
}

/* Restoring 512/256. status: 1 ok, -1 d=0, -2 q overflow. */
static int div32(const uint32_t n[PROD32], const uint32_t d[LIMB32],
                 uint32_t q[LIMB32], uint32_t r[LIMB32]) {
    uint32_t rem[LIMB32];
    int bit, j;
    int d_zero = 1;
    memset(q, 0, LIMB32 * sizeof(uint32_t));
    memset(r, 0, LIMB32 * sizeof(uint32_t));
    memset(rem, 0, sizeof(rem));
    for (j = 0; j < LIMB32; j++) if (d[j]) d_zero = 0;
    if (d_zero) return -1;
    for (bit = 511; bit >= 0; bit--) {
        int limb = bit / 32;
        int pos = bit & 31;
        uint32_t in_bit = (n[limb] >> pos) & 1u;
        uint32_t carry = in_bit;
        int cmp, take;
        for (j = 0; j < LIMB32; j++) {
            uint64_t t = ((uint64_t)rem[j] << 1) | (uint64_t)carry;
            rem[j] = (uint32_t)t;
            carry = (uint32_t)(t >> 32);
        }
        cmp = 0;
        for (j = LIMB32 - 1; j >= 0; j--) {
            if (cmp == 0) {
                if (rem[j] > d[j]) cmp = 1;
                else if (rem[j] < d[j]) cmp = -1;
            }
        }
        take = (carry == 1) || (cmp >= 0);
        if (take) {
            uint32_t borrow = 0;
            if (bit >= 256) return -2;
            q[bit / 32] |= (1u << (bit & 31));
            for (j = 0; j < LIMB32; j++) {
                uint64_t sub = (uint64_t)d[j] + borrow;
                if ((uint64_t)rem[j] < sub) {
                    rem[j] = (uint32_t)((uint64_t)rem[j] + 0x100000000ull - sub);
                    borrow = 1;
                } else {
                    rem[j] = (uint32_t)((uint64_t)rem[j] - sub);
                    borrow = 0;
                }
            }
        }
    }
    memcpy(r, rem, sizeof(rem));
    return 1;
}

#if defined(__SIZEOF_INT128__)
static void mul64(const uint64_t a[4], const uint64_t b[4], uint64_t n[8]) {
    int i, j, k;
    memset(n, 0, 8 * sizeof(uint64_t));
    for (i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (j = 0; j < 4; j++) {
            unsigned __int128 t = (unsigned __int128)n[i + j] +
                                  (unsigned __int128)a[i] * b[j] + carry;
            n[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (k < 8 && carry) {
            unsigned __int128 t = (unsigned __int128)n[k] + carry;
            n[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}

static void u32_to_u64(const uint32_t s[], int ns, uint64_t d[], int nd) {
    int i;
    memset(d, 0, (size_t)nd * sizeof(uint64_t));
    for (i = 0; i < ns; i++) d[i / 2] |= ((uint64_t)s[i]) << (32 * (i & 1));
}

static int limbs64_eq_u32(const uint64_t w[], int nw, const uint32_t s[], int ns) {
    uint64_t tmp[8];
    memset(tmp, 0, sizeof(tmp));
    u32_to_u64(s, ns, tmp, nw);
    return memcmp(tmp, w, (size_t)nw * sizeof(uint64_t)) == 0;
}
#endif

static int parse_256(const char *s, uint32_t o[LIMB32]) {
    uint8_t be[32];
    if (!parse_hex_be(s, be, 32)) return 0;
    bytes_be_to_u32le(be, 32, o, LIMB32);
    return 1;
}

static int parse_512(const char *s, uint32_t o[PROD32]) {
    uint8_t be[64];
    if (!parse_hex_be(s, be, 64)) return 0;
    bytes_be_to_u32le(be, 64, o, PROD32);
    return 1;
}

static void emit_256(const uint32_t x[LIMB32]) {
    uint8_t be[32];
    u32le_to_bytes_be(x, LIMB32, be, 32);
    print_hex(be, 32);
}

static void emit_512(const uint32_t x[PROD32]) {
    uint8_t be[64];
    u32le_to_bytes_be(x, PROD32, be, 64);
    print_hex(be, 64);
}

static int selftest(void) {
    uint32_t a[LIMB32], b[LIMB32], d[LIMB32], n[PROD32], q[LIMB32], r[LIMB32];
    uint32_t two[LIMB32], three[LIMB32], six[LIMB32];
    int st, fails = 0;
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b)); memset(d, 0, sizeof(d));
    memset(two, 0, sizeof(two)); memset(three, 0, sizeof(three)); memset(six, 0, sizeof(six));
    two[0] = 2; three[0] = 3; six[0] = 6;
    mul32(two, three, n);
    if (n[0] != 6) { fprintf(stderr, "mul 2*3\n"); fails++; }
    a[0] = 100; b[0] = 200; d[0] = 50;
    mul32(a, b, n);
    st = div32(n, d, q, r);
    if (st != 1 || q[0] != 400 || r[0] != 0) { fprintf(stderr, "muldiv 100*200/50\n"); fails++; }
    memset(d, 0, sizeof(d));
    st = div32(n, d, q, r);
    if (st != -1) { fprintf(stderr, "div0\n"); fails++; }
    /* 2^255 * 2 / 3 */
    memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b)); memset(d, 0, sizeof(d));
    a[7] = 0x80000000u;
    b[0] = 2;
    d[0] = 3;
    mul32(a, b, n);
    st = div32(n, d, q, r);
    if (st != 1 || r[0] != 1) { fprintf(stderr, "phantom rem\n"); fails++; }
    if (q[0] != 0x55555555u || q[1] != 0x55555555u || q[7] != 0x55555555u) {
        fprintf(stderr, "phantom q\n"); fails++;
    }
    /* (2^256-1)^2 / 1 -> q overflow */
    memset(a, 0xff, sizeof(a)); memset(b, 0xff, sizeof(b)); memset(d, 0, sizeof(d));
    d[0] = 1;
    mul32(a, b, n);
    st = div32(n, d, q, r);
    if (st != -2) { fprintf(stderr, "q overflow\n"); fails++; }
    if (n[0] != 1) { fprintf(stderr, "max*max lo\n"); fails++; }
    if (n[8] != 0xfffffffeu) { fprintf(stderr, "max*max hi0\n"); fails++; }
    if (!ge32(six, two, LIMB32) || ge32(two, six, LIMB32) == 1) {
        fprintf(stderr, "ge256\n"); fails++;
    }
#if defined(__SIZEOF_INT128__)
    {
        uint64_t a64[4], b64[4], n64[8];
        memset(a, 0, sizeof(a)); memset(b, 0, sizeof(b));
        a[0] = 0xffffffffu; a[1] = 0xffffffffu;
        b[0] = 0xffffffffu; b[1] = 0xfffffffeu;
        mul32(a, b, n);
        u32_to_u64(a, LIMB32, a64, 4);
        u32_to_u64(b, LIMB32, b64, 4);
        mul64(a64, b64, n64);
        if (!limbs64_eq_u32(n64, 8, n, PROD32)) { fprintf(stderr, "32 vs 64 mul\n"); fails++; }
    }
#endif
    if (fails) {
        fprintf(stderr, "selftest FAIL %d\n", fails);
        return 1;
    }
    printf("selftest=PASS int128=%d\n",
#if defined(__SIZEOF_INT128__)
           1
#else
           0
#endif
    );
    (void)eq32;
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: u512_coprocessor_c11 selftest\n"
            "       u512_coprocessor_c11 mul <hex256> <hex256>\n"
            "       u512_coprocessor_c11 ge <hex512> <hex512>\n"
            "       u512_coprocessor_c11 div <hex512> <hex256>\n"
            "       u512_coprocessor_c11 muldiv <hex256> <hex256> <hex256>\n");
}

int main(int argc, char **argv) {
    uint32_t a[LIMB32], b[LIMB32], d[LIMB32], n[PROD32], q[LIMB32], r[LIMB32];
    uint32_t A[PROD32], B[PROD32];
    int st;
    if (argc < 2) { usage(); return 2; }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "mul") == 0 && argc == 4) {
        if (!parse_256(argv[2], a) || !parse_256(argv[3], b)) return 2;
        mul32(a, b, n);
        printf("status=1 n="); emit_512(n); printf("\n");
        return 0;
    }
    if (strcmp(argv[1], "ge") == 0 && argc == 4) {
        if (!parse_512(argv[2], A) || !parse_512(argv[3], B)) return 2;
        printf("ge=%d\n", ge32(A, B, PROD32));
        return 0;
    }
    if (strcmp(argv[1], "div") == 0 && argc == 4) {
        if (!parse_512(argv[2], n) || !parse_256(argv[3], d)) return 2;
        st = div32(n, d, q, r);
        printf("status=%d q=", st); emit_256(q); printf(" r="); emit_256(r); printf("\n");
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc == 5) {
        if (!parse_256(argv[2], a) || !parse_256(argv[3], b) || !parse_256(argv[4], d)) return 2;
        mul32(a, b, n);
        st = div32(n, d, q, r);
        printf("status=%d n=", st); emit_512(n); printf(" q="); emit_256(q); printf(" r="); emit_256(r); printf("\n");
        return 0;
    }
    usage();
    return 2;
}
