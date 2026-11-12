/*
 * Independent C11 oracle for Aave V3 WadRayMath rayToWad / wadToRay (i64-positive).
 *
 * Two implementations of uint64 div/mod:
 *   1. Native unsigned 64-bit division
 *   2. Portable restoring divider (bit-by-bit)
 *
 * wadToRay overflow is checked with unsigned __int128 versus the
 * check-then-multiply path used by src/lin_aave_raytowad.lin.
 *
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: aave/aave-v3-core
 *   contracts/protocol/libraries/math/WadRayMath.sol rayToWad / wadToRay
 * License of the algorithm: MIT after BUSL Change Date 2023-01-27.
 * Full Solidity is NOT copied here (hash-only pin lives in the Python harness).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RATIO 1000000000ULL
#define HALF  500000000ULL
#define I64_MAX 9223372036854775807LL

static int use_restore = 0;

static uint64_t udiv_restore(uint64_t n, uint64_t d, uint64_t *rem) {
    uint64_t q = 0, r = 0, bit;
    int i;
    if (d == 0) {
        *rem = 0;
        return 0;
    }
    for (i = 63; i >= 0; i--) {
        bit = (n >> (unsigned)i) & 1ULL;
        r = (r << 1) | bit;
        if (r >= d) {
            r -= d;
            q |= (1ULL << (unsigned)i);
        }
    }
    *rem = r;
    return q;
}

static uint64_t udiv_native(uint64_t n, uint64_t d, uint64_t *rem) {
    if (d == 0) {
        *rem = 0;
        return 0;
    }
    *rem = n % d;
    return n / d;
}

static uint64_t udivmod(uint64_t n, uint64_t d, uint64_t *rem) {
    return use_restore ? udiv_restore(n, d, rem) : udiv_native(n, d, rem);
}

static int64_t ray_to_wad(int64_t a) {
    uint64_t q, r, ua;
    if (a < 0) return 0;
    ua = (uint64_t)a;
    q = udivmod(ua, RATIO, &r);
    if (r >= HALF) return (int64_t)(q + 1ULL);
    return (int64_t)q;
}

static int64_t ray_to_wad_floor(int64_t a) {
    uint64_t r;
    if (a < 0) return 0;
    return (int64_t)udivmod((uint64_t)a, RATIO, &r);
}

static int64_t ray_to_wad_ceil(int64_t a) {
    uint64_t q, r;
    if (a < 0) return 0;
    q = udivmod((uint64_t)a, RATIO, &r);
    if (r != 0) return (int64_t)(q + 1ULL);
    return (int64_t)q;
}

static int wad_to_ray_ok(int64_t a) {
    __int128 p;
    if (a < 0) return 0;
    p = (__int128)a * (__int128)RATIO;
    return p <= (__int128)I64_MAX;
}

static int64_t wad_to_ray(int64_t a) {
    if (!wad_to_ray_ok(a)) return 0;
    return a * (int64_t)RATIO;
}

static int64_t wad_to_ray_check_mul(int64_t a) {
    int64_t max_wad = I64_MAX / (int64_t)RATIO;
    if (a < 0 || a > max_wad) return 0;
    return a * (int64_t)RATIO;
}

static int selftest(void) {
    uint64_t r1, r2, q1, q2;
    uint64_t nums[] = {0, 1, HALF - 1, HALF, HALF + 1, RATIO,
                       RATIO + HALF - 1, RATIO + HALF, RATIO + HALF + 1,
                       1000000000000000000ULL};
    size_t i;
    int64_t half = (int64_t)HALF;
    int64_t ratio = (int64_t)RATIO;

    for (i = 0; i < sizeof(nums) / sizeof(nums[0]); i++) {
        q1 = udiv_native(nums[i], RATIO, &r1);
        q2 = udiv_restore(nums[i], RATIO, &r2);
        if (q1 != q2 || r1 != r2) {
            fprintf(stderr, "udiv mismatch i=%zu\n", i);
            return 1;
        }
    }

    use_restore = 0;
    if (ray_to_wad(0) != 0) return 2;
    if (ray_to_wad(1) != 0) return 3;
    if (ray_to_wad(half - 1) != 0) return 4;
    if (ray_to_wad(half) != 1) return 5;
    if (ray_to_wad_floor(half) != 0) return 6;
    if (ray_to_wad_ceil(half) != 1) return 7;
    if (ray_to_wad(ratio) != 1) return 8;
    if (ray_to_wad(ratio + half) != 2) return 9;
    if (ray_to_wad_floor(ratio + half) != 1) return 10;
    if (wad_to_ray(0) != 0) return 11;
    if (wad_to_ray(1) != ratio) return 12;
    if (wad_to_ray(ratio) != 1000000000000000000LL) return 13;
    if (wad_to_ray_ok(1000000000000000000LL) != 0) return 14;
    if (wad_to_ray(1000000000000000000LL) != 0) return 15;
    if (wad_to_ray(I64_MAX / (int64_t)RATIO) == 0) return 16;
    if (wad_to_ray(I64_MAX / (int64_t)RATIO + 1) != 0) return 17;
    if (wad_to_ray(42) != wad_to_ray_check_mul(42)) return 18;

    use_restore = 1;
    if (ray_to_wad(half) != 1) return 19;
    if (ray_to_wad(ratio + half) != 2) return 20;
    if (wad_to_ray_check_mul(ratio) != 1000000000000000000LL) return 21;

    puts("PASS");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr,
                "usage: aave_raytowad_c11 selftest | r2w|r2w-floor|r2w-ceil|w2r|w2r-ok|naive ... [--restore]\n");
        return 2;
    }
    if (argc > 1 && strcmp(argv[argc - 1], "--restore") == 0) {
        use_restore = 1;
        argc -= 1;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "r2w") == 0 && argc == 3) {
        printf("%" PRId64 "\n", ray_to_wad(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "r2w-floor") == 0 && argc == 3) {
        printf("%" PRId64 "\n", ray_to_wad_floor(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "r2w-ceil") == 0 && argc == 3) {
        printf("%" PRId64 "\n", ray_to_wad_ceil(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "w2r") == 0 && argc == 3) {
        printf("%" PRId64 "\n", wad_to_ray(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "w2r-ok") == 0 && argc == 3) {
        printf("%d\n", wad_to_ray_ok(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc == 4) {
        int64_t a = strtoll(argv[2], NULL, 10);
        int64_t b = strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", a * b);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
