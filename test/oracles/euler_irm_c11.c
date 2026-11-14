/*
 * Independent C11 oracle for Euler EVK IRMLinearKink (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect signed product (p/a == b, p >= 0, result <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: euler-xyz/euler-vault-kit IRMLinearKink.sol
 * computeInterestRateInternal (file SPDX GPL-2.0-or-later).
 * This oracle is original C11 and does not copy IRMLinearKink.sol.
 *
 * Distinct from Compound JumpRate: uint32.max utilization, slope*util with
 * no /BASE, no reserves, caller==vault auth on compute (not view).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define UTIL_SCALE 4294967295ULL
#define KINK_HALF 2147483648ULL

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

static int u_add_ok(uint64_t a, uint64_t b) {
  if (a > I64MAX || b > I64MAX) return 0;
  if (use_i128) return ((__int128)a + (__int128)b) <= (__int128)I64MAX;
  if (a > I64MAX - b) return 0;
  return 1;
}

static uint64_t eir_util(uint64_t cash, uint64_t borrows) {
  uint64_t total, u;
  if (cash > I64MAX || borrows > I64MAX) return 0;
  if (!u_add_ok(cash, borrows)) return 0;
  total = cash + borrows;
  if (total == 0) return 0;
  if (!u_mul_ok(borrows, UTIL_SCALE)) return 0;
  if (use_i128)
    u = (uint64_t)(((__int128)borrows * (__int128)UTIL_SCALE) / (__int128)total);
  else
    u = (borrows * UTIL_SCALE) / total;
  if (u > UTIL_SCALE) return 0;
  return u;
}

static uint64_t eir_rate(uint64_t cash, uint64_t borrows, uint64_t base,
                         uint64_t slope1, uint64_t slope2, uint64_t kink) {
  uint64_t u, ir, over, term;
  if (base > I64MAX || slope1 > I64MAX || slope2 > I64MAX || kink > UTIL_SCALE)
    return 0;
  if (cash > I64MAX || borrows > I64MAX) return 0;
  if (!u_add_ok(cash, borrows)) return 0;
  if ((cash + borrows) != 0 && !u_mul_ok(borrows, UTIL_SCALE)) return 0;
  u = eir_util(cash, borrows);
  ir = base;
  if (u <= kink) {
    if (!u_mul_ok(u, slope1)) return 0;
    term = use_i128 ? (uint64_t)((__int128)u * (__int128)slope1) : u * slope1;
    if (!u_add_ok(ir, term)) return 0;
    return ir + term;
  }
  if (!u_mul_ok(kink, slope1)) return 0;
  term = use_i128 ? (uint64_t)((__int128)kink * (__int128)slope1) : kink * slope1;
  if (!u_add_ok(ir, term)) return 0;
  ir = ir + term;
  if (u < kink) return 0;
  over = u - kink;
  if (!u_mul_ok(slope2, over)) return 0;
  term = use_i128 ? (uint64_t)((__int128)slope2 * (__int128)over) : slope2 * over;
  if (!u_add_ok(ir, term)) return 0;
  return ir + term;
}

static int eir_auth(uint64_t caller, uint64_t vault) {
  if (caller > I64MAX || vault > I64MAX) return 0;
  return caller == vault;
}

static uint64_t eir_compute(uint64_t caller, uint64_t vault, uint64_t cash,
                            uint64_t borrows, uint64_t base, uint64_t slope1,
                            uint64_t slope2, uint64_t kink) {
  if (!eir_auth(caller, vault)) return 0;
  return eir_rate(cash, borrows, base, slope1, slope2, kink);
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (eir_util(50, 50) != 2147483647ULL) return 1;
  if (eir_util(0, 0) != 0) return 1;
  if (eir_util(0, 100) != UTIL_SCALE) return 1;
  if (eir_rate(50, 50, 0, 2, 3, KINK_HALF) != 4294967294ULL) return 1;
  if (eir_rate(0, 100, 0, 2, 3, KINK_HALF) != 10737418237ULL) return 1;
  if (eir_rate(25, 75, 0, 2, 3, KINK_HALF) != 7516192765ULL) return 1;
  if (eir_rate(75, 25, 0, 2, 3, KINK_HALF) != 2147483646ULL) return 1;
  if (eir_rate(100, 0, 10, 2, 3, KINK_HALF) != 10) return 1;
  if (eir_rate(0, 0, 10, 2, 3, KINK_HALF) != 10) return 1;
  if (eir_compute(1, 2, 50, 50, 0, 2, 3, KINK_HALF) != 0) return 1;
  if (eir_compute(7, 7, 50, 50, 0, 2, 3, KINK_HALF) != 4294967294ULL) return 1;
  use_i128 = 1;
  if (eir_rate(50, 50, 0, 2, 3, KINK_HALF) != 4294967294ULL) return 1;
  if (eir_rate(0, 100, 0, 2, 3, KINK_HALF) != 10737418237ULL) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: euler_irm_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  add A B [--i128]\n", stderr);
  fputs("  util CASH BORROWS [--i128]\n", stderr);
  fputs("  rate CASH BORROWS BASE S1 S2 KINK [--i128]\n", stderr);
  fputs("  auth CALLER VAULT\n", stderr);
  fputs("  compute CALLER VAULT CASH BORROWS BASE S1 S2 KINK [--i128]\n", stderr);
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
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "mul") == 0 && argc >= 4) {
    printf("%d\n", u_mul_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "add") == 0 && argc >= 4) {
    printf("%d\n", u_add_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "util") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", eir_util(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "rate") == 0 && argc >= 8) {
    printf("%" PRIu64 "\n",
           eir_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                    strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "auth") == 0 && argc >= 4) {
    printf("%d\n", eir_auth(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "compute") == 0 && argc >= 10) {
    printf("%" PRIu64 "\n",
           eir_compute(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                       strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10)));
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
