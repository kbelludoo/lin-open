/*
 * Independent C11 oracle for Maker/Sky vat.grab (uint64-scale, RAY'=1e9).
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_vat_grab.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol grab/_add/_sub/_mul
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

static int sub_ui_ok(uint64_t x, int64_t y) {
    if (y == 0) return 1;
    if (y == INT64_MIN) return 0;
    if (y > 0) return x >= (uint64_t)y;
    uint64_t mag = (uint64_t)(-y);
    uint64_t s = x + mag;
    if (s < x) return 0;
    if (s > I64MAX) return 0;
    return 1;
}

static uint64_t sub_ui(uint64_t x, int64_t y) {
    if (!sub_ui_ok(x, y)) return 0;
    if (y >= 0) return x - (uint64_t)y;
    return x + (uint64_t)(-y);
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

static int64_t dtab_val(uint64_t rate, int64_t dart) {
    int ov = 0;
    uint64_t mag, q;
    if (!rad_ok(rate, dart)) return 0;
    if (dart == 0) return 0;
    mag = (dart < 0) ? (uint64_t)(-dart) : (uint64_t)dart;
    q = md(rate, mag, 1, &ov);
    if (ov) return 0;
    return (dart < 0) ? -(int64_t)q : (int64_t)q;
}

static int grab_ok(uint64_t rate, uint64_t ink, uint64_t art, uint64_t art_ilk,
                   int64_t dink, int64_t dart, uint64_t gem_v, uint64_t sin_w,
                   uint64_t vice) {
    int64_t dtab;
    if (!add_ui_ok(ink, dink) || !add_ui_ok(art, dart) || !add_ui_ok(art_ilk, dart))
        return 0;
    if (!rad_ok(rate, dart)) return 0;
    dtab = dtab_val(rate, dart);
    if (!sub_ui_ok(gem_v, dink) || !sub_ui_ok(sin_w, dtab) || !sub_ui_ok(vice, dtab))
        return 0;
    return 1;
}

static int underwater(uint64_t ink, uint64_t art, uint64_t rate, uint64_t spot) {
    int ov = 0;
    uint64_t tab, cov;
    tab = md(rate, art, 1, &ov);
    if (ov) return 0;
    ov = 0;
    cov = md(ink, spot, 1, &ov);
    if (ov) return 0;
    return cov < tab;
}

static int selftest(void) {
    uint64_t q1, q2, ray = RAY;
    int ov1 = 0, ov2 = 0;
    int64_t nd = -(int64_t)ray;
    int64_t n2 = -2000000000LL;
    q1 = muldiv_i128(100, 200, 50, &ov1);
    q2 = muldiv_limbs(100, 200, 50, &ov2);
    if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
    q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
    q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
    if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
    use_limbs = 0;
    if (grab_ok(ray, ray, ray, ray, nd, nd, 0, 0, 0) != 1) return 1;
    use_limbs = 1;
    if (grab_ok(ray, ray, ray, ray, nd, nd, 0, 0, 0) != 1) return 1;
    use_limbs = 0;
    if (grab_ok(ray, 0, 0, 0, -1, 0, 0, 0, 0) != 0) return 1;
    if (underwater(ray, 2000000000ULL, ray, ray) != 1) return 1;
    if (grab_ok(ray, ray, 2000000000ULL, 2000000000ULL, nd, n2, 0, 0, 0) != 1)
        return 1;
    if (sub_ui(0, nd) != ray) return 1;
    if (dtab_val(ray, nd) != -(int64_t)1000000000000000000LL) return 1;
    puts("PASS");
    return 0;
}

static void usage(void) {
    fputs("usage: maker_vat_grab_c11 selftest\n", stderr);
    fputs("  muldiv|muldiv_rem A B D [--limbs]\n", stderr);
    fputs("  add_ui|sub_ui X Y [--limbs]\n", stderr);
    fputs("  dtab RATE DART [--limbs]\n", stderr);
    fputs("  new_ink INK DINK [--limbs]\n", stderr);
    fputs("  new_art ART DART [--limbs]\n", stderr);
    fputs("  new_gem GEM DINK [--limbs]\n", stderr);
    fputs("  new_sin SIN RATE DART [--limbs]\n", stderr);
    fputs("  new_vice VICE RATE DART [--limbs]\n", stderr);
    fputs("  seized DINK [--limbs]\n", stderr);
    fputs("  cancelled DART [--limbs]\n", stderr);
    fputs("  underwater INK ART RATE SPOT [--limbs]\n", stderr);
    fputs("  ok RATE INK ART ART_ILK DINK DART GEM SIN VICE [--limbs]\n", stderr);
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
    if (strcmp(cmd, "add_ui") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               add_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "sub_ui") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               sub_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "dtab") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               dtab_val(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "new_ink") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               add_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "new_art") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               add_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "new_gem") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               sub_ui(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "new_sin") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               sub_ui(strtoull(argv[2], NULL, 10),
                      dtab_val(strtoull(argv[3], NULL, 10), strtoll(argv[4], NULL, 10))));
        return 0;
    }
    if (strcmp(cmd, "new_vice") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               sub_ui(strtoull(argv[2], NULL, 10),
                      dtab_val(strtoull(argv[3], NULL, 10), strtoll(argv[4], NULL, 10))));
        return 0;
    }
    if (strcmp(cmd, "seized") == 0 && argc >= 3) {
        int64_t dink = strtoll(argv[2], NULL, 10);
        printf("%" PRIu64 "\n", (dink < 0 && dink != INT64_MIN) ? (uint64_t)(-dink) : 0);
        return 0;
    }
    if (strcmp(cmd, "cancelled") == 0 && argc >= 3) {
        int64_t dart = strtoll(argv[2], NULL, 10);
        printf("%" PRIu64 "\n", (dart < 0 && dart != INT64_MIN) ? (uint64_t)(-dart) : 0);
        return 0;
    }
    if (strcmp(cmd, "underwater") == 0 && argc >= 6) {
        printf("%d\n",
               underwater(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "ok") == 0 && argc >= 11) {
        printf("%d\n",
               grab_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                       strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10),
                       strtoull(argv[10], NULL, 10)));
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
