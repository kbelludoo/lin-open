/*
 * Independent C11 oracle for Aave V3 WadRayMath (uint64 / i64-positive scale).
 *
 * Two implementations of (a*b + add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_wadray.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: aave/aave-v3-core contracts/protocol/libraries/math/WadRayMath.sol
 * Algorithm license: MIT (BUSL-1.1 Change Date 2023-01-27 elapsed).
 * This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL
#define HALF_WAD 500000000000000000ULL
#define RATIO 1000000000ULL
#define SRAY 1000000000ULL
#define HALF_SRAY 500000000ULL
#define I64MAX 9223372036854775807ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_add_limbs_q(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                               uint64_t *q_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, lo2;
    uint64_t bit, ge, need_borrow;
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
        *ov_out = 1;
        return;
    }
    *q_out = q;
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
    uint64_t q;
    int ov;
    muldiv_add_limbs_q(a, b, add, d, &q, &ov);
    return q;
}

static uint64_t wad_mul(uint64_t a, uint64_t b,
                        uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, HALF_WAD, WAD);
}

static uint64_t wad_div(uint64_t a, uint64_t b,
                        uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, WAD, b / 2, b);
}

static uint64_t floor_mul(uint64_t a, uint64_t b,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, 0, WAD);
}

static uint64_t floor_div(uint64_t a, uint64_t b,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, WAD, 0, b);
}

static uint64_t sray_mul(uint64_t a, uint64_t b,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, HALF_SRAY, SRAY);
}

static int wad_to_ray_ok(uint64_t a) {
    if (a == 0) return 1;
    return a <= (I64MAX / RATIO);
}

static uint64_t wad_to_ray(uint64_t a) {
    if (!wad_to_ray_ok(a)) return 0;
    return a * RATIO;
}

static int selftest(void) {
    int fail = 0;
    uint64_t (*md_i)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_i128;
    uint64_t (*md_l)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_limbs;
    uint64_t w = WAD;
    uint64_t h = HALF_WAD;
    uint64_t a, b;

    if (wad_mul(w, w, md_i) != w) fail++;
    if (wad_mul(w, w, md_l) != w) fail++;
    if (wad_mul(2 * w, 2 * w, md_i) != 4 * w) fail++;
    if (wad_mul(2 * w, 2 * w, md_l) != 4 * w) fail++;
    if (wad_mul(3, h, md_i) != 2) fail++;
    if (wad_mul(3, h, md_l) != 2) fail++;
    if (floor_mul(3, h, md_i) != 1) fail++;
    if (wad_div(2, 3, md_i) != 666666666666666667ULL) fail++;
    if (wad_div(2, 3, md_l) != 666666666666666667ULL) fail++;
    if (floor_div(2, 3, md_i) != 666666666666666666ULL) fail++;
    if (wad_div(1, 3, md_i) != wad_div(1, 3, md_l)) fail++;
    if (wad_mul(3 * w, 3 * w, md_i) != 9000000000000000000ULL) fail++;
    if (wad_mul(3 * w, 3 * w, md_l) != 9000000000000000000ULL) fail++;
    if (wad_mul(4 * w, 3 * w, md_i) != 0) fail++;
    if (wad_mul(4 * w, 3 * w, md_l) != 0) fail++;
    if (wad_to_ray_ok(w) != 0) fail++;
    if (wad_to_ray(w) != 0) fail++;
    if (wad_to_ray(1) != RATIO) fail++;
    if (sray_mul(3, HALF_SRAY, md_i) != 2) fail++;
    if (sray_mul(3, HALF_SRAY, md_l) != 2) fail++;
    a = 123456789ULL;
    b = 987654321ULL;
    if (wad_mul(a, b, md_i) != wad_mul(a, b, md_l)) fail++;
    if (wad_div(a, b, md_i) != wad_div(a, b, md_l)) fail++;

    if (fail) {
        fprintf(stderr, "aave_wadray_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("aave_wadray_c11 selftest PASS\n");
    printf("vector.wad_mul_1=%" PRIu64 "\n", wad_mul(w, w, md_i));
    printf("vector.half_up_3=%" PRIu64 "\n", wad_mul(3, h, md_i));
    printf("vector.floor_3=%" PRIu64 "\n", floor_mul(3, h, md_i));
    printf("vector.wad_div_2_3=%" PRIu64 "\n", wad_div(2, 3, md_i));
    printf("vector.ray_fits=0\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t) = muldiv_add_i128;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | wadmul a b | waddiv a b | floor_mul a b | floor_div a b | sraymul a b | wad2ray a\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muldiv_add_limbs;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "wadmul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", wad_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "waddiv") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", wad_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "floor_mul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", floor_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "floor_div") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", floor_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "sraymul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", sray_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "wad2ray") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", wad_to_ray(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "muldivadd") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
