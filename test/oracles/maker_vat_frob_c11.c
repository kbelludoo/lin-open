/*
 * Independent C11 oracle for Maker/Sky vat.frob (uint64-scale, RAY'=1e9).
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_vat_frob.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol frob/_add/_mul
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

static int umul_ok(uint64_t a, uint64_t b) {
    int ov = 0;
    (void)md(a, b, 1, &ov);
    return ov ? 0 : 1;
}

static uint64_t umul(uint64_t a, uint64_t b) {
    int ov = 0;
    uint64_t q = md(a, b, 1, &ov);
    return ov ? 0 : q;
}

static int rad_ok(uint64_t rate, int64_t dart) {
    int ov = 0;
    uint64_t mag;
    if (dart == 0) return 1;
    if (dart == INT64_MIN) return 0;
    mag = (dart < 0) ? (uint64_t)(-dart) : (uint64_t)dart;
    (void)md(rate, mag, 1, &ov);
    return ov ? 0 : 1;
}

static int64_t rad_val(uint64_t rate, int64_t dart) {
    int ov = 0;
    uint64_t mag, q;
    if (!rad_ok(rate, dart)) return 0;
    if (dart == 0) return 0;
    mag = (dart < 0) ? (uint64_t)(-dart) : (uint64_t)dart;
    q = md(rate, mag, 1, &ov);
    if (ov) return 0;
    return (dart < 0) ? -(int64_t)q : (int64_t)q;
}

static int is_safe(uint64_t ink, uint64_t art, uint64_t rate, uint64_t spot,
                   int64_t dink, int64_t dart) {
    uint64_t ink2, art2, tab, cov;
    if (!add_ui_ok(ink, dink) || !add_ui_ok(art, dart)) return 0;
    ink2 = add_ui(ink, dink);
    art2 = add_ui(art, dart);
    if (!umul_ok(rate, art2) || !umul_ok(ink2, spot)) return 0;
    if (dart <= 0 && dink >= 0) return 1;
    tab = umul(rate, art2);
    cov = umul(ink2, spot);
    return cov >= tab;
}

static int ceiling_ok(uint64_t art_ilk, uint64_t rate, uint64_t line,
                      uint64_t debt, uint64_t line_g, int64_t dart) {
    uint64_t art2, debt2;
    if (dart <= 0) return 1;
    if (!add_ui_ok(art_ilk, dart) || !rad_ok(rate, dart)) return 0;
    if (!add_ui_ok(debt, rad_val(rate, dart))) return 0;
    art2 = add_ui(art_ilk, dart);
    if (!umul_ok(art2, rate)) return 0;
    if (umul(art2, rate) > line) return 0;
    debt2 = add_ui(debt, rad_val(rate, dart));
    return debt2 <= line_g;
}

static int dust_ok(uint64_t art, uint64_t tab, uint64_t dust) {
    if (art == 0) return 1;
    return tab >= dust;
}

static int frob_ok(int live, uint64_t rate, uint64_t ink, uint64_t art,
                   uint64_t art_ilk, int64_t dink, int64_t dart, uint64_t spot,
                   uint64_t line, uint64_t line_g, uint64_t debt, uint64_t dust) {
    uint64_t art2, tab;
    if (live != 1 || rate == 0) return 0;
    if (!add_ui_ok(ink, dink) || !add_ui_ok(art, dart) || !add_ui_ok(art_ilk, dart))
        return 0;
    if (!is_safe(ink, art, rate, spot, dink, dart)) return 0;
    if (!ceiling_ok(art_ilk, rate, line, debt, line_g, dart)) return 0;
    art2 = add_ui(art, dart);
    tab = umul(rate, art2);
    if (!dust_ok(art2, tab, dust)) return 0;
    if (!rad_ok(rate, dart)) return 0;
    if (!add_ui_ok(debt, rad_val(rate, dart))) return 0;
    return 1;
}

static uint64_t max_art(uint64_t ink, uint64_t spot, uint64_t rate) {
    int ov = 0;
    uint64_t cov;
    if (rate == 0) return 0;
    if (!umul_ok(ink, spot)) return 0;
    cov = umul(ink, spot);
    return md(cov, 1, rate, &ov);
}

static int selftest(void) {
    uint64_t q1, q2, ray = RAY, e18 = 1000000000000000000ULL;
    int ov1 = 0, ov2 = 0;
    int64_t nd = -500000000;
    q1 = muldiv_i128(100, 200, 50, &ov1);
    q2 = muldiv_limbs(100, 200, 50, &ov2);
    if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
    q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
    q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
    if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
    use_limbs = 0;
    if (frob_ok(1, ray, 0, 0, 0, (int64_t)ray, 500000000, 2000000000ULL, e18, e18, 0, 0) != 1)
        return 1;
    use_limbs = 1;
    if (frob_ok(1, ray, 0, 0, 0, (int64_t)ray, 500000000, 2000000000ULL, e18, e18, 0, 0) != 1)
        return 1;
    use_limbs = 0;
    if (frob_ok(1, ray, 0, 0, 0, (int64_t)ray, 3000000000LL, 2000000000ULL, e18, e18, 0, 0) != 0)
        return 1;
    if (frob_ok(1, ray, ray, 2000000000ULL, 2000000000ULL, 0, nd, ray, e18, e18,
                2000000000000000000ULL, 0) != 1)
        return 1;
    if (max_art(ray, 1500000000ULL, ray) != 1500000000ULL) return 1;
    puts("PASS");
    return 0;
}

static void usage(void) {
    fputs("usage: maker_vat_frob_c11 selftest\n", stderr);
    fputs("  muldiv|muldiv_rem A B D [--limbs]\n", stderr);
    fputs("  tab ART RATE [--limbs]\n", stderr);
    fputs("  spot_cov INK SPOT [--limbs]\n", stderr);
    fputs("  add_ui X Y [--limbs]\n", stderr);
    fputs("  new_debt DEBT RATE DART [--limbs]\n", stderr);
    fputs("  safe INK ART RATE SPOT DINK DART [--limbs]\n", stderr);
    fputs("  ceiling ART_ILK RATE LINE DEBT LINE_G DART [--limbs]\n", stderr);
    fputs("  ok LIVE RATE INK ART ART_ILK DINK DART SPOT LINE LINE_G DEBT DUST [--limbs]\n", stderr);
    fputs("  max_art INK SPOT RATE [--limbs]\n", stderr);
    fputs("  naive A B\n", stderr);
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
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10), &ov));
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
    if (strcmp(cmd, "tab") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               umul(strtoull(argv[3], NULL, 10), strtoull(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "spot_cov") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               umul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "add_ui") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               add_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "new_debt") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               add_ui(strtoull(argv[2], NULL, 10),
                      rad_val(strtoull(argv[3], NULL, 10), strtoll(argv[4], NULL, 10))));
        return 0;
    }
    if (strcmp(cmd, "safe") == 0 && argc >= 8) {
        printf("%d\n",
               is_safe(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "ceiling") == 0 && argc >= 8) {
        printf("%d\n",
               ceiling_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                          strtoull(argv[6], NULL, 10), strtoll(argv[7], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "ok") == 0 && argc >= 14) {
        printf("%d\n",
               frob_ok((int)strtol(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                       strtoll(argv[8], NULL, 10), strtoull(argv[9], NULL, 10),
                       strtoull(argv[10], NULL, 10), strtoull(argv[11], NULL, 10),
                       strtoull(argv[12], NULL, 10), strtoull(argv[13], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "max_art") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               max_art(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "naive") == 0 && argc >= 4) {
        int64_t a = strtoll(argv[2], NULL, 10);
        int64_t b = strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", a * b);
        return 0;
    }
    usage();
    return 2;
}
