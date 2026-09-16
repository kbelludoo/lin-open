/*
 * Independent C11 oracle for 256x256->512 mulDiv (not in the LIN TCB).
 *
 * Two implementations that must agree:
 *   1. 16-bit schoolbook limbs (same width as src/lin_u512_coprocessor.lin)
 *   2. 64-bit schoolbook using unsigned __int128 for limb products
 *
 * Python int is the third oracle (test/prove_u512_coprocessor_external.py).
 * Class: EXPERIMENTAL. This is FullMath *width* (512-bit product), not
 * CRT/mulmod assembly and not a deployed pool.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define U16MASK 65535u
#define N16 16
#define N32 32
#define RAND_N 520

typedef struct {
    int status; /* 1, -1 d=0, -2 q overflow */
    uint64_t q[4];
    uint64_t r[4];
    uint64_t n[8];
} U512Md;

static void words_from_u256(uint64_t w[4], const uint16_t x[16]) {
    int i;
    for (i = 0; i < 4; i++) {
        w[i] = (uint64_t)(x[i * 4] & U16MASK)
             | ((uint64_t)(x[i * 4 + 1] & U16MASK) << 16)
             | ((uint64_t)(x[i * 4 + 2] & U16MASK) << 32)
             | ((uint64_t)(x[i * 4 + 3] & U16MASK) << 48);
    }
}

static void limbs_from_u256(uint16_t x[16], const uint64_t w[4]) {
    int i, k;
    for (i = 0; i < 4; i++) {
        for (k = 0; k < 4; k++) {
            x[i * 4 + k] = (uint16_t)((w[i] >> (16 * k)) & U16MASK);
        }
    }
}

static int is_zero256(const uint64_t w[4]) {
    return (w[0] | w[1] | w[2] | w[3]) == 0;
}

static void mul16(uint16_t n[32], const uint16_t a[16], const uint16_t b[16]) {
    int i, j, k;
    uint32_t carry, t;
    memset(n, 0, 32 * sizeof(uint16_t));
    for (i = 0; i < 16; i++) {
        carry = 0;
        for (j = 0; j < 16; j++) {
            k = i + j;
            t = (uint32_t)n[k] + (uint32_t)a[i] * (uint32_t)b[j] + carry;
            n[k] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
        }
        k = i + 16;
        while (k < 32 && carry != 0) {
            t = (uint32_t)n[k] + carry;
            n[k] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
            k++;
        }
    }
}

static int ge16_n_vs_d(const uint16_t n[32], const uint16_t d[16]) {
    int j;
    uint16_t dj;
    for (j = 31; j >= 0; j--) {
        dj = (j < 16) ? d[j] : 0;
        if (n[j] > dj) return 1;
        if (n[j] < dj) return 0;
    }
    return 1;
}

static void muldiv16(U512Md *out, const uint64_t aw[4], const uint64_t bw[4],
                     const uint64_t dw[4]) {
    uint16_t a[16], b[16], d[16], n[32], rem[32], q[16];
    int bit, limb, pos, j, take, cmp;
    uint32_t carry, t;
    int32_t st;
    uint16_t dj;
    int32_t borrow;

    memset(out, 0, sizeof(*out));
    limbs_from_u256(a, aw);
    limbs_from_u256(b, bw);
    limbs_from_u256(d, dw);
    mul16(n, a, b);
    for (j = 0; j < 8; j++) {
        int base = j * 4;
        out->n[j] = (uint64_t)(n[base] & U16MASK)
                  | ((uint64_t)(n[base + 1] & U16MASK) << 16)
                  | ((uint64_t)(n[base + 2] & U16MASK) << 32)
                  | ((uint64_t)(n[base + 3] & U16MASK) << 48);
    }
    if (is_zero256(dw)) {
        out->status = -1;
        return;
    }
    memset(rem, 0, sizeof(rem));
    memset(q, 0, sizeof(q));
    for (bit = 511; bit >= 0; bit--) {
        limb = bit >> 4;
        pos = bit & 15;
        carry = (uint32_t)((n[limb] >> pos) & 1);
        for (j = 0; j < 32; j++) {
            t = (uint32_t)rem[j] * 2u + carry;
            rem[j] = (uint16_t)(t & U16MASK);
            carry = t >> 16;
        }
        cmp = 0;
        for (j = 31; j >= 0; j--) {
            dj = (j < 16) ? d[j] : 0;
            if (cmp == 0) {
                if (rem[j] > dj) cmp = 1;
                else if (rem[j] < dj) cmp = -1;
            }
        }
        take = (carry == 1) || (cmp >= 0);
        if (!take) continue;
        if (bit >= 256) {
            out->status = -2;
            memset(out->q, 0, sizeof(out->q));
            memset(out->r, 0, sizeof(out->r));
            return;
        }
        q[limb] = (uint16_t)(q[limb] | (uint16_t)(1u << pos));
        borrow = 0;
        for (j = 0; j < 32; j++) {
            dj = (j < 16) ? d[j] : 0;
            st = (int32_t)rem[j] - (int32_t)dj - borrow;
            if (st < 0) {
                rem[j] = (uint16_t)(st + 65536);
                borrow = 1;
            } else {
                rem[j] = (uint16_t)st;
                borrow = 0;
            }
        }
    }
    out->status = 1;
    words_from_u256(out->q, q);
    words_from_u256(out->r, rem);
}

static void mul64(uint64_t n[8], const uint64_t a[4], const uint64_t b[4]) {
    int i, j, k;
    unsigned __int128 carry, t;
    memset(n, 0, 8 * sizeof(uint64_t));
    for (i = 0; i < 4; i++) {
        carry = 0;
        for (j = 0; j < 4; j++) {
            t = (unsigned __int128)n[i + j]
              + (unsigned __int128)a[i] * b[j]
              + carry;
            n[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        k = i + 4;
        while (k < 8 && carry != 0) {
            t = (unsigned __int128)n[k] + carry;
            n[k] = (uint64_t)t;
            carry = t >> 64;
            k++;
        }
    }
}

static void muldiv64(U512Md *out, const uint64_t aw[4], const uint64_t bw[4],
                     const uint64_t dw[4]) {
    uint64_t n[8], rem[8], q[4];
    int bit, limb, pos, j, take, cmp;
    uint64_t inbit, c, newc, dj;
    int borrow;

    memset(out, 0, sizeof(*out));
    mul64(n, aw, bw);
    memcpy(out->n, n, sizeof(n));
    if (is_zero256(dw)) {
        out->status = -1;
        return;
    }
    memset(rem, 0, sizeof(rem));
    memset(q, 0, sizeof(q));
    for (bit = 511; bit >= 0; bit--) {
        limb = bit / 64;
        pos = bit % 64;
        inbit = (n[limb] >> pos) & 1ull;
        c = inbit;
        for (j = 0; j < 8; j++) {
            newc = rem[j] >> 63;
            rem[j] = (rem[j] << 1) | c;
            c = newc;
        }
        cmp = 0;
        for (j = 7; j >= 0; j--) {
            dj = (j < 4) ? dw[j] : 0;
            if (cmp == 0) {
                if (rem[j] > dj) cmp = 1;
                else if (rem[j] < dj) cmp = -1;
            }
        }
        take = (c == 1) || (cmp >= 0);
        if (!take) continue;
        if (bit >= 256) {
            out->status = -2;
            memset(out->q, 0, sizeof(out->q));
            memset(out->r, 0, sizeof(out->r));
            return;
        }
        q[limb] |= (1ull << pos);
        borrow = 0;
        for (j = 0; j < 8; j++) {
            unsigned __int128 acc, dec;
            dj = (j < 4) ? dw[j] : 0;
            acc = rem[j];
            dec = (unsigned __int128)dj + (unsigned)borrow;
            if (acc < dec) {
                rem[j] = (uint64_t)(acc + ((unsigned __int128)1 << 64) - dec);
                borrow = 1;
            } else {
                rem[j] = (uint64_t)(acc - dec);
                borrow = 0;
            }
        }
    }
    out->status = 1;
    memcpy(out->q, q, sizeof(q));
    memcpy(out->r, rem, 4 * sizeof(uint64_t));
}

static int md_eq(const U512Md *x, const U512Md *y) {
    return x->status == y->status
        && memcmp(x->q, y->q, sizeof(x->q)) == 0
        && memcmp(x->r, y->r, sizeof(x->r)) == 0
        && memcmp(x->n, y->n, sizeof(x->n)) == 0;
}

static uint64_t splitmix(uint64_t *s) {
    uint64_t z = (*s += 0x9e3779b97f4a7c15ull);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

static void rand_u256(uint64_t *s, uint64_t w[4]) {
    int i;
    for (i = 0; i < 4; i++) w[i] = splitmix(s);
}

static void print_md(const U512Md *m) {
    printf("status=%d q0=%" PRIu64 " q1=%" PRIu64 " q2=%" PRIu64 " q3=%" PRIu64
           " r0=%" PRIu64 " r1=%" PRIu64 " r2=%" PRIu64 " r3=%" PRIu64
           " n0=%" PRIu64 " n1=%" PRIu64 " n2=%" PRIu64 " n3=%" PRIu64
           " n4=%" PRIu64 " n5=%" PRIu64 " n6=%" PRIu64 " n7=%" PRIu64 "\n",
           m->status, m->q[0], m->q[1], m->q[2], m->q[3],
           m->r[0], m->r[1], m->r[2], m->r[3],
           m->n[0], m->n[1], m->n[2], m->n[3],
           m->n[4], m->n[5], m->n[6], m->n[7]);
}

static int selftest(void) {
    U512Md a, b;
    uint64_t aw[4], bw[4], dw[4];
    uint64_t seed;
    int i, fail = 0;
    uint16_t al[16], bl[16], dl[16], nl[32];

    memset(aw, 0, sizeof(aw)); memset(bw, 0, sizeof(bw)); memset(dw, 0, sizeof(dw));
    aw[0] = 7; bw[0] = 9; dw[0] = 2;
    muldiv16(&a, aw, bw, dw);
    muldiv64(&b, aw, bw, dw);
    if (!md_eq(&a, &b) || a.status != 1 || a.q[0] != 31 || a.r[0] != 1) fail++;

    dw[0] = 0;
    muldiv16(&a, aw, bw, dw);
    muldiv64(&b, aw, bw, dw);
    if (!md_eq(&a, &b) || a.status != -1) fail++;

    memset(aw, 0xff, sizeof(aw));
    memset(bw, 0xff, sizeof(bw));
    memset(dw, 0, sizeof(dw)); dw[0] = 1;
    muldiv16(&a, aw, bw, dw);
    muldiv64(&b, aw, bw, dw);
    if (!md_eq(&a, &b) || a.status != -2) fail++;

    memset(aw, 0, sizeof(aw)); memset(bw, 0, sizeof(bw)); memset(dw, 0, sizeof(dw));
    aw[3] = 1ull << 63; /* 2^255 */
    bw[0] = 2;
    dw[0] = 3;
    muldiv16(&a, aw, bw, dw);
    muldiv64(&b, aw, bw, dw);
    if (!md_eq(&a, &b) || a.status != 1) fail++;
    if (a.q[0] != 0x5555555555555555ull || a.q[1] != 0x5555555555555555ull
        || a.q[2] != 0x5555555555555555ull || a.q[3] != 0x5555555555555555ull) fail++;
    if (a.r[0] != 1 || a.r[1] | a.r[2] | a.r[3]) fail++;

    memset(aw, 0, sizeof(aw)); memset(bw, 0, sizeof(bw)); memset(dw, 0, sizeof(dw));
    aw[0] = 3; bw[0] = 3; dw[0] = 10;
    limbs_from_u256(al, aw); limbs_from_u256(bl, bw); limbs_from_u256(dl, dw);
    mul16(nl, al, bl);
    if (ge16_n_vs_d(nl, dl) != 0) fail++;
    bw[0] = 4; dw[0] = 12;
    limbs_from_u256(bl, bw); limbs_from_u256(dl, dw);
    mul16(nl, al, bl);
    if (ge16_n_vs_d(nl, dl) != 1) fail++;

    seed = 20260916ull;
    for (i = 0; i < RAND_N; i++) {
        rand_u256(&seed, aw);
        rand_u256(&seed, bw);
        rand_u256(&seed, dw);
        if ((i % 17) == 0) memset(dw, 0, sizeof(dw));
        if ((i % 29) == 0) { memset(aw, 0xff, sizeof(aw)); memset(bw, 0xff, sizeof(bw)); dw[0] = 1; dw[1]=dw[2]=dw[3]=0; }
        muldiv16(&a, aw, bw, dw);
        muldiv64(&b, aw, bw, dw);
        if (!md_eq(&a, &b)) fail++;
    }
    if (fail) {
        printf("SELFTEST FAIL count=%d\n", fail);
        return 1;
    }
    printf("SELFTEST PASS n=%d limb16==limb64 2^255*2/3 q=0x5555.. r=1\n", RAND_N);
    return 0;
}

int main(int argc, char **argv) {
    U512Md m16, m64;
    uint64_t aw[4], bw[4], dw[4];
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest|muldiv a0 a1 a2 a3 b0 b1 b2 b3 d0 d1 d2 d3|ge a0.. d3\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0) {
        if (argc != 14) { fprintf(stderr, "muldiv needs 12 words\n"); return 2; }
        aw[0]=strtoull(argv[2],0,10); aw[1]=strtoull(argv[3],0,10);
        aw[2]=strtoull(argv[4],0,10); aw[3]=strtoull(argv[5],0,10);
        bw[0]=strtoull(argv[6],0,10); bw[1]=strtoull(argv[7],0,10);
        bw[2]=strtoull(argv[8],0,10); bw[3]=strtoull(argv[9],0,10);
        dw[0]=strtoull(argv[10],0,10); dw[1]=strtoull(argv[11],0,10);
        dw[2]=strtoull(argv[12],0,10); dw[3]=strtoull(argv[13],0,10);
        muldiv16(&m16, aw, bw, dw);
        muldiv64(&m64, aw, bw, dw);
        if (!md_eq(&m16, &m64)) { printf("DIVERGE\n"); print_md(&m16); print_md(&m64); return 1; }
        print_md(&m16);
        return 0;
    }
    if (strcmp(argv[1], "ge") == 0) {
        uint16_t al[16], bl[16], dl[16], nl[32];
        int g;
        if (argc != 14) return 2;
        aw[0]=strtoull(argv[2],0,10); aw[1]=strtoull(argv[3],0,10);
        aw[2]=strtoull(argv[4],0,10); aw[3]=strtoull(argv[5],0,10);
        bw[0]=strtoull(argv[6],0,10); bw[1]=strtoull(argv[7],0,10);
        bw[2]=strtoull(argv[8],0,10); bw[3]=strtoull(argv[9],0,10);
        dw[0]=strtoull(argv[10],0,10); dw[1]=strtoull(argv[11],0,10);
        dw[2]=strtoull(argv[12],0,10); dw[3]=strtoull(argv[13],0,10);
        limbs_from_u256(al, aw); limbs_from_u256(bl, bw); limbs_from_u256(dl, dw);
        mul16(nl, al, bl);
        g = ge16_n_vs_d(nl, dl);
        printf("ge=%d\n", g);
        return 0;
    }
    fprintf(stderr, "unknown cmd\n");
    return 2;
}
