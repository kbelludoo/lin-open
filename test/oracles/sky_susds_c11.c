/*
 * Independent C11 oracle for Sky sUSDS ERC-4626 convert (uint64-scale).
 *
 * shares*chi and assets*RAY two implementations:
 *   1. wrapping-detect unsigned mul (p/a == b and p <= INT64_MAX)
 *   2. __int128: (int128)a * (int128)b in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: sky-ecosystem/sdai src/SUsds.sol convertToAssets /
 * convertToShares / _divup (AGPL-3.0-or-later). This oracle is original C11
 * and does not copy SUsds.sol.
 *
 * Distinct from pot.drip rpow and from OZ ERC-4626 virtual offset.
 * chi is an argument (already-accrued). convertTo* are public view.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define RAY 1000ULL

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

static uint64_t divup(uint64_t x, uint64_t y) {
  if (y < 1) return 0;
  if (x == 0) return 0;
  return ((x - 1) / y) + 1;
}

static int64_t to_assets(uint64_t shares, uint64_t chi) {
  if (chi < 1 || shares > I64MAX) return 0;
  if (!u_mul_ok(shares, chi)) return 0;
  return (int64_t)((shares * chi) / RAY);
}

static int64_t to_shares(uint64_t assets, uint64_t chi) {
  if (chi < 1 || assets > I64MAX) return 0;
  if (!u_mul_ok(assets, RAY)) return 0;
  return (int64_t)((assets * RAY) / chi);
}

static int64_t preview_mint(uint64_t shares, uint64_t chi) {
  if (chi < 1 || shares > I64MAX) return 0;
  if (!u_mul_ok(shares, chi)) return 0;
  return (int64_t)divup(shares * chi, RAY);
}

static int64_t preview_withdraw(uint64_t assets, uint64_t chi) {
  if (chi < 1 || assets > I64MAX) return 0;
  if (!u_mul_ok(assets, RAY)) return 0;
  return (int64_t)divup(assets * RAY, chi);
}

static int64_t roundtrip_loss(uint64_t assets, uint64_t chi) {
  int64_t sh, back;
  sh = to_shares(assets, chi);
  back = to_assets((uint64_t)sh, chi);
  if (back < 0 || (uint64_t)back > assets) return 0;
  return (int64_t)(assets - (uint64_t)back);
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (!u_mul_ok_wrap(1000, 1100) || u_mul(1000, 1100) != 1100000) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(1000, 1100) || u_mul(1000, 1100) != 1100000) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (to_assets(500, 1000) != 500 || to_shares(500, 1000) != 500) return 1;
  if (to_assets(1000, 1100) != 1100 || to_shares(1100, 1100) != 1000) return 1;
  if (to_assets(1, 1100) != 1 || to_shares(1, 1100) != 0) return 1;
  if (preview_mint(1, 1100) != 2 || preview_withdraw(1, 1100) != 1) return 1;
  if (roundtrip_loss(100, 1100) != 1) return 1;
  if (to_assets(1000, 0) != 0 || to_shares(1000, 0) != 0) return 1;
  if (divup(0, 1000) != 0 || divup(1100, 1000) != 2) return 1;
  use_i128 = 1;
  if (to_assets(1000, 1100) != 1100 || preview_mint(1, 1100) != 2) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: sky_susds_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  assets|shares|mint|withdraw|ok|loss X CHI [--i128]\n", stderr);
  fputs("  divup X Y\n", stderr);
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
  uint64_t x, chi;
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
  if (strcmp(cmd, "divup") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", divup(strtoull(argv[2], NULL, 10),
                                  strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (argc >= 4 && (strcmp(cmd, "assets") == 0 || strcmp(cmd, "shares") == 0 ||
                    strcmp(cmd, "mint") == 0 || strcmp(cmd, "withdraw") == 0 ||
                    strcmp(cmd, "ok") == 0 || strcmp(cmd, "loss") == 0)) {
    x = strtoull(argv[2], NULL, 10);
    chi = strtoull(argv[3], NULL, 10);
    if (strcmp(cmd, "assets") == 0) printf("%" PRId64 "\n", to_assets(x, chi));
    else if (strcmp(cmd, "shares") == 0) printf("%" PRId64 "\n", to_shares(x, chi));
    else if (strcmp(cmd, "mint") == 0) printf("%" PRId64 "\n", preview_mint(x, chi));
    else if (strcmp(cmd, "withdraw") == 0) printf("%" PRId64 "\n", preview_withdraw(x, chi));
    else if (strcmp(cmd, "ok") == 0) printf("%d\n", (chi >= 1 && u_mul_ok(x, chi)) ? 1 : 0);
    else printf("%" PRId64 "\n", roundtrip_loss(x, chi));
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
