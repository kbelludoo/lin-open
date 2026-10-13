/*
 * Independent C11 oracle for GMX V2 getNextFundingFactorPerSecond
 * (uint64 scale). (a*b)/d uses unsigned __int128 AND a portable 32-bit
 * limb muldiv that mirrors src/lin_gmx_v2_funding_fps.lin. Consensus is
 * required before any LIN comparison. This file is not linked into the
 * LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/market/MarketUtils.sol getNextFundingFactorPerSecond
 *   contracts/utils/Calc.sol boundMagnitude
 *   contracts/utils/Precision.sol applyFactor / toFactor
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (FLOAT' = 1e6; exponent/pow skipped as identity):
 *   static (incFps==0): fps = min(diff*factor/total, max); saved = 0
 *   adaptive: nextSaved += sign(skew)*applyFactor(imb,inc)*dur   OR
 *             nextSaved magnitude -= decFps*dur (to +/-1, not 0)
 *   charged fps = abs(bound(nextSaved, min, max))
 *   stored saved = bound(nextSaved, 0, max)   // min is NOT applied
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

static int64_t iabs64(int64_t a) { return a < 0 ? -a : a; }

static int64_t sign64(int64_t a) {
    if (a == 0) return 1;
    return a < 0 ? (int64_t)-1 : (int64_t)1;
}

static int64_t bound_mag(int64_t value, uint64_t minv, uint64_t maxv) {
    uint64_t mag = (uint64_t)iabs64(value);
    if (mag < minv) mag = minv;
    if (mag > maxv) mag = maxv;
    return (int64_t)mag * sign64(value);
}

static uint64_t diff_u(uint64_t a, uint64_t b) { return a > b ? a - b : b - a; }

static uint64_t imb_u(uint64_t lo, uint64_t so, int use_limbs) {
    uint64_t total = lo + so;
    if (total == 0) return 0;
    return md(diff_u(lo, so), FLOAT_P, total, use_limbs);
}

static int change_u(uint64_t lo, uint64_t so, int64_t saved, uint64_t stable,
                    uint64_t dthr, int use_limbs) {
    int same = (saved > 0 && lo > so) || (saved < 0 && so > lo);
    uint64_t imb;
    if (!same) return 1;
    imb = imb_u(lo, so, use_limbs);
    if (imb > stable) return 1;
    if (imb < dthr) return 2;
    return 0;
}

static int64_t raw_u(uint64_t lo, uint64_t so, int64_t saved, uint64_t dur,
                     uint64_t inc, uint64_t dec, uint64_t stable, uint64_t dthr,
                     int dec_as_factor, int dec_to_zero, int use_limbs) {
    uint64_t d, total, mag, decv, incv;
    int ch;
    int64_t nexts;
    d = diff_u(lo, so);
    total = lo + so;
    if (d == 0 && inc == 0) return 0;
    if (total == 0) return 0;
    if (inc == 0) return 0;
    ch = change_u(lo, so, saved, stable, dthr, use_limbs);
    nexts = saved;
    if (ch == 1) {
        incv = md(md(d, inc, total, use_limbs), dur, 1, use_limbs);
        nexts = saved + (lo < so ? -(int64_t)incv : (int64_t)incv);
    }
    if (ch == 2 && saved != 0) {
        mag = (uint64_t)iabs64(saved);
        decv = md(dec, dur, 1, use_limbs);
        if (dec_as_factor)
            decv = md(md(imb_u(lo, so, use_limbs), dec, FLOAT_P, use_limbs),
                      dur, 1, use_limbs);
        if (mag <= decv)
            nexts = dec_to_zero ? 0 : sign64(saved);
        else
            nexts = (int64_t)(mag - decv) * sign64(saved);
    }
    return nexts;
}

struct In {
    uint64_t lo, so, dur, inc, dec, minf, maxf, stable, dthr, sfactor;
    int64_t saved;
};

static int64_t saved_u(struct In p, int use_limbs) {
    int64_t nxt;
    if (p.inc == 0) return 0;
    nxt = raw_u(p.lo, p.so, p.saved, p.dur, p.inc, p.dec, p.stable, p.dthr, 0,
                0, use_limbs);
    return bound_mag(nxt, 0, p.maxf);
}

static int64_t minb_u(struct In p, int use_limbs) {
    int64_t s = saved_u(p, use_limbs);
    if (p.inc == 0) return 0;
    return bound_mag(s, p.minf, p.maxf);
}

static uint64_t static_fps_u(uint64_t lo, uint64_t so, uint64_t maxf,
                            uint64_t sfactor, int use_limbs) {
    uint64_t fps;
    if (diff_u(lo, so) == 0 || lo + so == 0) return 0;
    fps = md(imb_u(lo, so, use_limbs), sfactor, FLOAT_P, use_limbs);
    if (fps > maxf) return maxf;
    return fps;
}

static uint64_t fps_u(struct In p, int use_limbs) {
    if (diff_u(p.lo, p.so) == 0 && p.inc == 0) return 0;
    if (p.lo + p.so == 0) return 0;
    if (p.inc == 0) return static_fps_u(p.lo, p.so, p.maxf, p.sfactor, use_limbs);
    return (uint64_t)iabs64(minb_u(p, use_limbs));
}

static int pay_u(struct In p, int use_limbs) {
    int64_t m;
    if (diff_u(p.lo, p.so) == 0 && p.inc == 0) return 1;
    if (p.lo + p.so == 0) return 0;
    if (p.inc == 0) return p.lo > p.so ? 1 : 0;
    m = minb_u(p, use_limbs);
    return m > 0 ? 1 : 0;
}

static int64_t wrong_min_u(struct In p, int use_limbs) {
    int64_t nxt;
    if (p.inc == 0) return 0;
    nxt = raw_u(p.lo, p.so, p.saved, p.dur, p.inc, p.dec, p.stable, p.dthr, 0,
                0, use_limbs);
    return bound_mag(nxt, p.minf, p.maxf);
}

static int64_t wrong_dec0_u(struct In p, int use_limbs) {
    int64_t nxt = raw_u(p.lo, p.so, p.saved, p.dur, p.inc, p.dec, p.stable,
                        p.dthr, 0, 1, use_limbs);
    return bound_mag(nxt, 0, p.maxf);
}

static int64_t wrong_decf_u(struct In p, int use_limbs) {
    int64_t nxt = raw_u(p.lo, p.so, p.saved, p.dur, p.inc, p.dec, p.stable,
                        p.dthr, 1, 0, use_limbs);
    return bound_mag(nxt, 0, p.maxf);
}

static uint64_t wrong_nocap_u(uint64_t lo, uint64_t so, uint64_t sfactor,
                             int use_limbs) {
    if (lo + so == 0) return 0;
    return md(imb_u(lo, so, use_limbs), sfactor, FLOAT_P, use_limbs);
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static struct In parse11(char **argv) {
    struct In p;
    p.lo = (uint64_t)atoll(argv[2]);
    p.so = (uint64_t)atoll(argv[3]);
    p.saved = atoll(argv[4]);
    p.dur = (uint64_t)atoll(argv[5]);
    p.inc = (uint64_t)atoll(argv[6]);
    p.dec = (uint64_t)atoll(argv[7]);
    p.minf = (uint64_t)atoll(argv[8]);
    p.maxf = (uint64_t)atoll(argv[9]);
    p.stable = (uint64_t)atoll(argv[10]);
    p.dthr = (uint64_t)atoll(argv[11]);
    p.sfactor = (uint64_t)atoll(argv[12]);
    return p;
}

static int selftest(void) {
    struct In a;
    int limb;
    for (limb = 0; limb < 2; limb++) {
        if (md(100, 200, 50, limb) != 400) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 600; a.so = 400; a.maxf = 10000; a.sfactor = 50;
        if (fps_u(a, limb) != 10) return 1;
        a.lo = 900; a.so = 100; a.maxf = 20;
        if (fps_u(a, limb) != 20) return 1;
        if (wrong_nocap_u(900, 100, 50, limb) != 40) return 1;
        a.lo = 500; a.so = 500; a.maxf = 10000;
        if (fps_u(a, limb) != 0 || pay_u(a, limb) != 1) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 700; a.so = 300; a.saved = 100; a.dur = 5; a.inc = 10;
        a.maxf = 10000; a.stable = 100000;
        if (fps_u(a, limb) != 120) return 1;
        a.lo = 300; a.so = 700;
        if (fps_u(a, limb) != 80 || pay_u(a, limb) != 1) return 1;
        a.saved = 10;
        if (saved_u(a, limb) != -10 || pay_u(a, limb) != 0) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 400; a.so = 600; a.saved = -3; a.inc = 10; a.minf = 10;
        a.maxf = 10000; a.stable = 500000; a.dthr = 50000;
        if (saved_u(a, limb) != -3) return 1;
        if (wrong_min_u(a, limb) != -10) return 1;
        if (fps_u(a, limb) != 10) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 510; a.so = 490; a.saved = 50; a.dur = 7; a.inc = 10; a.dec = 8;
        a.maxf = 10000; a.stable = 500000; a.dthr = 100000;
        if (saved_u(a, limb) != 1) return 1;
        if (wrong_dec0_u(a, limb) != 0) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 800; a.so = 200; a.saved = 100; a.dur = 7; a.inc = 10; a.dec = 8;
        a.maxf = 10000; a.stable = 900000; a.dthr = 700000;
        if (saved_u(a, limb) != 44) return 1;
        if (wrong_decf_u(a, limb) != 72) return 1;
        memset(&a, 0, sizeof(a));
        a.lo = 700; a.so = 300; a.saved = 90; a.dur = 5; a.inc = 10; a.maxf = 100;
        a.stable = 100000;
        if (fps_u(a, limb) != 100) return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, limb) !=
            14000000000000ULL)
            return 1;
    }
    if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
        return 1;
    if (bound_mag(-3, 10, 10000) != -10) return 1;
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
    if (strcmp(argv[1], "wrongnocap") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               wrong_nocap_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                             (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "bound") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               bound_mag(atoll(argv[2]), (uint64_t)atoll(argv[3]),
                         (uint64_t)atoll(argv[4])));
        return 0;
    }
    if (argc < 13) return 2;
    p = parse11(argv);
    if (strcmp(argv[1], "fps") == 0) {
        printf("%" PRIu64 "\n", fps_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "saved") == 0) {
        printf("%" PRId64 "\n", saved_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "pay") == 0) {
        printf("%d\n", pay_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongmin") == 0) {
        printf("%" PRId64 "\n", wrong_min_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongdec0") == 0) {
        printf("%" PRId64 "\n", wrong_dec0_u(p, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongdecf") == 0) {
        printf("%" PRId64 "\n", wrong_decf_u(p, use_limbs));
        return 0;
    }
    return 2;
}
