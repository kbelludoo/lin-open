/*
 * Independent C11 oracle for Bitcoin Core GetBlockProof / SetCompact.
 *
 * Implements arith_uint256::SetCompact + GetBlockProof from bitcoin/bitcoin
 * v27.1 (MIT) on eight uint32 limbs, matching src/lin_bitcoin_blockproof.lin.
 * A second path reconstructs the 256-bit integers as hex and is checked by
 * the Python harness via arbitrary-precision int (2**256 // (target+1)).
 *
 * This file is not linked into the LIN compiler TCB.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void zero8(uint32_t p[8]) {
    int i;
    for (i = 0; i < 8; i++) p[i] = 0;
}

static int nsize(uint32_t n) { return (int)((n >> 24) & 255u); }
static uint32_t nword(uint32_t n) { return n & 0x007fffffu; }

static int compact_overflow(uint32_t n) {
    uint32_t w = nword(n);
    int s = nsize(n);
    if (w == 0) return 0;
    if (s > 34) return 1;
    if (w > 0xffu && s > 33) return 1;
    if (w > 0xffffu && s > 32) return 1;
    return 0;
}

static int compact_negative(uint32_t n) {
    uint32_t w = nword(n);
    if (w == 0) return 0;
    return (n & 0x00800000u) != 0;
}

static void set_compact(uint32_t n, uint32_t t[8], int *neg, int *ovf) {
    uint32_t w = nword(n);
    int s = nsize(n);
    unsigned sh, off, bit;
    zero8(t);
    *neg = compact_negative(n);
    *ovf = compact_overflow(n);
    if (*ovf) return;
    if (s <= 3) {
        t[0] = w >> (8 * (3 - s));
        return;
    }
    sh = (unsigned)(8 * (s - 3));
    off = sh / 32;
    bit = sh % 32;
    if (off < 8)
        t[off] = (uint32_t)(((uint64_t)w << bit) & 0xffffffffull);
    if (bit != 0 && off + 1 < 8)
        t[off + 1] = w >> (32 - bit);
}

static int is_zero(const uint32_t p[8]) {
    int i;
    for (i = 0; i < 8; i++) if (p[i]) return 0;
    return 1;
}

static int ge256(const uint32_t a[8], const uint32_t b[8]) {
    int i;
    for (i = 7; i >= 0; i--) {
        if (a[i] > b[i]) return 1;
        if (a[i] < b[i]) return 0;
    }
    return 1;
}

static void add1(uint32_t p[8]) {
    uint64_t c = 1;
    int i;
    for (i = 0; i < 8; i++) {
        uint64_t s = (uint64_t)p[i] + c;
        p[i] = (uint32_t)(s & 0xffffffffull);
        c = s >> 32;
    }
}

static void get_block_proof(uint32_t nbits, uint32_t q[8]) {
    uint32_t t[8], d[8], r[9], tb;
    int neg, ovf, i, li, bi, ge, b;
    uint64_t x, c;
    zero8(q);
    set_compact(nbits, t, &neg, &ovf);
    if (neg || ovf || is_zero(t)) return;
    memcpy(d, t, sizeof d);
    add1(d);
    memset(r, 0, sizeof r);
    for (i = 255; i >= 0; i--) {
        c = 0;
        for (b = 0; b < 8; b++) {
            x = ((uint64_t)r[b] << 1) + c;
            r[b] = (uint32_t)(x & 0xffffffffull);
            c = x >> 32;
        }
        r[8] = (uint32_t)c;
        li = i >> 5;
        bi = i & 31;
        tb = (t[li] >> bi) & 1u;
        r[0] |= (1u - tb);
        ge = r[8] ? 1 : ge256(r, d);
        if (ge) {
            uint32_t bo = 0;
            for (b = 0; b < 8; b++) {
                uint64_t sub = (uint64_t)d[b] + bo;
                if ((uint64_t)r[b] < sub) {
                    r[b] = (uint32_t)(((uint64_t)r[b] + 0x100000000ull) - sub);
                    bo = 1;
                } else {
                    r[b] = (uint32_t)((uint64_t)r[b] - sub);
                    bo = 0;
                }
            }
            r[8] = 0;
            q[li] |= (1u << bi);
        }
    }
    add1(q);
}

static int hex_eq(const uint32_t p[8], const char *hex64) {
    char buf[65];
    int i;
    for (i = 7; i >= 0; i--) sprintf(buf + (7 - i) * 8, "%08x", p[i]);
    buf[64] = 0;
    return strcmp(buf, hex64) == 0;
}

static int selftest(void) {
    uint32_t t[8], w[8];
    int neg, ovf, fail = 0;
    set_compact(0x03123456u, t, &neg, &ovf);
    if (neg || ovf || !hex_eq(t, "0000000000000000000000000000000000000000000000000000000000123456")) fail++;
    set_compact(0x04123456u, t, &neg, &ovf);
    if (neg || ovf || !hex_eq(t, "0000000000000000000000000000000000000000000000000000000012345600")) fail++;
    set_compact(0x01123456u, t, &neg, &ovf);
    if (neg || ovf || !hex_eq(t, "0000000000000000000000000000000000000000000000000000000000000012")) fail++;
    set_compact(0x20123456u, t, &neg, &ovf);
    if (neg || ovf || !hex_eq(t, "1234560000000000000000000000000000000000000000000000000000000000")) fail++;
    set_compact(0xff123456u, t, &neg, &ovf);
    if (!ovf) fail++;
    set_compact(0x01fedcbau, t, &neg, &ovf);
    if (!neg || ovf || !hex_eq(t, "000000000000000000000000000000000000000000000000000000000000007e")) fail++;
    set_compact(0x1d00ffffu, t, &neg, &ovf);
    if (neg || ovf || !hex_eq(t, "00000000ffff0000000000000000000000000000000000000000000000000000")) fail++;
    get_block_proof(0x20123456u, w);
    if (w[0] != 14u || w[1] != 0) fail++;
    get_block_proof(0x1d00ffffu, w);
    if (w[0] != 0x10001u || w[1] != 1u) fail++;
    get_block_proof(0x04923456u, w);
    if (w[0] != 0) fail++;
    if (fail) {
        printf("SELFTEST FAIL %d\n", fail);
        return 1;
    }
    printf("SELFTEST PASS\n");
    return 0;
}

static void print8(const uint32_t p[8]) {
    int i;
    for (i = 0; i < 8; i++) {
        if (i) putchar(' ');
        printf("%u", p[i]);
    }
    putchar('\n');
}

int main(int argc, char **argv) {
    uint32_t n, t[8], w[8];
    int neg, ovf, limb;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | flags N | target N | work N | limb N I\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 3) return 2;
    n = (uint32_t)strtoul(argv[2], NULL, 0);
    if (strcmp(argv[1], "flags") == 0) {
        set_compact(n, t, &neg, &ovf);
        printf("neg=%d ovf=%d zero=%d\n", neg, ovf, is_zero(t));
        return 0;
    }
    if (strcmp(argv[1], "target") == 0) {
        set_compact(n, t, &neg, &ovf);
        print8(t);
        return 0;
    }
    if (strcmp(argv[1], "work") == 0) {
        get_block_proof(n, w);
        print8(w);
        return 0;
    }
    if (strcmp(argv[1], "limb") == 0 && argc >= 4) {
        limb = atoi(argv[3]);
        get_block_proof(n, w);
        if (limb < 0 || limb > 7) return 2;
        printf("%u\n", w[limb]);
        return 0;
    }
    return 2;
}
