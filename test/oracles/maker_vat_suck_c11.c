/*
 * Independent C11 oracle for Maker/Sky vat.suck (uint64-scale, RAY'=1e9).
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_vat_suck.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol suck/_add(uint,uint)
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy vat.sol.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d, uint64_t *q_out,
                            uint64_t *r_out, int *ov_out) {
  uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
  uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge,
      need_borrow;
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
      if (i >= 64)
        ov = 1;
      else
        q = q | (1ULL << i);
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

static int u_sub_ok(uint64_t x, uint64_t y) {
  return x >= y && x <= I64MAX && y <= I64MAX;
}

static uint64_t u_sub(uint64_t x, uint64_t y) {
  if (!u_sub_ok(x, y)) return 0;
  return x - y;
}

static int u_add_ok(uint64_t x, uint64_t y) {
  uint64_t s;
  if (x > I64MAX || y > I64MAX) return 0;
  s = x + y;
  if (s < x) return 0;
  if (s > I64MAX) return 0;
  return 1;
}

static uint64_t u_add(uint64_t x, uint64_t y) {
  if (!u_add_ok(x, y)) return 0;
  return x + y;
}

static int auth_ok(uint64_t auth) { return auth == 1; }

static int suck_ok(uint64_t sin_u, uint64_t dai_v, uint64_t vice, uint64_t debt,
                   uint64_t rad, uint64_t auth) {
  if (sin_u > I64MAX || dai_v > I64MAX || vice > I64MAX || debt > I64MAX ||
      rad > I64MAX)
    return 0;
  if (!auth_ok(auth)) return 0;
  return u_add_ok(sin_u, rad) && u_add_ok(dai_v, rad) && u_add_ok(vice, rad) &&
         u_add_ok(debt, rad);
}

static uint64_t minted(uint64_t sin_u, uint64_t dai_v, uint64_t vice,
                       uint64_t debt, uint64_t rad, uint64_t auth) {
  return suck_ok(sin_u, dai_v, vice, debt, rad, auth) ? rad : 0;
}

static int deltas_equal(uint64_t sin_u, uint64_t dai_v, uint64_t vice,
                        uint64_t debt, uint64_t rad, uint64_t auth) {
  if (!suck_ok(sin_u, dai_v, vice, debt, rad, auth)) return 0;
  return u_add(sin_u, rad) - sin_u == rad && u_add(dai_v, rad) - dai_v == rad &&
         u_add(vice, rad) - vice == rad && u_add(debt, rad) - debt == rad;
}

static int inverse_ok(uint64_t sin_u, uint64_t dai_v, uint64_t vice,
                      uint64_t debt, uint64_t rad, uint64_t auth) {
  if (!suck_ok(sin_u, dai_v, vice, debt, rad, auth)) return 0;
  return u_sub(u_add(sin_u, rad), rad) == sin_u &&
         u_sub(u_add(dai_v, rad), rad) == dai_v &&
         u_sub(u_add(vice, rad), rad) == vice &&
         u_sub(u_add(debt, rad), rad) == debt;
}

static int selftest(void) {
  uint64_t q1, q2;
  int ov1 = 0, ov2 = 0;
  uint64_t e18 = 1000000000000000000ULL;
  uint64_t e18_2 = 2000000000000000000ULL;
  uint64_t e18_3 = 3000000000000000000ULL;
  uint64_t e18_5 = 5000000000000000000ULL;
  q1 = muldiv_i128(100, 200, 50, &ov1);
  q2 = muldiv_limbs(100, 200, 50, &ov2);
  if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
  q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
  q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
  if (!ov1 || !ov2 || q1 != 0 || q2 != 0) return 1;
  use_limbs = 0;
  if (suck_ok(e18_2, e18_3, e18_2, e18_5, e18, 1) != 1) return 1;
  use_limbs = 1;
  if (suck_ok(e18_2, e18_3, e18_2, e18_5, e18, 1) != 1) return 1;
  use_limbs = 0;
  if (suck_ok(e18_2, e18_3, e18_2, e18_5, e18, 0) != 0) return 1;
  if (u_add(e18_2, e18) != e18_3) return 1;
  if (u_sub(e18_3, e18) != e18_2) return 1;
  if (u_add(7000000000000000000ULL, 3000000000000000000ULL) != 0) return 1;
  if (deltas_equal(e18_2, e18_3, e18_2, e18_5, e18, 1) != 1) return 1;
  if (inverse_ok(e18_2, e18_3, e18_2, e18_5, e18, 1) != 1) return 1;
  if (minted(e18_2, e18_3, e18_2, e18_5, e18_2, 1) != e18_2) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_vat_suck_c11 selftest\n", stderr);
  fputs("  muldiv|muldiv_rem A B D [--limbs]\n", stderr);
  fputs("  sub|add X Y [--limbs]\n", stderr);
  fputs("  new_sin|new_dai|new_vice|new_debt X RAD [--limbs]\n", stderr);
  fputs("  restore NEW RAD [--limbs]\n", stderr);
  fputs("  minted SIN DAI VICE DEBT RAD AUTH [--limbs]\n", stderr);
  fputs("  deltas SIN DAI VICE DEBT RAD AUTH [--limbs]\n", stderr);
  fputs("  inverse SIN DAI VICE DEBT RAD AUTH [--limbs]\n", stderr);
  fputs("  ok SIN DAI VICE DEBT RAD AUTH [--limbs]\n", stderr);
  fputs("  auth A\n", stderr);
  fputs("  naive_mul|naive_add A B\n", stderr);
}

static int last_limbs(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++) {
    if (strcmp(argv[i], "--limbs") == 0) return 1;
  }
  return 0;
}

int main(int argc, char **argv) {
  const char *cmd;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_limbs = last_limbs(argc, argv);
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
  if ((strcmp(cmd, "sub") == 0 || strcmp(cmd, "restore") == 0) && argc >= 4) {
    printf("%" PRIu64 "\n",
           u_sub(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if ((strcmp(cmd, "add") == 0 || strcmp(cmd, "new_sin") == 0 ||
       strcmp(cmd, "new_dai") == 0 || strcmp(cmd, "new_vice") == 0 ||
       strcmp(cmd, "new_debt") == 0) &&
      argc >= 4) {
    printf("%" PRIu64 "\n",
           u_add(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "minted") == 0 && argc >= 8) {
    printf("%" PRIu64 "\n",
           minted(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                  strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "deltas") == 0 && argc >= 8) {
    printf("%d\n",
           deltas_equal(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                        strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "inverse") == 0 && argc >= 8) {
    printf("%d\n",
           inverse_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                      strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "ok") == 0 && argc >= 8) {
    printf("%d\n",
           suck_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                   strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                   strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "auth") == 0 && argc >= 3) {
    printf("%d\n", auth_ok(strtoull(argv[2], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "naive_mul") == 0 && argc >= 4) {
    int64_t a = strtoll(argv[2], NULL, 10);
    int64_t b = strtoll(argv[3], NULL, 10);
    printf("%" PRId64 "\n", (int64_t)((uint64_t)a * (uint64_t)b));
    return 0;
  }
  if (strcmp(cmd, "naive_add") == 0 && argc >= 4) {
    int64_t a = strtoll(argv[2], NULL, 10);
    int64_t b = strtoll(argv[3], NULL, 10);
    printf("%" PRId64 "\n", (int64_t)((uint64_t)a + (uint64_t)b));
    return 0;
  }
  usage();
  return 2;
}
