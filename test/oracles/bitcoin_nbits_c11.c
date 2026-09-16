/*
 * Independent C11 oracle for Bitcoin Core CalculateNextWorkRequired.
 *
 * Compact nBits uses 8 x uint32 limbs, matching arith_uint256 WIDTH=8.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: bitcoin/bitcoin v27.1 src/pow.cpp + src/arith_uint256.cpp (MIT)
 * Gold vectors: src/test/pow_tests.cpp (MIT)
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIDTH 8
#define MASK32 0xffffffffu
#define MAINNET_TIMESPAN 1209600LL
#define MAINNET_LIMIT_NBITS 0x1d00ffffu

static uint32_t g_pn[WIDTH];

static void zero(uint32_t *p) {
    int i;
    for (i = 0; i < WIDTH; i++) p[i] = 0;
}

static void copy(uint32_t *d, const uint32_t *s) {
    int i;
    for (i = 0; i < WIDTH; i++) d[i] = s[i];
}

static void shl(uint32_t *pn, unsigned int shift) {
    uint32_t a[WIDTH];
    int i, k;
    copy(a, pn);
    zero(pn);
    k = (int)(shift / 32u);
    shift = shift % 32u;
    for (i = 0; i < WIDTH; i++) {
        if (i + k + 1 < WIDTH && shift != 0)
            pn[i + k + 1] |= (a[i] >> (32u - shift));
        if (i + k < WIDTH)
            pn[i + k] |= (a[i] << shift);
    }
}

static void shr(uint32_t *pn, unsigned int shift) {
    uint32_t a[WIDTH];
    int i, k;
    copy(a, pn);
    zero(pn);
    k = (int)(shift / 32u);
    shift = shift % 32u;
    for (i = 0; i < WIDTH; i++) {
        if (i - k - 1 >= 0 && shift != 0)
            pn[i - k - 1] |= (a[i] << (32u - shift));
        if (i - k >= 0)
            pn[i - k] |= (a[i] >> shift);
    }
}

static void mul_u32(uint32_t *pn, uint32_t b32) {
    uint64_t carry = 0;
    int i;
    for (i = 0; i < WIDTH; i++) {
        uint64_t n = carry + (uint64_t)b32 * (uint64_t)pn[i];
        pn[i] = (uint32_t)(n & MASK32);
        carry = n >> 32;
    }
}

static int bits_of(const uint32_t *pn) {
    int pos, nbits;
    for (pos = WIDTH - 1; pos >= 0; pos--) {
        if (pn[pos]) {
            for (nbits = 31; nbits > 0; nbits--) {
                if (pn[pos] & (1u << nbits))
                    return 32 * pos + nbits + 1;
            }
            return 32 * pos + 1;
        }
    }
    return 0;
}

static uint64_t getlow64(const uint32_t *pn) {
    return (uint64_t)pn[0] | ((uint64_t)pn[1] << 32);
}

static int cmp(const uint32_t *a, const uint32_t *b) {
    int i;
    for (i = WIDTH - 1; i >= 0; i--) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
    }
    return 0;
}

static void sub(uint32_t *a, const uint32_t *b) {
    uint64_t borrow = 0;
    int i;
    for (i = 0; i < WIDTH; i++) {
        uint64_t x = a[i];
        uint64_t y = (uint64_t)b[i] + borrow;
        if (x >= y) {
            a[i] = (uint32_t)(x - y);
            borrow = 0;
        } else {
            a[i] = (uint32_t)(x + (1ull << 32) - y);
            borrow = 1;
        }
    }
}

static void setcompact(uint32_t *pn, uint32_t ncompact, int *neg, int *ov) {
    int nsize = (int)(ncompact >> 24);
    uint32_t nword = ncompact & 0x007fffffu;
    zero(pn);
    if (nsize <= 3) {
        nword >>= 8 * (3 - nsize);
        pn[0] = nword;
    } else {
        pn[0] = nword;
        shl(pn, (unsigned)(8 * (nsize - 3)));
    }
    if (neg)
        *neg = (nword != 0 && (ncompact & 0x00800000u) != 0);
    if (ov)
        *ov = (nword != 0 && ((nsize > 34) ||
                              (nword > 0xff && nsize > 33) ||
                              (nword > 0xffff && nsize > 32)));
}

static uint32_t getcompact(const uint32_t *pn) {
    int nsize = (bits_of(pn) + 7) / 8;
    uint32_t ncompact;
    uint32_t tmp[WIDTH];
    if (nsize <= 3) {
        ncompact = (uint32_t)(getlow64(pn) << (8 * (3 - nsize)));
    } else {
        copy(tmp, pn);
        shr(tmp, (unsigned)(8 * (nsize - 3)));
        ncompact = (uint32_t)getlow64(tmp);
    }
    if (ncompact & 0x00800000u) {
        ncompact >>= 8;
        nsize++;
    }
    ncompact &= 0x007fffffu;
    ncompact |= ((uint32_t)nsize) << 24;
    return ncompact;
}

static int div_u256(uint32_t *num, const uint32_t *divn) {
    uint32_t div[WIDTH], quot[WIDTH];
    int num_bits, div_bits, shift;
    copy(div, divn);
    zero(quot);
    num_bits = bits_of(num);
    div_bits = bits_of(div);
    if (div_bits == 0) return 0;
    if (div_bits > num_bits) {
        zero(num);
        return 1;
    }
    shift = num_bits - div_bits;
    shl(div, (unsigned)shift);
    while (shift >= 0) {
        if (cmp(num, div) >= 0) {
            sub(num, div);
            quot[shift / 32] |= (1u << (shift & 31));
        }
        shr(div, 1);
        shift--;
    }
    copy(num, quot);
    return 1;
}

static int64_t timespan_clamp(int64_t actual, int64_t target) {
    int64_t lo, hi;
    if (target <= 0) return 0;
    lo = target / 4;
    hi = target * 4;
    if (actual < lo) actual = lo;
    if (actual > hi) actual = hi;
    return actual;
}

static int compact_negative(uint32_t n) {
    uint32_t w = n & 0x007fffffu;
    return (w != 0 && (n & 0x00800000u) != 0) ? 1 : 0;
}

static int compact_overflow(uint32_t n) {
    int nsize = (int)(n >> 24);
    uint32_t w = n & 0x007fffffu;
    return (w != 0 && ((nsize > 34) || (w > 0xff && nsize > 33) ||
                       (w > 0xffff && nsize > 32)))
               ? 1
               : 0;
}

static uint32_t next_work(uint32_t last_nbits, int64_t last_time, int64_t first_time,
                          int64_t target_timespan, uint32_t pow_limit_nbits,
                          int no_retarget) {
    int64_t actual;
    uint32_t bn[WIDTH], limit[WIDTH], divn[WIDTH];
    if (no_retarget) return last_nbits;
    if (target_timespan <= 0) return 0;
    actual = timespan_clamp(last_time - first_time, target_timespan);
    setcompact(bn, last_nbits, NULL, NULL);
    mul_u32(bn, (uint32_t)actual);
    zero(divn);
    divn[0] = (uint32_t)(target_timespan & MASK32);
    divn[1] = (uint32_t)((uint64_t)target_timespan >> 32);
    if (!div_u256(bn, divn)) return 0;
    setcompact(limit, pow_limit_nbits, NULL, NULL);
    if (cmp(bn, limit) > 0) copy(bn, limit);
    return getcompact(bn);
}

static int compact_ok(uint32_t nbits, uint32_t pow_limit_nbits) {
    int neg = 0, ov = 0;
    uint32_t bn[WIDTH], limit[WIDTH];
    int i, z;
    setcompact(bn, nbits, &neg, &ov);
    if (neg || ov) return 0;
    z = 1;
    for (i = 0; i < WIDTH; i++)
        if (bn[i]) z = 0;
    if (z) return 0;
    setcompact(limit, pow_limit_nbits, NULL, NULL);
    if (cmp(bn, limit) > 0) return 0;
    return 1;
}

static int selftest(void) {
    uint32_t g;
    int fails = 0;
    g = next_work(0x1d00ffffu, 1262152739LL, 1261130161LL, MAINNET_TIMESPAN,
                  MAINNET_LIMIT_NBITS, 0);
    if (g != 0x1d00d86au) {
        printf("FAIL get_next_work got=0x%08x\n", g);
        fails++;
    }
    g = next_work(0x1d00ffffu, 1233061996LL, 1231006505LL, MAINNET_TIMESPAN,
                  MAINNET_LIMIT_NBITS, 0);
    if (g != 0x1d00ffffu) {
        printf("FAIL pow_limit got=0x%08x\n", g);
        fails++;
    }
    g = next_work(0x1c05a3f4u, 1279297671LL, 1279008237LL, MAINNET_TIMESPAN,
                  MAINNET_LIMIT_NBITS, 0);
    if (g != 0x1c0168fdu) {
        printf("FAIL lower_limit got=0x%08x\n", g);
        fails++;
    }
    g = next_work(0x1c387f6fu, 1269211443LL, 1263163443LL, MAINNET_TIMESPAN,
                  MAINNET_LIMIT_NBITS, 0);
    if (g != 0x1d00e1fdu) {
        printf("FAIL upper_limit got=0x%08x\n", g);
        fails++;
    }
    setcompact(g_pn, 0x1d00ffffu, NULL, NULL);
    if (getcompact(g_pn) != 0x1d00ffffu) {
        printf("FAIL roundtrip genesis\n");
        fails++;
    }
    if (compact_overflow((uint32_t)(~0x00800000u)) != 1) {
        printf("FAIL overflow vector\n");
        fails++;
    }
    if (compact_ok(0x1d00ffffu, MAINNET_LIMIT_NBITS) != 1) {
        printf("FAIL compact_ok genesis\n");
        fails++;
    }
    if (compact_ok((uint32_t)(~0x00800000u), MAINNET_LIMIT_NBITS) != 0) {
        printf("FAIL compact_ok overflow\n");
        fails++;
    }
    if (timespan_clamp(100, MAINNET_TIMESPAN) != MAINNET_TIMESPAN / 4) {
        printf("FAIL timespan lower clamp\n");
        fails++;
    }
    if (fails) {
        printf("SELFTEST FAIL %d\n", fails);
        return 1;
    }
    printf("SELFTEST PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint32_t last, limit, out;
    int64_t last_t, first_t, span;
    int no_rt;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | next last_nbits last_time first_time "
                "[timespan] [limit] [no_retarget] | clamp actual target | "
                "ok nbits limit | overflow nbits | negative nbits | roundtrip nbits\n",
                argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "next") == 0 && argc >= 5) {
        last = (uint32_t)strtoul(argv[2], NULL, 0);
        last_t = strtoll(argv[3], NULL, 10);
        first_t = strtoll(argv[4], NULL, 10);
        span = (argc > 5) ? strtoll(argv[5], NULL, 10) : MAINNET_TIMESPAN;
        limit = (argc > 6) ? (uint32_t)strtoul(argv[6], NULL, 0) : MAINNET_LIMIT_NBITS;
        no_rt = (argc > 7) ? (int)strtol(argv[7], NULL, 10) : 0;
        out = next_work(last, last_t, first_t, span, limit, no_rt);
        printf("%" PRIu32 "\n", out);
        return 0;
    }
    if (strcmp(argv[1], "clamp") == 0 && argc == 4) {
        printf("%" PRId64 "\n",
               timespan_clamp(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "ok") == 0 && argc == 4) {
        printf("%d\n", compact_ok((uint32_t)strtoul(argv[2], NULL, 0),
                                  (uint32_t)strtoul(argv[3], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "overflow") == 0 && argc == 3) {
        printf("%d\n", compact_overflow((uint32_t)strtoul(argv[2], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "negative") == 0 && argc == 3) {
        printf("%d\n", compact_negative((uint32_t)strtoul(argv[2], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "roundtrip") == 0 && argc == 3) {
        setcompact(g_pn, (uint32_t)strtoul(argv[2], NULL, 0), NULL, NULL);
        printf("%" PRIu32 "\n", getcompact(g_pn));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
