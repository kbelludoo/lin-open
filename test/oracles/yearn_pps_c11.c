/*
 * Independent C11 oracle for Yearn V2 pricePerShare / locked-profit math
 * (uint64-scale). Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_yearn_pps.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: yearn/yearn-vaults contracts/Vault.vy (AGPL-3.0-or-later).
 * This oracle is original C11 and does not copy Vault.vy.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DEG_COEF 1000000000000000000ULL
#define DEFAULT_DEG 46000000000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int *ov) {
    __uint128_t q;
    if (ov) *ov = 0;
    if (d == 0) {
        if (ov) *ov = 1;
        return 0;
    }
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) {
        if (ov) *ov = 1;
        return 0;
    }
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
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
            else q = q | (1ULL << i);
        }
    }
    if ((int64_t)q < 0) ov = 1;
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d, int *ov) {
    uint64_t q, r;
    int o = 0;
    muldiv_limbs_qr(a, b, d, &q, &r, &o);
    if (ov) *ov = o;
    return q;
}

static int use_limbs = 0;

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int *ov) {
    return use_limbs ? muldiv_limbs(a, b, d, ov) : muldiv_i128(a, b, d, ov);
}

static uint64_t pow10u(int n) {
    uint64_t v = 1;
    int i;
    if (n < 0 || n > 18) return 0;
    for (i = 0; i < n; i++) v *= 10ULL;
    return v;
}

static int add_ov(uint64_t a, uint64_t b, uint64_t *out) {
    *out = a + b;
    return *out < a;
}

static uint64_t locked_remaining(uint64_t now_ts, uint64_t last, uint64_t locked,
                                 uint64_t deg, int *ok) {
    uint64_t dt, ratio, unlocked;
    int ov = 0;
    *ok = 1;
    if (now_ts < last) {
        *ok = 0;
        return 0;
    }
    dt = now_ts - last;
    if (deg == 0) return locked;
    ratio = md(dt, deg, 1, &ov);
    if (ov) {
        *ok = 0;
        return 0;
    }
    if (ratio >= DEG_COEF) return 0;
    unlocked = md(ratio, locked, DEG_COEF, &ov);
    if (ov || unlocked > locked) {
        *ok = 0;
        return 0;
    }
    return locked - unlocked;
}

static uint64_t free_funds(uint64_t idle, uint64_t debt, uint64_t rem, int *ok) {
    uint64_t assets;
    *ok = 1;
    if (add_ov(idle, debt, &assets)) {
        *ok = 0;
        return 0;
    }
    if (assets < rem) {
        *ok = 0;
        return 0;
    }
    return assets - rem;
}

static uint64_t share_value(uint64_t shares, uint64_t free, uint64_t supply) {
    int ov = 0;
    if (supply == 0) return shares;
    return md(shares, free, supply, &ov);
}

static uint64_t price_per_share(uint64_t decimals, uint64_t idle, uint64_t debt,
                                uint64_t supply, uint64_t now_ts, uint64_t last,
                                uint64_t locked, uint64_t deg) {
    int ok = 1, ov = 0;
    uint64_t unit, rem, free;
    unit = pow10u((int)decimals);
    if (unit == 0) return 0;
    rem = locked_remaining(now_ts, last, locked, deg, &ok);
    if (!ok) return 0;
    free = free_funds(idle, debt, rem, &ok);
    if (!ok) return 0;
    (void)ov;
    return share_value(unit, free, supply);
}

static uint64_t shares_for_amount(uint64_t amount, uint64_t idle, uint64_t debt,
                                  uint64_t supply, uint64_t now_ts, uint64_t last,
                                  uint64_t locked, uint64_t deg) {
    int ok = 1, ov = 0;
    uint64_t rem, free;
    rem = locked_remaining(now_ts, last, locked, deg, &ok);
    if (!ok) return 0;
    free = free_funds(idle, debt, rem, &ok);
    if (!ok) return 0;
    if (supply == 0) return amount;
    if (free == 0) return 0;
    return md(amount, supply, free, &ov);
}

static uint64_t ignore_lock_pps(uint64_t decimals, uint64_t idle, uint64_t debt,
                                uint64_t supply) {
    uint64_t unit = pow10u((int)decimals), assets;
    int ok = 1;
    if (unit == 0) return 0;
    if (add_ov(idle, debt, &assets)) return 0;
    (void)ok;
    return share_value(unit, assets, supply);
}

static uint64_t step_lock_pps(uint64_t decimals, uint64_t idle, uint64_t debt,
                              uint64_t supply, uint64_t now_ts, uint64_t last,
                              uint64_t locked, uint64_t deg) {
    int ok = 1, ov = 0;
    uint64_t dt, ratio, rem, unit, free;
    if (now_ts < last) return 0;
    dt = now_ts - last;
    ratio = md(dt, deg, 1, &ov);
    if (ov) return 0;
    rem = (ratio >= DEG_COEF) ? 0 : locked;
    unit = pow10u((int)decimals);
    if (unit == 0) return 0;
    free = free_funds(idle, debt, rem, &ok);
    if (!ok) return 0;
    return share_value(unit, free, supply);
}

static int selftest(void) {
    uint64_t q1, q2, r1, r2;
    int ov1 = 0, ov2 = 0;
    q1 = muldiv_i128(100, 200, 50, &ov1);
    q2 = muldiv_limbs(100, 200, 50, &ov2);
    if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
    r1 = muldiv_rem_i128(3, 4, 5);
    muldiv_limbs_qr(3, 4, 5, &q2, &r2, &ov2);
    if (r1 != 2 || r2 != 2) return 1;
    q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
    q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
    if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
    use_limbs = 0;
    q1 = price_per_share(18, 1000000000000000000ULL, 0, 1000000000000000000ULL,
                         1000, 1000, 100000000000000000ULL, DEFAULT_DEG);
    use_limbs = 1;
    q2 = price_per_share(18, 1000000000000000000ULL, 0, 1000000000000000000ULL,
                         1000, 1000, 100000000000000000ULL, DEFAULT_DEG);
    if (q1 != 900000000000000000ULL || q1 != q2) return 1;
    puts("PASS");
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    int i;
    if (argc < 2) {
        fprintf(stderr, "usage: yearn_pps_c11 selftest|muldiv|pps|locked|shares|ignore|step [...]\n");
        return 2;
    }
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc >= 5) {
        int ov = 0;
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", md(a, b, d, &ov));
        return 0;
    }
    if (strcmp(cmd, "muldiv_rem") == 0 && argc >= 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        if (use_limbs) {
            uint64_t q, r;
            int ov = 0;
            muldiv_limbs_qr(a, b, d, &q, &r, &ov);
            printf("%" PRIu64 "\n", r);
        } else {
            printf("%" PRIu64 "\n", muldiv_rem_i128(a, b, d));
        }
        return 0;
    }
    if (strcmp(cmd, "pps") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               price_per_share(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                               strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                               strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                               strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "locked") == 0 && argc >= 6) {
        int ok = 1;
        printf("%" PRIu64 "\n",
               locked_remaining(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                &ok));
        return 0;
    }
    if (strcmp(cmd, "shares") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               shares_for_amount(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                 strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                 strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                                 strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "ignore") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               ignore_lock_pps(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                               strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "step") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               step_lock_pps(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                             strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                             strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                             strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
