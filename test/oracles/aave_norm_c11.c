/*
 * Independent C11 oracle for Aave V3 normalized income / debt (uint64 scale).
 *
 * RAY' = 1e9 (mainnet RAY=1e27 does not fit uint64).
 * SECONDS_PER_YEAR = 365 days = 31536000.
 *
 *   linear(rate, dt) = RAY' + (rate * dt) / SPY
 *   income(rate, index, dt) = dt==0 ? index : rayMul(linear(rate,dt), index)
 *   compound = Aave 3-term binomial; debt = rayMul(compound, index)
 *   rayMul(a,b) = (a*b + HALF_RAY') / RAY'   (half-up)
 *
 * Two implementations of (a*b + add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_norm.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: aave/aave-v3-core ReserveLogic.sol + MathUtils.sol
 * (MIT after BUSL Change Date 2023-01-27). This oracle is original C11 and
 * does not vendor the Solidity source.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY_P 1000000000ULL
#define HALF_RAY_P 500000000ULL
#define SPY 31536000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_add_limbs_qr(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                                uint64_t *q_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
    uint64_t bit, ge, need_borrow, lo2;
    int i, ov;

    if (d == 0) {
        *q_out = 0;
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
    hi = hi + ((lo2 < lo) ? 1ULL : 0ULL);
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
    if ((int64_t)q < 0) ov = 1;
    *q_out = ov ? 0 : q;
    *ov_out = ov;
}

static uint64_t muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q;
    int ov;
    muldiv_add_limbs_qr(a, b, add, d, &q, &ov);
    return q;
}

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t num, q;
    if (d == 0) return 0;
    num = (__uint128_t)a * (__uint128_t)b + (__uint128_t)add;
    q = num / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t ray_mul(uint64_t a, uint64_t b, md_fn md) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, HALF_RAY_P, RAY_P);
}

static uint64_t linear_interest(uint64_t rate, uint64_t dt, md_fn md) {
    uint64_t inc = md(rate, dt, 0, SPY);
    uint64_t s = RAY_P + inc;
    if (s < RAY_P) return 0;
    if ((int64_t)s < 0) return 0;
    return s;
}

static uint64_t normalized_income(uint64_t rate, uint64_t index, uint64_t dt, md_fn md) {
    if (dt == 0) return index;
    return ray_mul(linear_interest(rate, dt, md), index, md);
}

static uint64_t compounded_interest(uint64_t rate, uint64_t dt, md_fn md) {
    uint64_t spy2, bp2, bp3, e1, e2, first, second, third, s, s2, s3;
    if (dt == 0) return RAY_P;
    spy2 = md(SPY, SPY, 0, 1);
    if (spy2 == 0) return 0;
    bp2 = md(ray_mul(rate, rate, md), 1, 0, spy2);
    bp3 = md(ray_mul(bp2, rate, md), 1, 0, SPY);
    e1 = dt - 1;
    e2 = (dt > 2) ? (dt - 2) : 0;
    second = md(md(dt, e1, 0, 1), bp2, 0, 2);
    third = md(md(md(dt, e1, 0, 1), e2, 0, 1), bp3, 0, 6);
    first = md(rate, dt, 0, SPY);
    s = RAY_P + first;
    if (s < RAY_P) return 0;
    s2 = s + second;
    if (s2 < s) return 0;
    s3 = s2 + third;
    if (s3 < s2) return 0;
    if ((int64_t)s3 < 0) return 0;
    return s3;
}

static uint64_t normalized_debt(uint64_t rate, uint64_t index, uint64_t dt, md_fn md) {
    if (dt == 0) return index;
    return ray_mul(compounded_interest(rate, dt, md), index, md);
}

static int selftest(void) {
    int fail = 0;
    struct {
        const char *kind;
        uint64_t a, b, c;
        uint64_t want;
    } vec[] = {
        {"linear", 0, SPY, 0, RAY_P},
        {"linear", 50000000ULL, SPY, 0, 1050000000ULL},
        {"income", 50000000ULL, RAY_P, 0, RAY_P},
        {"income", 50000000ULL, RAY_P, SPY, 1050000000ULL},
        {"income", 50000000ULL, 2ULL * RAY_P, SPY, 2100000000ULL},
        {"income", 50000000ULL, RAY_P, 86400ULL, 1000136986ULL},
        {"compound", 50000000ULL, SPY, 0, 1050000000ULL},
        {"debt", 50000000ULL, RAY_P, SPY, 1050000000ULL},
        {"compound", 1000000000000ULL, SPY, 0, 498260632232000ULL},
        {"linear", 1000000000000ULL, SPY, 0, 1001000000000ULL},
        {"debt", 50000000ULL, RAY_P, 0, RAY_P},
        {"raymul", 10000000000ULL, 10000000000ULL, 0, 100000000000ULL},
    };
    size_t i, n = sizeof(vec) / sizeof(vec[0]);
    for (i = 0; i < n; i++) {
        uint64_t got_i = 0, got_l = 0, want = vec[i].want;
        const char *k = vec[i].kind;
        uint64_t a = vec[i].a, b = vec[i].b, c = vec[i].c;
        if (strcmp(k, "linear") == 0) {
            got_i = linear_interest(a, b, muldiv_add_i128);
            got_l = linear_interest(a, b, muldiv_add_limbs);
        } else if (strcmp(k, "income") == 0) {
            got_i = normalized_income(a, b, c, muldiv_add_i128);
            got_l = normalized_income(a, b, c, muldiv_add_limbs);
        } else if (strcmp(k, "compound") == 0) {
            got_i = compounded_interest(a, b, muldiv_add_i128);
            got_l = compounded_interest(a, b, muldiv_add_limbs);
        } else if (strcmp(k, "debt") == 0) {
            got_i = normalized_debt(a, b, c, muldiv_add_i128);
            got_l = normalized_debt(a, b, c, muldiv_add_limbs);
        } else {
            got_i = ray_mul(a, b, muldiv_add_i128);
            got_l = ray_mul(a, b, muldiv_add_limbs);
        }
        if (got_i != want || got_l != want) {
            fprintf(stderr, "selftest fail %s a=%" PRIu64 " b=%" PRIu64
                            " c=%" PRIu64 " i128=%" PRIu64 " limbs=%" PRIu64
                            " want=%" PRIu64 "\n",
                    k, a, b, c, got_i, got_l, want);
            fail = 1;
        }
    }
    if (compounded_interest(1000000000000ULL, SPY, muldiv_add_i128) ==
        linear_interest(1000000000000ULL, SPY, muldiv_add_i128))
        fail = 1;
    if (fail) {
        printf("FAIL\n");
        return 1;
    }
    printf("PASS\n");
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: aave_norm_c11 selftest\n"
            "       aave_norm_c11 linear|compound RATE DT [--limbs]\n"
            "       aave_norm_c11 income|debt RATE INDEX DT [--limbs]\n"
            "       aave_norm_c11 raymul A B [--limbs]\n");
}

int main(int argc, char **argv) {
    uint64_t a, b, c = 0, got;
    int limbs = 0;
    const char *kind;
    md_fn md;

    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 4) {
        usage();
        return 2;
    }
    kind = argv[1];
    a = strtoull(argv[2], NULL, 10);
    b = strtoull(argv[3], NULL, 10);
    if (strcmp(kind, "income") == 0 || strcmp(kind, "debt") == 0) {
        if (argc < 5) {
            usage();
            return 2;
        }
        c = strtoull(argv[4], NULL, 10);
        if (argc >= 6 && strcmp(argv[5], "--limbs") == 0) limbs = 1;
    } else if (argc >= 5 && strcmp(argv[4], "--limbs") == 0) {
        limbs = 1;
    }
    md = limbs ? muldiv_add_limbs : muldiv_add_i128;
    if (strcmp(kind, "linear") == 0) {
        got = linear_interest(a, b, md);
    } else if (strcmp(kind, "compound") == 0) {
        got = compounded_interest(a, b, md);
    } else if (strcmp(kind, "income") == 0) {
        got = normalized_income(a, b, c, md);
    } else if (strcmp(kind, "debt") == 0) {
        got = normalized_debt(a, b, c, md);
    } else if (strcmp(kind, "raymul") == 0) {
        got = ray_mul(a, b, md);
    } else {
        usage();
        return 2;
    }
    printf("%" PRIu64 "\n", got);
    return 0;
}
