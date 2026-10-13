/*
 * Independent C11 oracle for GMX V2 getBorrowingFactorPerSecond
 * (uint64 scale). (a*b)/d uses unsigned __int128 AND a portable 32-bit
 * limb muldiv that mirrors src/lin_gmx_v2_borrow_fps.lin. Consensus is
 * required before any LIN comparison. This file is not linked into the
 * LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/market/MarketUtils.sol getBorrowingFactorPerSecond
 *   getKinkBorrowingFactor / getUsageFactor
 *   getNextCumulativeBorrowingFactor (delta = duration * fps)
 *   contracts/utils/Precision.sol applyFactor / toFactor
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (FLOAT' = 1e6; exponent/pow skipped as identity):
 *   reserved==0 -> 0
 *   skipBorrowingFeeForSmallerSide && this side OI < other -> 0
 *     equal OI still charges both
 *   pool==0 -> fail-closed 0 (Solidity reverts)
 *   opt!=0 -> kink: apply(usage, base) + (above>base ? above-base : 0)
 *             * (usage-opt) / (FLOAT-opt)     // raw, not applyFactor
 *   else linear: apply(toFactor(reserved, pool), borrowingFactor)
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FLOAT_P 1000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
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
            else q |= (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return q;
}

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d);
}

struct In {
    uint64_t reserved, pool, long_oi, short_oi, skip, opt, rfactor, factor, base,
        above;
    int is_long;
};

static uint64_t apply_u(uint64_t v, uint64_t f, int use_limbs) {
    return md(v, f, FLOAT_P, use_limbs);
}

static uint64_t tofactor_u(uint64_t v, uint64_t d, int use_limbs) {
    if (d == 0) return 0;
    return md(v, FLOAT_P, d, use_limbs);
}

static uint64_t usage_u(uint64_t reserved, uint64_t pool, uint64_t rfactor,
                        int use_limbs) {
    uint64_t maxr = apply_u(pool, rfactor, use_limbs);
    if (maxr == 0) return 0;
    return tofactor_u(reserved, maxr, use_limbs);
}

static int skip_charge_u(int is_long, uint64_t long_oi, uint64_t short_oi,
                         uint64_t skip) {
    if (skip == 0) return 1;
    if (is_long) return !(long_oi < short_oi);
    return !(short_oi < long_oi);
}

static uint64_t kink_u(uint64_t usage, uint64_t opt, uint64_t base,
                       uint64_t above, int use_limbs) {
    uint64_t fps = apply_u(usage, base, use_limbs);
    uint64_t add, den;
    if (usage > opt && FLOAT_P > opt) {
        add = (above > base) ? (above - base) : 0;
        den = FLOAT_P - opt;
        if (den == 0) return fps;
        fps += md(add, usage - opt, den, use_limbs);
    }
    return fps;
}

static uint64_t linear_u(uint64_t reserved, uint64_t pool, uint64_t factor,
                         int use_limbs) {
    if (pool == 0) return 0;
    return apply_u(tofactor_u(reserved, pool, use_limbs), factor, use_limbs);
}

static int ok_u(uint64_t reserved, uint64_t pool) {
    if (reserved == 0) return 1;
    if (pool == 0) return 0;
    return 1;
}

static uint64_t fps_u(struct In p, int use_limbs) {
    if (p.reserved == 0) return 0;
    if (!skip_charge_u(p.is_long, p.long_oi, p.short_oi, p.skip)) return 0;
    if (p.pool == 0) return 0;
    if (p.opt != 0)
        return kink_u(usage_u(p.reserved, p.pool, p.rfactor, use_limbs), p.opt,
                      p.base, p.above, use_limbs);
    return linear_u(p.reserved, p.pool, p.factor, use_limbs);
}

static uint64_t wrong_linear_u(struct In p, int use_limbs) {
    if (p.reserved == 0) return 0;
    if (!skip_charge_u(p.is_long, p.long_oi, p.short_oi, p.skip)) return 0;
    if (p.pool == 0) return 0;
    return linear_u(p.reserved, p.pool, p.factor, use_limbs);
}

static uint64_t wrong_kink_apply_u(struct In p, int use_limbs) {
    uint64_t usage, fps, add;
    if (p.reserved == 0) return 0;
    if (!skip_charge_u(p.is_long, p.long_oi, p.short_oi, p.skip)) return 0;
    if (p.pool == 0) return 0;
    usage = usage_u(p.reserved, p.pool, p.rfactor, use_limbs);
    fps = apply_u(usage, p.base, use_limbs);
    if (usage > p.opt && FLOAT_P > p.opt) {
        add = (p.above > p.base) ? (p.above - p.base) : 0;
        fps += apply_u(usage - p.opt, add, use_limbs);
    }
    return fps;
}

static uint64_t wrong_no_rfactor_u(struct In p, int use_limbs) {
    if (p.reserved == 0) return 0;
    if (!skip_charge_u(p.is_long, p.long_oi, p.short_oi, p.skip)) return 0;
    if (p.pool == 0) return 0;
    return kink_u(tofactor_u(p.reserved, p.pool, use_limbs), p.opt, p.base,
                  p.above, use_limbs);
}

static int64_t wrong_add_neg_u(struct In p, int use_limbs) {
    uint64_t usage;
    int64_t fps, den;
    if (p.reserved == 0) return 0;
    if (p.pool == 0) return 0;
    usage = usage_u(p.reserved, p.pool, p.rfactor, use_limbs);
    fps = (int64_t)apply_u(usage, p.base, use_limbs);
    if (usage > p.opt) {
        den = (int64_t)FLOAT_P - (int64_t)p.opt;
        if (den == 0) return fps;
        fps += ((int64_t)p.above - (int64_t)p.base) *
               ((int64_t)usage - (int64_t)p.opt) / den;
    }
    return fps;
}

static uint64_t delta_u(uint64_t fps, uint64_t duration, int use_limbs) {
    return md(fps, duration, 1, use_limbs);
}

static uint64_t wrong_delta_apply_u(uint64_t fps, uint64_t duration,
                                    int use_limbs) {
    return apply_u(duration, fps, use_limbs);
}

static uint64_t v1_interval_u(uint64_t fps, uint64_t duration, uint64_t interval,
                             int use_limbs) {
    if (interval == 0) return 0;
    return md(fps, duration / interval, 1, use_limbs);
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static struct In parse11(char **argv) {
    struct In p;
    p.reserved = (uint64_t)atoll(argv[2]);
    p.pool = (uint64_t)atoll(argv[3]);
    p.is_long = (int)atoll(argv[4]);
    p.long_oi = (uint64_t)atoll(argv[5]);
    p.short_oi = (uint64_t)atoll(argv[6]);
    p.skip = (uint64_t)atoll(argv[7]);
    p.opt = (uint64_t)atoll(argv[8]);
    p.rfactor = (uint64_t)atoll(argv[9]);
    p.factor = (uint64_t)atoll(argv[10]);
    p.base = (uint64_t)atoll(argv[11]);
    p.above = (uint64_t)atoll(argv[12]);
    return p;
}

static int selftest(void) {
    struct In a;
    int limb;
    for (limb = 0; limb < 2; limb++) {
        if (md(100, 200, 50, limb) != 400) return 1;
        memset(&a, 0, sizeof(a));
        a.reserved = 500000; a.pool = 1000000; a.is_long = 1;
        a.long_oi = 600; a.short_oi = 400; a.rfactor = 1000000; a.factor = 20;
        if (fps_u(a, limb) != 10) return 1;
        a.long_oi = 400; a.short_oi = 600; a.skip = 1;
        if (fps_u(a, limb) != 0) return 1;
        a.is_long = 0;
        if (fps_u(a, limb) != 10) return 1;
        a.is_long = 1; a.long_oi = 500; a.short_oi = 500;
        if (fps_u(a, limb) != 10) return 1;
        a.skip = 0; a.long_oi = 400; a.short_oi = 600;
        if (fps_u(a, limb) != 10) return 1;
        if (ok_u(100, 0) != 0 || ok_u(0, 0) != 1) return 1;
        memset(&a, 0, sizeof(a));
        a.reserved = 400000; a.pool = 1000000; a.is_long = 1;
        a.long_oi = 600; a.short_oi = 400; a.opt = 500000;
        a.rfactor = 1000000; a.factor = 50; a.base = 20; a.above = 100;
        if (fps_u(a, limb) != 8) return 1;
        if (wrong_linear_u(a, limb) != 20) return 1;
        a.reserved = 800000; a.factor = 30;
        if (fps_u(a, limb) != 64) return 1;
        if (wrong_kink_apply_u(a, limb) != 40) return 1;
        if (wrong_linear_u(a, limb) != 24) return 1;
        memset(&a, 0, sizeof(a));
        a.reserved = 500000; a.pool = 1000000; a.is_long = 1;
        a.long_oi = 600; a.short_oi = 400; a.opt = 500000;
        a.rfactor = 500000; a.factor = 20; a.base = 20; a.above = 100;
        if (fps_u(a, limb) != 100) return 1;
        if (wrong_no_rfactor_u(a, limb) != 10) return 1;
        memset(&a, 0, sizeof(a));
        a.reserved = 800000; a.pool = 1000000; a.is_long = 1;
        a.long_oi = 600; a.short_oi = 400; a.opt = 500000;
        a.rfactor = 1000000; a.factor = 30; a.base = 100; a.above = 50;
        if (fps_u(a, limb) != 80) return 1;
        if (wrong_add_neg_u(a, limb) != 50) return 1;
        if (delta_u(10, 3600, limb) != 36000) return 1;
        if (wrong_delta_apply_u(10, 3600, limb) != 0) return 1;
        if (v1_interval_u(10, 3600, 3600, limb) != 10) return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, limb) !=
            14000000000000ULL)
            return 1;
    }
    if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
        return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    int use_limbs = 0;
    int i;
    struct In p;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (argc < 2) return 2;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                  (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_i64(atoll(argv[2]), atoll(argv[3]), atoll(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "ok") == 0 && argc >= 4) {
        printf("%d\n", ok_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "delta") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               delta_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                       use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "applydelta") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               wrong_delta_apply_u((uint64_t)atoll(argv[2]),
                                   (uint64_t)atoll(argv[3]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "v1") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               v1_interval_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                             (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (argc < 13) return 2;
    p = parse11(argv);
    if (strcmp(argv[1], "fps") == 0) {
        printf("%" PRIu64 "\n", fps_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wronglinear") == 0) {
        printf("%" PRIu64 "\n", wrong_linear_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongkinkapply") == 0) {
        printf("%" PRIu64 "\n", wrong_kink_apply_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongnorfactor") == 0) {
        printf("%" PRIu64 "\n", wrong_no_rfactor_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongaddneg") == 0) {
        printf("%" PRId64 "\n", wrong_add_neg_u(p, use_limbs));
        return 0;
    }
    return 2;
}
