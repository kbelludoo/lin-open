/*
 * Independent C11 oracle for Maker/Sky pot.drip (uint64-scale, RAY'=1e9).
 *
 *   drip(dsr, chi, now, rho) = rmul(rpow(dsr, now-rho, RAY'), chi)
 *   rpow: binary exponentiation, half-up (Maker assembly)
 *   rmul: floor (x*y)/RAY'  (Maker pot._rmul)
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_pot_drip.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/pot.sol drip/_rpow/_rmul
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy pot.sol.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY 1000000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int round, int *ov) {
    __uint128_t num, q;
    if (ov) *ov = 0;
    if (d == 0) {
        if (ov) *ov = 1;
        return 0;
    }
    num = (__uint128_t)a * (__uint128_t)b;
    if (round) num += (__uint128_t)(d >> 1);
    q = num / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) {
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

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d, int round,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    uint64_t half, lo2, hi2, c;
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
    if (round) {
        half = d >> 1;
        lo2 = lo + half;
        c = (lo2 < lo) ? 1 : 0;
        lo = lo2;
        hi2 = hi + c;
        if (hi2 < hi) {
            *q_out = 0;
            *r_out = 0;
            *ov_out = 1;
            return;
        }
        hi = hi2;
    }
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

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d, int round, int *ov) {
    uint64_t q, r;
    int o = 0;
    muldiv_limbs_qr(a, b, d, round, &q, &r, &o);
    if (ov) *ov = o;
    return q;
}

static int use_limbs = 0;

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int round, int *ov) {
    return use_limbs ? muldiv_limbs(a, b, d, round, ov)
                     : muldiv_i128(a, b, d, round, ov);
}

static uint64_t rmul(uint64_t x, uint64_t y) {
    int ov = 0;
    return md(x, y, RAY, 0, &ov);
}

static uint64_t rpow(uint64_t x, uint64_t n, uint64_t b) {
    uint64_t z, n2, steps;
    int ov = 0;
    if (b == 0) return 0;
    if (x == 0) return (n == 0) ? b : 0;
    z = (n & 1ULL) ? x : b;
    n2 = n >> 1;
    steps = 0;
    while (n2 != 0) {
        x = md(x, x, b, 1, &ov);
        if (n2 & 1ULL) z = md(z, x, b, 1, &ov);
        n2 >>= 1;
        steps++;
        if (steps > 63) return 0;
    }
    return z;
}

static uint64_t drip(uint64_t dsr, uint64_t chi, uint64_t now_ts, uint64_t rho) {
    uint64_t dt, acc;
    if (now_ts < rho) return 0;
    dt = now_ts - rho;
    acc = rpow(dsr, dt, RAY);
    return rmul(acc, chi);
}

static uint64_t linear(uint64_t dsr, uint64_t chi, uint64_t now_ts, uint64_t rho) {
    uint64_t dt, extra, scaled;
    int ov = 0;
    if (now_ts < rho) return 0;
    if (dsr < RAY) return 0;
    dt = now_ts - rho;
    extra = md(dsr - RAY, dt, 1, 0, &ov);
    scaled = RAY + extra;
    if (scaled < RAY) return 0;
    return rmul(scaled, chi);
}

static uint64_t chi_delta(uint64_t dsr, uint64_t chi, uint64_t now_ts, uint64_t rho) {
    uint64_t tmp = drip(dsr, chi, now_ts, rho);
    if (tmp < chi) return 0;
    return tmp - chi;
}

static int selftest(void) {
    uint64_t q1, q2, r1, r2;
    int ov1 = 0, ov2 = 0;
    uint64_t dsr = RAY + 1000000ULL;
    q1 = muldiv_i128(100, 200, 50, 0, &ov1);
    q2 = muldiv_limbs(100, 200, 50, 0, &ov2);
    if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
    r1 = muldiv_rem_i128(3, 4, 5);
    muldiv_limbs_qr(3, 4, 5, 0, &q2, &r2, &ov2);
    if (r1 != 2 || r2 != 2) return 1;
    q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, 0, &ov1);
    q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, 0, &ov2);
    if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
    use_limbs = 0;
    q1 = drip(dsr, RAY, 2, 0);
    use_limbs = 1;
    q2 = drip(dsr, RAY, 2, 0);
    if (q1 != 1002001000ULL || q1 != q2) return 1;
    use_limbs = 0;
    q1 = linear(dsr, RAY, 2, 0);
    use_limbs = 1;
    q2 = linear(dsr, RAY, 2, 0);
    if (q1 != 1002000000ULL || q1 != q2) return 1;
    use_limbs = 0;
    q1 = drip(dsr, RAY, 10, 0);
    use_limbs = 1;
    q2 = drip(dsr, RAY, 10, 0);
    if (q1 != 1010045120ULL || q1 != q2) return 1;
    puts("PASS");
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: maker_pot_drip_c11 selftest\n"
            "       maker_pot_drip_c11 drip|linear|chi_delta DSR CHI NOW RHO [--limbs]\n"
            "       maker_pot_drip_c11 rpow X N B [--limbs]\n"
            "       maker_pot_drip_c11 rmul X Y [--limbs]\n"
            "       maker_pot_drip_c11 join_rad PIE CHI [--limbs]\n"
            "       maker_pot_drip_c11 suck_rad PIE DELTA [--limbs]\n"
            "       maker_pot_drip_c11 file_ok NOW RHO\n"
            "       maker_pot_drip_c11 muldiv|muldiv_half|muldiv_rem A B D [--limbs]\n");
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
                  strtoull(argv[4], NULL, 10), 0, &ov));
        return 0;
    }
    if (strcmp(cmd, "muldiv_half") == 0 && argc >= 5) {
        int ov = 0;
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10), 1, &ov));
        return 0;
    }
    if (strcmp(cmd, "muldiv_rem") == 0 && argc >= 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        if (use_limbs) {
            uint64_t q, r;
            int ov = 0;
            muldiv_limbs_qr(a, b, d, 0, &q, &r, &ov);
            printf("%" PRIu64 "\n", r);
        } else {
            printf("%" PRIu64 "\n", muldiv_rem_i128(a, b, d));
        }
        return 0;
    }
    if (strcmp(cmd, "rpow") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               rpow(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "rmul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               rmul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "drip") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               drip(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "linear") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               linear(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "chi_delta") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               chi_delta(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "join_rad") == 0 && argc >= 4) {
        int ov = 0;
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 1, 0, &ov));
        return 0;
    }
    if (strcmp(cmd, "suck_rad") == 0 && argc >= 4) {
        int ov = 0;
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 1, 0, &ov));
        return 0;
    }
    if (strcmp(cmd, "file_ok") == 0 && argc >= 4) {
        uint64_t now_ts = strtoull(argv[2], NULL, 10);
        uint64_t rho = strtoull(argv[3], NULL, 10);
        printf("%d\n", now_ts == rho ? 1 : 0);
        return 0;
    }
    usage();
    return 2;
}
