/*
 * Independent C11 oracle for Aave V3 MathUtils compounded interest (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_compound.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: aave/aave-v3-core contracts/protocol/libraries/math/MathUtils.sol
 * License of the algorithm: MIT after BUSL Change Date 2023-01-27.
 * This oracle is original C11. Experimental wad (1e18) scale, not ray (1e27).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL
#define YEAR 31536000ULL
#define YEAR2 994519296000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
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

static uint64_t (*MD)(uint64_t, uint64_t, uint64_t) = muldiv_i128;

static int dt_ok(uint64_t dt) { return dt <= 2000000000ULL; }

static uint64_t aci_linear(uint64_t rate, uint64_t dt) {
    if (!dt_ok(dt)) return 0;
    return WAD + MD(rate, dt, YEAR);
}

static uint64_t aci_compounded(uint64_t rate, uint64_t dt) {
    uint64_t dt1, dt2, first, r2, pair, second, r3, t, third;
    if (!dt_ok(dt)) return 0;
    if (dt == 0) return WAD;
    dt1 = dt - 1;
    dt2 = (dt > 2) ? (dt - 2) : 0;
    first = MD(rate, dt, YEAR);
    r2 = MD(rate, rate, WAD);
    pair = MD(dt, dt1, 2);
    second = MD(r2, pair, YEAR2);
    r3 = MD(r2, rate, WAD);
    t = MD(r3, dt, YEAR);
    t = MD(t, dt1, YEAR);
    t = MD(t, dt2, YEAR);
    third = MD(t, 1, 6);
    return WAD + first + second + third;
}

static uint64_t aci_year2_floor(uint64_t rate, uint64_t dt) {
    uint64_t dt1, dt2, first, r2, bp2, pair, second, bp3, third;
    if (!dt_ok(dt)) return 0;
    if (dt == 0) return WAD;
    dt1 = dt - 1;
    dt2 = (dt > 2) ? (dt - 2) : 0;
    first = MD(rate, dt, YEAR);
    r2 = MD(rate, rate, WAD);
    bp2 = MD(r2, 1, YEAR2);
    pair = MD(dt, dt1, 2);
    second = MD(pair, bp2, 1);
    bp3 = MD(MD(bp2, rate, WAD), 1, YEAR);
    third = MD(MD(MD(dt, dt1, 1), dt2, 1), bp3, 6);
    return WAD + first + second + third;
}

static uint64_t aci_ex_horner(uint64_t rate, uint64_t dt) {
    uint64_t x, x2, x3;
    if (!dt_ok(dt)) return 0;
    x = MD(rate, dt, YEAR);
    x2 = MD(x, x, WAD);
    x3 = MD(x2, x, WAD);
    return WAD + x + MD(x2, 1, 2) + MD(x3, 1, 6);
}

static uint64_t aci_index_mul(uint64_t index, uint64_t interest) {
    return MD(index, interest, WAD);
}

static int selftest(void) {
    uint64_t q1, r1, q2, r2;
    int ov;
    uint64_t a, b, d;
    const uint64_t vec[][3] = {
        {100, 200, 50}, {7, 9, 1}, {WAD, 1, 2}, {7, 9, 2}
    };
    size_t i;
    for (i = 0; i < sizeof(vec) / sizeof(vec[0]); i++) {
        a = vec[i][0];
        b = vec[i][1];
        d = vec[i][2];
        q1 = muldiv_i128(a, b, d);
        muldiv_limbs_qr(a, b, d, &q2, &r2, &ov);
        (void)ov;
        r1 = muldiv_rem_i128(a, b, d);
        if (q1 != q2 || r1 != r2) {
            printf("SELFTEST FAIL muldiv %llu %llu %llu i128=%llu limbs=%llu\n",
                   (unsigned long long)a, (unsigned long long)b,
                   (unsigned long long)d, (unsigned long long)q1,
                   (unsigned long long)q2);
            return 1;
        }
    }
    MD = muldiv_i128;
    if (aci_compounded(50000000000000000ULL, 31536000ULL) != 1051270833291714231ULL)
        return 1;
    MD = muldiv_limbs;
    if (aci_compounded(50000000000000000ULL, 31536000ULL) != 1051270833291714231ULL)
        return 1;
    MD = muldiv_i128;
    printf("PASS\n");
    return 0;
}

static void use_limbs(int argc, char **argv) {
    int i;
    MD = muldiv_i128;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) MD = muldiv_limbs;
    }
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, out;
    if (argc < 2) {
        fprintf(stderr, "usage: aave_compound_c11 selftest | muldiv A B D [--limbs] | linear RATE DT | compounded RATE DT | year2floor RATE DT | horner RATE DT | index INDEX INTEREST\n");
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    use_limbs(argc, argv);
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        out = MD(a, b, c);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if ((strcmp(kind, "linear") == 0 || strcmp(kind, "compounded") == 0 ||
         strcmp(kind, "year2floor") == 0 || strcmp(kind, "horner") == 0) &&
        argc >= 4) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        if (strcmp(kind, "linear") == 0) out = aci_linear(a, b);
        else if (strcmp(kind, "compounded") == 0) out = aci_compounded(a, b);
        else if (strcmp(kind, "year2floor") == 0) out = aci_year2_floor(a, b);
        else out = aci_ex_horner(a, b);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "index") == 0 && argc >= 4) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n", aci_index_mul(a, b));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
