/*
 * Independent C11 oracle for Maker/Sky Pot.drip/join/exit (uint64-scale).
 *
 * rpow uses half-up (xx + base/2)/base; rmul is floor (x*y)/RAY.
 * Two implementations:
 *   1. unsigned wrap-detect (p/a == b and p <= INT64_MAX) then div
 *   2. __int128 / __uint128 product, fail-closed if quotient > INT64_MAX
 *
 * Consensus between (1) and (2) is required before any LIN comparison on
 * vectors whose intermediates fit uint64. Wide products use (2) only and
 * the Python bigint harness.
 *
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/pot.sol Pot.drip/join/exit
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy pot.sol.
 *
 * Distinct from sUSDS convertToAssets (ERC-4626 chi wrap) and from
 * ExponentialDecrease.price (auction decay): drip accumulates chi and
 * vat.suck(Pie * delta_chi); join requires now==rho; exit does not.
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

static int u_add_ok_wrap(uint64_t a, uint64_t b) {
  uint64_t s;
  if (a > I64MAX || b > I64MAX) return 0;
  s = a + b;
  if (s > I64MAX) return 0;
  return s >= a;
}

static int u_add_ok_i128(uint64_t a, uint64_t b) {
  __int128 s;
  if (a > I64MAX || b > I64MAX) return 0;
  s = (__int128)a + (__int128)b;
  return s >= 0 && s <= (__int128)I64MAX;
}

static int u_sub_ok_wrap(uint64_t a, uint64_t b) {
  if (a > I64MAX || b > I64MAX) return 0;
  return a >= b;
}

static int u_sub_ok_i128(uint64_t a, uint64_t b) {
  __int128 d;
  if (a > I64MAX || b > I64MAX) return 0;
  d = (__int128)a - (__int128)b;
  return d >= 0 && d <= (__int128)I64MAX;
}

static int u_mul_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_mul_ok_i128(a, b) : u_mul_ok_wrap(a, b);
}

static int u_add_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_add_ok_i128(a, b) : u_add_ok_wrap(a, b);
}

static int u_sub_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_sub_ok_i128(a, b) : u_sub_ok_wrap(a, b);
}

static uint64_t muldiv_round_wrap(uint64_t a, uint64_t b, uint64_t d) {
  uint64_t p, t;
  if (d == 0 || !u_mul_ok_wrap(a, b)) return 0;
  p = a * b;
  t = p + (d / 2);
  if (t < p) return 0;
  return t / d;
}

static uint64_t muldiv_round_i128(uint64_t a, uint64_t b, uint64_t d) {
  __uint128_t p, q;
  if (d == 0) return 0;
  p = (__uint128_t)a * (__uint128_t)b;
  q = p + (__uint128_t)(d / 2);
  if (q < p) return 0;
  q = q / (__uint128_t)d;
  if (q > I64MAX) return 0;
  return (uint64_t)q;
}

static uint64_t muldiv_floor_i128(uint64_t a, uint64_t b, uint64_t d) {
  __uint128_t q;
  if (d == 0) return 0;
  q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
  if (q > I64MAX) return 0;
  return (uint64_t)q;
}

static uint64_t muldiv_round(uint64_t a, uint64_t b, uint64_t d) {
  return use_i128 ? muldiv_round_i128(a, b, d) : muldiv_round_wrap(a, b, d);
}

static uint64_t muldiv_floor(uint64_t a, uint64_t b, uint64_t d) {
  if (use_i128) return muldiv_floor_i128(a, b, d);
  if (d == 0 || !u_mul_ok_wrap(a, b)) return 0;
  return (a * b) / d;
}

static uint64_t rpow(uint64_t x, uint64_t n, uint64_t b) {
  uint64_t z, odd;
  if (b == 0) return 0;
  if (n == 0) return b;
  if (x == 0) return 0;
  z = (n % 2 == 0) ? b : x;
  n = n / 2;
  while (n > 0) {
    x = muldiv_round(x, x, b);
    odd = n % 2;
    if (odd) z = muldiv_round(z, x, b);
    n = n / 2;
  }
  return z;
}

typedef struct {
  uint64_t dsr, chi, rho, now_ts, pie_total;
} DripIn;

typedef struct {
  uint64_t now_ts, rho, chi, pie_user, pie_total, wad;
} JoinIn;

typedef struct {
  uint64_t chi, pie_user, pie_total, wad;
} ExitIn;

static int drip_eval(DripIn p, int want, int64_t *out) {
  uint64_t rp, tmp, delta, suck;
  *out = 0;
  if (p.dsr > I64MAX || p.chi > I64MAX || p.rho > I64MAX || p.now_ts > I64MAX ||
      p.pie_total > I64MAX)
    return 0;
  if (p.now_ts < p.rho) return 0;
  rp = rpow(p.dsr, p.now_ts - p.rho, RAY);
  tmp = muldiv_floor(rp, p.chi, RAY);
  if (!u_sub_ok(tmp, p.chi)) return 0;
  delta = tmp - p.chi;
  if (!u_mul_ok(p.pie_total, delta)) return 0;
  suck = p.pie_total * delta;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)tmp;
  else if (want == 2) *out = (int64_t)delta;
  else if (want == 3) *out = (int64_t)suck;
  else *out = 0;
  return 1;
}

static int join_eval(JoinIn p, int want, int64_t *out) {
  uint64_t rad;
  *out = 0;
  if (p.now_ts > I64MAX || p.rho > I64MAX || p.chi > I64MAX ||
      p.pie_user > I64MAX || p.pie_total > I64MAX || p.wad > I64MAX)
    return 0;
  if (p.now_ts != p.rho) return 0;
  if (!u_mul_ok(p.chi, p.wad)) return 0;
  if (!u_add_ok(p.pie_user, p.wad) || !u_add_ok(p.pie_total, p.wad)) return 0;
  rad = p.chi * p.wad;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)rad;
  else if (want == 2) *out = (int64_t)(p.pie_user + p.wad);
  else if (want == 3) *out = (int64_t)(p.pie_total + p.wad);
  else *out = 0;
  return 1;
}

static int exit_eval(ExitIn p, int want, int64_t *out) {
  uint64_t rad;
  *out = 0;
  if (p.chi > I64MAX || p.pie_user > I64MAX || p.pie_total > I64MAX ||
      p.wad > I64MAX)
    return 0;
  if (!u_mul_ok(p.chi, p.wad)) return 0;
  if (!u_sub_ok(p.pie_user, p.wad) || !u_sub_ok(p.pie_total, p.wad)) return 0;
  rad = p.chi * p.wad;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)rad;
  else if (want == 2) *out = (int64_t)(p.pie_user - p.wad);
  else if (want == 3) *out = (int64_t)(p.pie_total - p.wad);
  else *out = 0;
  return 1;
}

static int64_t drip_field(DripIn p, int want) {
  int64_t v = 0;
  if (!drip_eval(p, want, &v)) return 0;
  return v;
}

static int64_t join_field(JoinIn p, int want) {
  int64_t v = 0;
  if (!join_eval(p, want, &v)) return 0;
  return v;
}

static int64_t exit_field(ExitIn p, int want) {
  int64_t v = 0;
  if (!exit_eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  DripIn d;
  JoinIn j;
  ExitIn e;
  int64_t w;
  use_i128 = 0;
  if (rpow(3, 2, 2) != 5) return 1;
  if (rpow(1010000000ULL, 1, RAY) != 1010000000ULL) return 1;
  if (rpow(1010000000ULL, 2, RAY) != 1020100000ULL) return 1;
  if (rpow(1010000000ULL, 3, RAY) != 1030301000ULL) return 1;
  d = (DripIn){RAY, RAY, 10, 10, 1000};
  if (drip_field(d, 0) != 1 || drip_field(d, 1) != 1000000000LL) return 1;
  if (drip_field(d, 3) != 0) return 1;
  d = (DripIn){1010000000ULL, RAY, 0, 1, 1000};
  if (drip_field(d, 1) != 1010000000LL || drip_field(d, 3) != 10000000000LL)
    return 1;
  d = (DripIn){1010000000ULL, RAY, 0, 2, 1000};
  if (drip_field(d, 1) != 1020100000LL || drip_field(d, 3) != 20100000000LL)
    return 1;
  d.now_ts = 9;
  d.rho = 10;
  if (drip_field(d, 0) != 0) return 1;
  j = (JoinIn){10, 10, RAY, 0, 0, 1000};
  if (join_field(j, 0) != 1 || join_field(j, 1) != 1000000000000LL) return 1;
  j.now_ts = 11;
  if (join_field(j, 0) != 0) return 1;
  e = (ExitIn){RAY, 1000, 1000, 400};
  if (exit_field(e, 0) != 1 || exit_field(e, 1) != 400000000000LL) return 1;
  use_i128 = 1;
  d = (DripIn){1010000000ULL, RAY, 0, 2, 1000};
  if (drip_field(d, 1) != 1020100000LL || drip_field(d, 3) != 20100000000LL)
    return 1;
  if (rpow(1010000000ULL, 2, RAY) != 1020100000ULL) return 1;
  w = (int64_t)((uint64_t)10000000000LL * (uint64_t)1000000000LL);
  if (w != -8446744073709551616LL) return 1;
  if (u_mul_ok_i128(10000000000ULL, 1000000000ULL)) return 1;
  puts("PASS");
  return 0;
}

static int last_i128(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++)
    if (strcmp(argv[i], "--i128") == 0) return 1;
  return 0;
}

static int want_of(const char *cmd) {
  if (strcmp(cmd, "ok") == 0) return 0;
  if (strcmp(cmd, "chi") == 0 || strcmp(cmd, "rad") == 0) return 1;
  if (strcmp(cmd, "delta") == 0 || strcmp(cmd, "user") == 0) return 2;
  if (strcmp(cmd, "suck") == 0 || strcmp(cmd, "total") == 0) return 3;
  return -1;
}

static void usage(void) {
  fputs("usage: maker_pot_c11 selftest\n", stderr);
  fputs("  rpow X N B [--i128]\n", stderr);
  fputs("  rmul X Y [--i128]\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  drip ok|chi|delta|suck DSR CHI RHO NOW PIE [--i128]\n", stderr);
  fputs("  join ok|rad|user|total NOW RHO CHI USER TOTAL WAD [--i128]\n", stderr);
  fputs("  exit ok|rad|user|total CHI USER TOTAL WAD [--i128]\n", stderr);
  fputs("  naive_mul A B\n", stderr);
}

int main(int argc, char **argv) {
  const char *cmd;
  int w;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "rpow") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n", rpow(strtoull(argv[2], NULL, 10),
                                 strtoull(argv[3], NULL, 10),
                                 strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "rmul") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", muldiv_floor(strtoull(argv[2], NULL, 10),
                                         strtoull(argv[3], NULL, 10), RAY));
    return 0;
  }
  if (strcmp(cmd, "mul") == 0 && argc >= 4) {
    uint64_t a = strtoull(argv[2], NULL, 10);
    uint64_t b = strtoull(argv[3], NULL, 10);
    {
      uint64_t p = u_mul_ok(a, b) ? a * b : 0;
      printf("%" PRIu64 "\n", p);
    }
    return 0;
  }
  if (strcmp(cmd, "drip") == 0 && argc >= 8) {
    DripIn p;
    w = want_of(argv[2]);
    if (w < 0) {
      usage();
      return 2;
    }
    p.dsr = strtoull(argv[3], NULL, 10);
    p.chi = strtoull(argv[4], NULL, 10);
    p.rho = strtoull(argv[5], NULL, 10);
    p.now_ts = strtoull(argv[6], NULL, 10);
    p.pie_total = strtoull(argv[7], NULL, 10);
    printf("%" PRId64 "\n", drip_field(p, w));
    return 0;
  }
  if (strcmp(cmd, "join") == 0 && argc >= 9) {
    JoinIn p;
    w = want_of(argv[2]);
    if (w < 0) {
      usage();
      return 2;
    }
    p.now_ts = strtoull(argv[3], NULL, 10);
    p.rho = strtoull(argv[4], NULL, 10);
    p.chi = strtoull(argv[5], NULL, 10);
    p.pie_user = strtoull(argv[6], NULL, 10);
    p.pie_total = strtoull(argv[7], NULL, 10);
    p.wad = strtoull(argv[8], NULL, 10);
    printf("%" PRId64 "\n", join_field(p, w));
    return 0;
  }
  if (strcmp(cmd, "exit") == 0 && argc >= 7) {
    ExitIn p;
    w = want_of(argv[2]);
    if (w < 0) {
      usage();
      return 2;
    }
    p.chi = strtoull(argv[3], NULL, 10);
    p.pie_user = strtoull(argv[4], NULL, 10);
    p.pie_total = strtoull(argv[5], NULL, 10);
    p.wad = strtoull(argv[6], NULL, 10);
    printf("%" PRId64 "\n", exit_field(p, w));
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
