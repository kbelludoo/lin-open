/*
 * Independent C11 oracle for Maker/Sky vat.fold (uint64-scale, RAY'=1e9).
 *
 *   new_rate = rate + rate_delta          (uint + signed, fail-closed)
 *   rad      = Art * rate_delta           (uint * signed, 128-bit mag)
 *   new_dai  = dai + rad
 *   new_debt = debt + rad
 *   live != 1 fail-closes
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_vat_fold.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol fold/_add(uint,int)/_mul(uint,int)
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy vat.sol.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY 1000000000ULL
#define I64MAX ((uint64_t)INT64_MAX)

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int *ov) {
    __uint128_t q;
    if (ov) *ov = 0;
    if (d == 0) {
        if (ov) *ov = 1;
        return 0;
    }
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > I64MAX) {
        if (ov) *ov = 1;
        return 0;
    }
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

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

static int add_ui_ok(uint64_t x, int64_t y) {
    if (y == 0) return 1;
    if (y > 0) {
        uint64_t s = x + (uint64_t)y;
        if (s < x) return 0;
        if (s > I64MAX) return 0;
        return 1;
    }
    if (y == INT64_MIN) return 0;
    uint64_t mag = (uint64_t)(-y);
    return x >= mag;
}

static uint64_t add_ui(uint64_t x, int64_t y) {
    if (!add_ui_ok(x, y)) return 0;
    if (y >= 0) return x + (uint64_t)y;
    return x - (uint64_t)(-y);
}

static int rad_ok(uint64_t art, int64_t rate_delta) {
    int ov = 0;
    uint64_t mag;
    if (rate_delta == 0) return 1;
    if (rate_delta == INT64_MIN) return 0;
    mag = (rate_delta < 0) ? (uint64_t)(-rate_delta) : (uint64_t)rate_delta;
    (void)md(art, mag, 1, &ov);
    return ov ? 0 : 1;
}

static int64_t rad_val(uint64_t art, int64_t rate_delta) {
    int ov = 0;
    uint64_t mag, q;
    if (!rad_ok(art, rate_delta)) return 0;
    if (rate_delta == 0) return 0;
    mag = (rate_delta < 0) ? (uint64_t)(-rate_delta) : (uint64_t)rate_delta;
    q = md(art, mag, 1, &ov);
    if (ov) return 0;
    return (rate_delta < 0) ? -(int64_t)q : (int64_t)q;
}

static uint64_t fold_rate(uint64_t rate, int64_t rate_delta, int live) {
    if (live != 1) return 0;
    return add_ui(rate, rate_delta);
}

static int64_t fold_rad(uint64_t art, int64_t rate_delta, int live) {
    if (live != 1) return 0;
    return rad_val(art, rate_delta);
}

static uint64_t fold_dai(uint64_t dai, uint64_t art, int64_t rate_delta, int live) {
    if (live != 1) return 0;
    if (!rad_ok(art, rate_delta)) return 0;
    return add_ui(dai, rad_val(art, rate_delta));
}

static int fold_ok(uint64_t rate, uint64_t art, int64_t rate_delta,
                   uint64_t dai, uint64_t debt, int live) {
    int64_t r;
    if (live != 1) return 0;
    if (!add_ui_ok(rate, rate_delta)) return 0;
    if (!rad_ok(art, rate_delta)) return 0;
    r = rad_val(art, rate_delta);
    if (!add_ui_ok(dai, r)) return 0;
    if (!add_ui_ok(debt, r)) return 0;
    return 1;
}

static int selftest(void) {
    uint64_t q1, q2;
    int ov1 = 0, ov2 = 0;
    int64_t r1, r2;
    uint64_t ray = RAY;
    uint64_t art = RAY;
    int64_t dlt = 1000000;
    int64_t nd = -1000000;
    q1 = muldiv_i128(100, 200, 50, &ov1);
    q2 = muldiv_limbs(100, 200, 50, &ov2);
    if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
    q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
    q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
    if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
    use_limbs = 0;
    r1 = fold_rad(art, dlt, 1);
    use_limbs = 1;
    r2 = fold_rad(art, dlt, 1);
    if (r1 != 1000000000000000LL || r1 != r2) return 1;
    use_limbs = 0;
    q1 = fold_rate(ray, dlt, 1);
    use_limbs = 1;
    q2 = fold_rate(ray, dlt, 1);
    if (q1 != 1001000000ULL || q1 != q2) return 1;
    use_limbs = 0;
    r1 = fold_rad(art, nd, 1);
    use_limbs = 1;
    r2 = fold_rad(art, nd, 1);
    if (r1 != -1000000000000000LL || r1 != r2) return 1;
    use_limbs = 0;
    if (fold_rate(ray, dlt, 0) != 0) return 1;
    if (fold_ok(ray, art, dlt, 0, 0, 1) != 1) return 1;
    if (fold_ok(100, art, -200, 0, 0, 1) != 0) return 1;
    if (fold_dai(100, art, nd, 1) != 0) return 1;
    puts("PASS");
    return 0;
}

static void usage(void) {
    fputs("usage: maker_vat_fold_c11 selftest", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 rad ART RATE_DELTA [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 rate RATE RATE_DELTA LIVE [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 dai DAI ART RATE_DELTA LIVE [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 debt DEBT ART RATE_DELTA LIVE [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 ok RATE ART RATE_DELTA DAI DEBT LIVE [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 muldiv|muldiv_rem A B D [--limbs]", stderr); fputc(10, stderr);
    fputs("       maker_vat_fold_c11 naive A B", stderr); fputc(10, stderr);
}

int main(int argc, char **argv) {
    const char *cmd;
    int i;
    if (argc < 2) {
        usage();
        return 2;
    }
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc >= 5) {
        int ov = 0;
        printf("%" PRIu64 "%c",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10), &ov), 10);
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
            printf("%" PRIu64 "%c", r, 10);
        } else {
            printf("%" PRIu64 "%c", muldiv_rem_i128(a, b, d), 10);
        }
        return 0;
    }
    if (strcmp(cmd, "rad") == 0 && argc >= 4) {
        printf("%" PRId64 "%c",
               fold_rad(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10), 1), 10);
        return 0;
    }
    if (strcmp(cmd, "rate") == 0 && argc >= 5) {
        printf("%" PRIu64 "%c",
               fold_rate(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                         (int)strtol(argv[4], NULL, 10)), 10);
        return 0;
    }
    if (strcmp(cmd, "dai") == 0 && argc >= 6) {
        printf("%" PRIu64 "%c",
               fold_dai(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoll(argv[4], NULL, 10), (int)strtol(argv[5], NULL, 10)), 10);
        return 0;
    }
    if (strcmp(cmd, "debt") == 0 && argc >= 6) {
        printf("%" PRIu64 "%c",
               fold_dai(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoll(argv[4], NULL, 10), (int)strtol(argv[5], NULL, 10)), 10);
        return 0;
    }
    if (strcmp(cmd, "ok") == 0 && argc >= 8) {
        printf("%d%c",
               fold_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoll(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), (int)strtol(argv[7], NULL, 10)), 10);
        return 0;
    }
    if (strcmp(cmd, "naive") == 0 && argc >= 4) {
        int64_t a = (int64_t)strtoll(argv[2], NULL, 10);
        int64_t b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "%c", a * b, 10);
        return 0;
    }
    usage();
    return 2;
}
