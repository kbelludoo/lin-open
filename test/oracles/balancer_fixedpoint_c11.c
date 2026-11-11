/*
 * Independent C11 oracle for Balancer V2 FixedPoint (uint64 / i64-positive).
 *
 * Two implementations of (a*b + add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_balancer_fixedpoint.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: balancer/balancer-v2-monorepo
 *   pkg/solidity-utils/contracts/math/FixedPoint.sol
 * Algorithm license: GPL-3.0-or-later (Balancer). This oracle is original C11.
 *
 * Scope: mulDown/mulUp/divDown/divUp/complement. Not powDown/powUp/LogExpMath.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ONE 1000000000000000000ULL
#define HALF 500000000000000000ULL
#define I64MAX 9223372036854775807ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_add_limbs_q(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                               uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, lo2;
    uint64_t bit, ge, need_borrow;
    int i, ov;

    if (d == 0) {
        *q_out = 0;
        *r_out = 0;
        *ov_out = 1;
        return;
    }
    a0 = a & 0xffffffffULL;
    a1 = a >> 32;
    b0 = b & 0xffffffffULL;
    b1 = b >> 32;
    p0 = a0 * b0;
    p1 = a0 * b1;
    p2 = a1 * b0;
    p3 = a1 * b1;
    mid = p1 + p2;
    mid_carry = (mid < p1) ? 1 : 0;
    t = (mid & 0xffffffffULL) << 32;
    lo = p0 + t;
    lo_carry = (lo < p0) ? 1 : 0;
    hi = p3 + (mid >> 32);
    hi = hi + (mid_carry << 32);
    hi = hi + lo_carry;
    lo2 = lo + add;
    hi = hi + ((lo2 < lo) ? 1 : 0);
    lo = lo2;

    r_hi = 0;
    r_lo = 0;
    q = 0;
    ov = 0;
    for (i = 127; i >= 0; i--) {
        bit = (i >= 64) ? ((hi >> (i - 64)) & 1ULL) : ((lo >> i) & 1ULL);
        new_hi = (r_hi << 1) | (r_lo >> 63);
        new_lo = (r_lo << 1) | bit;
        r_hi = new_hi;
        r_lo = new_lo;
        ge = (r_hi != 0) || (r_lo >= d);
        if (ge) {
            need_borrow = u_lt(r_lo, d);
            r_lo = r_lo - d;
            if (need_borrow) r_hi = r_hi - 1;
            if (i >= 64) ov = 1;
            if (i < 64) q = q | (1ULL << i);
        }
    }
    if (ov || q > I64MAX) {
        *q_out = 0;
        *r_out = r_lo;
        *ov_out = 1;
        return;
    }
    *q_out = q;
    *r_out = r_lo;
    *ov_out = 0;
}

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t n, q;
    if (d == 0) return 0;
    n = (__uint128_t)a * (__uint128_t)b + (__uint128_t)add;
    q = n / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_add_limbs_q(a, b, add, d, &q, &r, &ov);
    return q;
}

static uint64_t ceil_from_qr(uint64_t q, uint64_t r, int ov) {
    uint64_t s;
    if (ov) return 0;
    if (r == 0) return q;
    s = q + 1ULL;
    if (s < q || s > I64MAX) return 0;
    return s;
}

static uint64_t mul_down(uint64_t a, uint64_t b,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    return md(a, b, 0, ONE);
}

static uint64_t mul_up_i128(uint64_t a, uint64_t b) {
    __uint128_t n, q, r;
    if (a == 0 || b == 0) return 0;
    n = (__uint128_t)a * (__uint128_t)b;
    q = n / (__uint128_t)ONE;
    r = n % (__uint128_t)ONE;
    if (q > I64MAX) return 0;
    return ceil_from_qr((uint64_t)q, (uint64_t)r, 0);
}

static uint64_t mul_up_limbs(uint64_t a, uint64_t b) {
    uint64_t q, r;
    int ov;
    if (a == 0 || b == 0) return 0;
    muldiv_add_limbs_q(a, b, 0, ONE, &q, &r, &ov);
    return ceil_from_qr(q, r, ov);
}

static uint64_t div_down(uint64_t a, uint64_t b,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, ONE, 0, b);
}

static uint64_t div_up_i128(uint64_t a, uint64_t b) {
    __uint128_t n, q, r;
    if (b == 0 || a == 0) return 0;
    n = (__uint128_t)a * (__uint128_t)ONE;
    q = n / (__uint128_t)b;
    r = n % (__uint128_t)b;
    if (q > I64MAX) return 0;
    return ceil_from_qr((uint64_t)q, (uint64_t)r, 0);
}

static uint64_t div_up_limbs(uint64_t a, uint64_t b) {
    uint64_t q, r;
    int ov;
    if (b == 0 || a == 0) return 0;
    muldiv_add_limbs_q(a, ONE, 0, b, &q, &r, &ov);
    return ceil_from_qr(q, r, ov);
}

static uint64_t halfup_mul(uint64_t a, uint64_t b,
                           uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    return md(a, b, HALF, ONE);
}

static uint64_t halfup_div(uint64_t a, uint64_t b,
                           uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, ONE, b / 2, b);
}

static uint64_t complement(uint64_t x) { return (x < ONE) ? (ONE - x) : 0; }

static int selftest(void) {
    int fail = 0;
    uint64_t (*md_i)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_i128;
    uint64_t (*md_l)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_limbs;
    uint64_t o = ONE;
    uint64_t h = HALF;
    uint64_t w = 3000000000000000000ULL;
    uint64_t a, b;

    if (mul_down(o, o, md_i) != o) fail++;
    if (mul_down(o, o, md_l) != o) fail++;
    if (mul_down(3, h, md_i) != 1) fail++;
    if (mul_down(3, h, md_l) != 1) fail++;
    if (mul_up_i128(3, h) != 2) fail++;
    if (mul_up_limbs(3, h) != 2) fail++;
    if (halfup_mul(3, h, md_i) != 2) fail++;
    if (mul_down(1, 1, md_i) != 0) fail++;
    if (mul_up_i128(1, 1) != 1) fail++;
    if (mul_up_limbs(1, 1) != 1) fail++;
    if (div_down(1, 3, md_i) != 333333333333333333ULL) fail++;
    if (div_up_i128(1, 3) != 333333333333333334ULL) fail++;
    if (div_up_limbs(1, 3) != 333333333333333334ULL) fail++;
    if (halfup_div(1, 3, md_i) != 333333333333333333ULL) fail++;
    if (mul_down(w, w, md_i) != 9000000000000000000ULL) fail++;
    if (mul_down(w, w, md_l) != 9000000000000000000ULL) fail++;
    if (mul_down(4000000000000000000ULL, w, md_i) != 0) fail++;
    if (mul_up_i128(4000000000000000000ULL, w) != 0) fail++;
    if (complement(100000000000000000ULL) != 900000000000000000ULL) fail++;
    if (complement(o) != 0) fail++;
    a = 123456789ULL;
    b = 2500ULL;
    if (mul_down(a, b, md_i) != mul_down(a, b, md_l)) fail++;
    if (mul_up_i128(a, b) != mul_up_limbs(a, b)) fail++;
    if (div_down(a, b, md_i) != div_down(a, b, md_l)) fail++;
    if (div_up_i128(a, b) != div_up_limbs(a, b)) fail++;

    if (fail) {
        fprintf(stderr, "balancer_fixedpoint_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("balancer_fixedpoint_c11 selftest PASS\n");
    printf("vector.mul_down_3=%" PRIu64 "\n", mul_down(3, h, md_i));
    printf("vector.mul_up_3=%" PRIu64 "\n", mul_up_i128(3, h));
    printf("vector.div_up_1_3=%" PRIu64 "\n", div_up_i128(1, 3));
    printf("vector.halfup_div_1_3=%" PRIu64 "\n", halfup_div(1, 3, md_i));
    printf("vector.wide=%" PRIu64 "\n", mul_down(w, w, md_i));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_i128;
    int limbs = 0;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldown a b | mulup a b | divdown a b | divup a b | halfup_mul a b | halfup_div a b | complement x\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muldiv_add_limbs;
        limbs = 1;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldown") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               mul_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "mulup") == 0 && argc == 4) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n", limbs ? mul_up_limbs(a, b) : mul_up_i128(a, b));
        return 0;
    }
    if (strcmp(cmd, "divdown") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               div_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "divup") == 0 && argc == 4) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n", limbs ? div_up_limbs(a, b) : div_up_i128(a, b));
        return 0;
    }
    if (strcmp(cmd, "halfup_mul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               halfup_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "halfup_div") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               halfup_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "complement") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", complement(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
