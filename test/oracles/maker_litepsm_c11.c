/*
 * Independent C11 oracle for Maker/Sky DssLitePsm sellGem/buyGem (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect signed product (p/a == b, p >= 0, result <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Fee is (dai/wad)*tin + (dai%wad)*tin/wad, matching Solidity floor(dai*tin/wad)
 * without a wrapping 128-bit product. Consensus of wrap-detect XOR __int128
 * is required before any LIN comparison. Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: sky-ecosystem/dss-lite-psm src/DssLitePsm.sol
 * _sellGem / _buyGem (AGPL-3.0-or-later). This oracle is original C11.
 *
 * Distinct from DaiJoin (wad→rad) and GemJoin (ilk slip): gem*to18, tin/tout
 * WAD' fee, HALTED sentinel -1 (not type(uint256).max).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define WAD_P 1000000000ULL

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

static uint64_t psm_pow10(uint64_t n) {
  uint64_t p = 1, i;
  if (n > 9) return 0;
  for (i = 0; i < n; i++) {
    if (!u_mul_ok(p, 10)) return 0;
    p *= 10;
  }
  return p;
}

static uint64_t psm_to18(uint64_t scale_dec, uint64_t gem_dec) {
  if (scale_dec > 9 || gem_dec > scale_dec) return 0;
  return psm_pow10(scale_dec - gem_dec);
}

static uint64_t psm_gem_wad(uint64_t gem, uint64_t to18) {
  if (!u_mul_ok(gem, to18)) return 0;
  return use_i128 ? (uint64_t)((__int128)gem * (__int128)to18) : gem * to18;
}

static uint64_t psm_fee(uint64_t dai, uint64_t tin, uint64_t wad) {
  uint64_t q, r, hi, lo;
  if (wad == 0 || tin > wad) return 0;
  if (tin == 0) return 0;
  q = dai / wad;
  r = dai % wad;
  if (!u_mul_ok(q, tin) || !u_mul_ok(r, tin)) return 0;
  hi = use_i128 ? (uint64_t)((__int128)q * (__int128)tin) : q * tin;
  lo = (use_i128 ? (uint64_t)((__int128)r * (__int128)tin) : r * tin) / wad;
  if (!u_add_ok(hi, lo)) return 0;
  return hi + lo;
}

static int64_t psm_sell(int64_t gem, int64_t to18, int64_t tin, int64_t wad) {
  uint64_t dai, fee;
  if (tin == -1) return 0;
  if (gem < 0 || to18 < 0 || tin < 0 || wad <= 0) return 0;
  dai = psm_gem_wad((uint64_t)gem, (uint64_t)to18);
  if (dai == 0) return 0;
  if (tin == 0) return (int64_t)dai;
  fee = psm_fee(dai, (uint64_t)tin, (uint64_t)wad);
  if (dai < fee) return 0;
  return (int64_t)(dai - fee);
}

static int64_t psm_buy(int64_t gem, int64_t to18, int64_t tout, int64_t wad) {
  uint64_t dai, fee;
  if (tout == -1) return 0;
  if (gem < 0 || to18 < 0 || tout < 0 || wad <= 0) return 0;
  dai = psm_gem_wad((uint64_t)gem, (uint64_t)to18);
  if (dai == 0) return 0;
  if (tout == 0) return (int64_t)dai;
  fee = psm_fee(dai, (uint64_t)tout, (uint64_t)wad);
  if (!u_add_ok(dai, fee)) return 0;
  return (int64_t)(dai + fee);
}

static int64_t psm_sell_nofee(int64_t kissed, int64_t gem, int64_t to18, int64_t wad) {
  if (kissed != 1) return 0;
  return psm_sell(gem, to18, 0, wad);
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (psm_to18(9, 6) != 1000) return 1;
  if (psm_gem_wad(1000000, 1000) != WAD_P) return 1;
  if (psm_sell(1000000, 1000, 0, (int64_t)WAD_P) != (int64_t)WAD_P) return 1;
  if (psm_sell(1000000, 1000, 1000000, (int64_t)WAD_P) != 999000000) return 1;
  if (psm_buy(1000000, 1000, 1000000, (int64_t)WAD_P) != 1001000000) return 1;
  if (psm_sell(1000000, 1000, (int64_t)WAD_P, (int64_t)WAD_P) != 0) return 1;
  if (psm_sell(1000000, 1000, -1, (int64_t)WAD_P) != 0) return 1;
  if (psm_sell_nofee(0, 1000000, 1000, (int64_t)WAD_P) != 0) return 1;
  if (psm_sell_nofee(1, 1000000, 1000, (int64_t)WAD_P) != (int64_t)WAD_P) return 1;
  use_i128 = 1;
  if (psm_sell(1000000, 1000, 1000000, (int64_t)WAD_P) != 999000000) return 1;
  if (psm_buy(1000000, 1000, 1000000, (int64_t)WAD_P) != 1001000000) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_litepsm_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  add A B [--i128]\n", stderr);
  fputs("  to18 SCALE GEMDEC [--i128]\n", stderr);
  fputs("  gem GEM TO18 [--i128]\n", stderr);
  fputs("  fee DAI TIN WAD [--i128]\n", stderr);
  fputs("  sell GEM TO18 TIN WAD [--i128]\n", stderr);
  fputs("  buy GEM TO18 TOUT WAD [--i128]\n", stderr);
  fputs("  sell_nofee KISSED GEM TO18 WAD [--i128]\n", stderr);
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
  if (strcmp(cmd, "to18") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", psm_to18(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "gem") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", psm_gem_wad(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "fee") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n",
           psm_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                   strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "sell") == 0 && argc >= 6) {
    printf("%" PRId64 "\n",
           psm_sell(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "buy") == 0 && argc >= 6) {
    printf("%" PRId64 "\n",
           psm_buy(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "sell_nofee") == 0 && argc >= 6) {
    printf("%" PRId64 "\n",
           psm_sell_nofee(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                          strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10)));
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
