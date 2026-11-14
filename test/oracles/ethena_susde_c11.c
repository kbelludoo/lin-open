/*
 * Independent C11 oracle for Ethena StakedUSDe convert / vest (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect signed product (p/a == b, p >= 0, result <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: ethena-labs/code4arena-contest StakedUSDe.sol
 * getUnvestedAmount / totalAssets / ERC4626 convert (GPL-3.0).
 * This oracle is original C11 and does not copy StakedUSDe.sol.
 *
 * Distinct from Sky sUSDS (chi/RAY): 8-hour linear vest, MIN_SHARES, no offset.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define PERIOD 8ULL
#define MIN_SHARES 1000ULL

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

static uint64_t muldiv(uint64_t a, uint64_t b, uint64_t d) {
  if (d < 1 || !u_mul_ok(a, b)) return 0;
  if (use_i128) return (uint64_t)(((__int128)a * (__int128)b) / (__int128)d);
  return (a * b) / d;
}

static uint64_t divup(uint64_t x, uint64_t y) {
  if (y < 1 || x == 0) return 0;
  return ((x - 1) / y) + 1;
}

static uint64_t muldiv_ceil(uint64_t a, uint64_t b, uint64_t d) {
  if (d < 1 || !u_mul_ok(a, b)) return 0;
  if (use_i128) return divup((uint64_t)((__int128)a * (__int128)b), d);
  return divup(a * b, d);
}

static int time_ok(uint64_t now, uint64_t last_ts) {
  if (now > I64MAX || last_ts > I64MAX) return 0;
  return now >= last_ts;
}

static uint64_t unvested(uint64_t now, uint64_t last_ts, uint64_t vest) {
  uint64_t elapsed, remaining;
  if (!time_ok(now, last_ts) || vest > I64MAX) return 0;
  elapsed = now - last_ts;
  if (elapsed >= PERIOD) return 0;
  remaining = PERIOD - elapsed;
  return muldiv(remaining, vest, PERIOD);
}

static uint64_t total_assets(uint64_t balance, uint64_t now, uint64_t last_ts, uint64_t vest) {
  uint64_t u;
  if (balance > I64MAX || !time_ok(now, last_ts)) return 0;
  u = unvested(now, last_ts, vest);
  if (balance < u) return 0;
  return balance - u;
}

static uint64_t to_shares(uint64_t assets, uint64_t supply, uint64_t ta) {
  if (assets > I64MAX || supply > I64MAX || ta > I64MAX) return 0;
  if (assets == 0) return 0;
  if (supply == 0) return assets;
  if (ta == 0) return 0;
  return muldiv(assets, supply, ta);
}

static uint64_t to_assets(uint64_t shares, uint64_t supply, uint64_t ta) {
  if (shares > I64MAX || supply > I64MAX || ta > I64MAX) return 0;
  if (shares == 0) return 0;
  if (supply == 0) return shares;
  if (ta == 0) return 0;
  return muldiv(shares, ta, supply);
}

static uint64_t preview_mint(uint64_t shares, uint64_t supply, uint64_t ta) {
  if (shares > I64MAX || supply > I64MAX || ta > I64MAX) return 0;
  if (shares == 0) return 0;
  if (supply == 0) return shares;
  if (ta == 0) return 0;
  return muldiv_ceil(shares, ta, supply);
}

static uint64_t preview_withdraw(uint64_t assets, uint64_t supply, uint64_t ta) {
  if (assets > I64MAX || supply > I64MAX || ta > I64MAX) return 0;
  if (assets == 0) return 0;
  if (supply == 0) return assets;
  if (ta == 0) return 0;
  return muldiv_ceil(assets, supply, ta);
}

static int min_shares_ok(uint64_t ns) {
  if (ns > I64MAX) return 0;
  if (ns == 0) return 1;
  return ns >= MIN_SHARES;
}

static int rewards_ok(uint64_t now, uint64_t last_ts, uint64_t vest, uint64_t amount) {
  if (amount < 1 || amount > I64MAX) return 0;
  if (!time_ok(now, last_ts)) return 0;
  return unvested(now, last_ts, vest) == 0;
}

static uint64_t deposit_shares(uint64_t assets, uint64_t balance, uint64_t now,
                              uint64_t last_ts, uint64_t vest, uint64_t supply) {
  uint64_t ta, sh;
  ta = total_assets(balance, now, last_ts, vest);
  sh = to_shares(assets, supply, ta);
  if (sh < 1) return 0;
  if (!u_mul_ok(supply, 1) || supply > I64MAX - sh) return 0;
  if (!min_shares_ok(supply + sh)) return 0;
  return sh;
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (unvested(2, 0, 800) != 600) return 1;
  if (unvested(0, 0, 800) != 800) return 1;
  if (unvested(8, 0, 800) != 0) return 1;
  if (total_assets(10800, 2, 0, 800) != 10200) return 1;
  if (to_shares(1020, 10000, 10200) != 1000) return 1;
  if (to_assets(1000, 10000, 10200) != 1020) return 1;
  if (preview_mint(1, 10000, 10200) != 2) return 1;
  if (preview_withdraw(1, 10000, 10200) != 1) return 1;
  use_i128 = 1;
  if (unvested(2, 0, 800) != 600) return 1;
  if (to_shares(1020, 10000, 10200) != 1000) return 1;
  if (deposit_shares(1020, 10800, 2, 0, 800, 10000) != 1000) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: ethena_susde_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  unvested NOW LAST VEST [--i128]\n", stderr);
  fputs("  total BALANCE NOW LAST VEST [--i128]\n", stderr);
  fputs("  shares ASSETS SUPPLY TA [--i128]\n", stderr);
  fputs("  assets SHARES SUPPLY TA [--i128]\n", stderr);
  fputs("  mint SHARES SUPPLY TA [--i128]\n", stderr);
  fputs("  withdraw ASSETS SUPPLY TA [--i128]\n", stderr);
  fputs("  minshares NS\n", stderr);
  fputs("  rewards NOW LAST VEST AMOUNT [--i128]\n", stderr);
  fputs("  deposit ASSETS BALANCE NOW LAST VEST SUPPLY [--i128]\n", stderr);
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
  if (strcmp(cmd, "unvested") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", unvested(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                     strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "total") == 0 && argc >= 6) {
    printf("%" PRIu64 "\n", total_assets(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                         strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "shares") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", to_shares(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                      strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "assets") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", to_assets(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                      strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "mint") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", preview_mint(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                         strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "withdraw") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", preview_withdraw(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                             strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "minshares") == 0 && argc >= 3) {
    printf("%d\n", min_shares_ok(strtoull(argv[2], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "rewards") == 0 && argc >= 6) {
    printf("%d\n", rewards_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                              strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "deposit") == 0 && argc >= 8) {
    printf("%" PRIu64 "\n", deposit_shares(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                           strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                           strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
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
