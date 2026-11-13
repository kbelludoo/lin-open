/*
 * Independent C11 oracle for Maker LinearDecrease.price (uint64-scale).
 *
 * (tau-dur)*RAY and top*factor two implementations:
 *   1. wrapping-detect unsigned mul (p/a == b and p <= INT64_MAX)
 *   2. __int128: (int128)a * (int128)b in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/abaci.sol LinearDecrease.price
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy abaci.sol.
 *
 * Distinct from StairstepExponentialDecrease rpow and from Clipper.take.
 * tau is an argument (not wards/file storage). dur is elapsed seconds.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define RAY 1000000000ULL

static int use_i128 = 0;

static int u_mul_ok_wrap(uint64_t a, uint64_t b) {
  uint64_t p;
  if (a > I64MAX || b > I64MAX) return 0;
  if (a == 0 || b == 0) return 1;
  p = a * b;
  if (p > I64MAX) return 0;
  return p / a == b;
}

static int u_mul_ok_i128(uint64_t a, uint64_t b) {
  __int128 p;
  if (a > I64MAX || b > I64MAX) return 0;
  p = (__int128)a * (__int128)b;
  return p >= 0 && p <= (__int128)I64MAX;
}

static int u_mul_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_mul_ok_i128(a, b) : u_mul_ok_wrap(a, b);
}

static uint64_t u_mul(uint64_t a, uint64_t b) {
  if (!u_mul_ok(a, b)) return 0;
  return a * b;
}

static int64_t factor(uint64_t dur, uint64_t tau) {
  uint64_t rem;
  if (tau < 1 || dur >= tau) return 0;
  rem = tau - dur;
  if (!u_mul_ok(rem, RAY)) return 0;
  return (int64_t)((rem * RAY) / tau);
}

static int64_t price(uint64_t top, uint64_t dur, uint64_t tau) {
  int64_t f;
  if (top > I64MAX) return 0;
  f = factor(dur, tau);
  if (f <= 0) return 0;
  if (!u_mul_ok(top, (uint64_t)f)) return 0;
  return (int64_t)((top * (uint64_t)f) / RAY);
}

static int64_t ok_price(uint64_t top, uint64_t dur, uint64_t tau) {
  int64_t f;
  if (top > I64MAX) return 0;
  if (tau < 1 || dur >= tau) return 0;
  f = factor(dur, tau);
  if (f <= 0) return 0;
  return u_mul_ok(top, (uint64_t)f) ? 1 : 0;
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (!u_mul_ok_wrap(1000, 1100) || u_mul(1000, 1100) != 1100000) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(1000, 1100) || u_mul(1000, 1100) != 1100000) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(10000000000ULL, 1000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(10000000000ULL, 1000000000ULL)) return 1;
  use_i128 = 0;
  if (price(1000000000ULL, 0, 100) != 1000000000LL) return 1;
  if (price(1000000000ULL, 50, 100) != 500000000LL) return 1;
  if (price(1000000000ULL, 99, 100) != 10000000LL) return 1;
  if (price(1000000000ULL, 100, 100) != 0) return 1;
  if (price(7, 2, 5) != 4) return 1;
  if (price(123456789ULL, 1, 3600) != 123422495LL) return 1;
  if (factor(50, 100) != 500000000LL) return 1;
  if (ok_price(1000000000ULL, 0, 100) != 1) return 1;
  if (ok_price(1000000000ULL, 100, 100) != 0) return 1;
  if (price(10000000000ULL, 0, 100) != 0) return 1;
  use_i128 = 1;
  if (price(1000000000ULL, 50, 100) != 500000000LL) return 1;
  w = (int64_t)((uint64_t)10000000000LL * (uint64_t)1000000000LL);
  if (w != -8446744073709551616LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_abacus_linear_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  factor DUR TAU [--i128]\n", stderr);
  fputs("  price|ok TOP DUR TAU [--i128]\n", stderr);
  fputs("  naive_mul A B\n", stderr);
}

static int last_i128(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++)
    if (strcmp(argv[i], "--i128") == 0) return 1;
  return 0;
}

int main(int argc, char **argv) {
  const char *cmd;
  uint64_t top, dur, tau;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "mul") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", u_mul(strtoull(argv[2], NULL, 10),
                                  strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "factor") == 0 && argc >= 4) {
    printf("%" PRId64 "\n", factor(strtoull(argv[2], NULL, 10),
                                   strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (argc >= 5 && (strcmp(cmd, "price") == 0 || strcmp(cmd, "ok") == 0)) {
    top = strtoull(argv[2], NULL, 10);
    dur = strtoull(argv[3], NULL, 10);
    tau = strtoull(argv[4], NULL, 10);
    if (strcmp(cmd, "price") == 0) printf("%" PRId64 "\n", price(top, dur, tau));
    else printf("%" PRId64 "\n", ok_price(top, dur, tau));
    return 0;
  }
  if (strcmp(cmd, "naive_mul") == 0 && argc >= 4) {
    int64_t a = strtoll(argv[2], NULL, 10);
    int64_t b = strtoll(argv[3], NULL, 10);
    printf("%" PRId64 "\n", (int64_t)((uint64_t)a * (uint64_t)b));
    return 0;
  }
  usage();
  return 2;
}
