/*
 * Independent C11 oracle for Maker End cage(ilk)/skim/flow (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect unsigned product (z / y == x, z <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Consensus of wrap-detect XOR __int128 is required before any LIN comparison.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/end.sol (AGPL-3.0-or-later).
 * Original C11. pip.read / vat.grab / vat.ilks are arguments or not executed.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define WAD ((uint64_t)1000000ULL)
#define RAY ((uint64_t)1000000000ULL)

static int use_i128 = 0;

static int u_add_ok_wrap(uint64_t a, uint64_t b) {
  uint64_t z;
  if (a > I64MAX || b > I64MAX) return 0;
  z = a + b;
  if (z > I64MAX) return 0;
  return z >= a;
}

static int u_add_ok_i128(uint64_t a, uint64_t b) {
  __int128 z;
  if (a > I64MAX || b > I64MAX) return 0;
  z = (__int128)a + (__int128)b;
  return z >= 0 && z <= (__int128)I64MAX;
}

static int u_add_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_add_ok_i128(a, b) : u_add_ok_wrap(a, b);
}

static int u_sub_ok(uint64_t a, uint64_t b) {
  if (a > I64MAX || b > I64MAX) return 0;
  return a >= b;
}

static int u_mul_ok_wrap(uint64_t a, uint64_t b) {
  uint64_t z;
  if (a > I64MAX || b > I64MAX) return 0;
  if (b == 0 || a == 0) return 1;
  z = a * b;
  if (z > I64MAX) return 0;
  return z / b == a;
}

static int u_mul_ok_i128(uint64_t a, uint64_t b) {
  __int128 z;
  if (a > I64MAX || b > I64MAX) return 0;
  z = (__int128)a * (__int128)b;
  return z >= 0 && z <= (__int128)I64MAX;
}

static int u_mul_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_mul_ok_i128(a, b) : u_mul_ok_wrap(a, b);
}

static uint64_t u_mul(uint64_t x, uint64_t y) {
  if (!u_mul_ok(x, y)) return 0;
  return use_i128 ? (uint64_t)((__int128)x * (__int128)y) : x * y;
}

static uint64_t u_add(uint64_t x, uint64_t y) {
  if (!u_add_ok(x, y)) return 0;
  return use_i128 ? (uint64_t)((__int128)x + (__int128)y) : x + y;
}

static uint64_t u_sub(uint64_t x, uint64_t y) {
  if (!u_sub_ok(x, y)) return 0;
  return x - y;
}

static uint64_t rmul(uint64_t x, uint64_t y) {
  return u_mul(x, y) / RAY;
}

static uint64_t wdiv(uint64_t x, uint64_t y) {
  if (y == 0) return 0;
  return u_mul(x, WAD) / y;
}

static uint64_t umin(uint64_t x, uint64_t y) { return x <= y ? x : y; }

static int64_t cage_tag(int64_t live, int64_t tag_prev, int64_t par, int64_t pip) {
  if (live != 0 || tag_prev != 0 || par < 0 || pip <= 0) return 0;
  return (int64_t)wdiv((uint64_t)par, (uint64_t)pip);
}

static int skim_owe_ok(int64_t art, int64_t rate, int64_t tag) {
  uint64_t d;
  if (art < 0 || rate < 0 || tag <= 0) return 0;
  if (!u_mul_ok((uint64_t)art, (uint64_t)rate)) return 0;
  d = u_mul((uint64_t)art, (uint64_t)rate) / RAY;
  return u_mul_ok(d, (uint64_t)tag);
}

static int64_t skim_owe(int64_t art, int64_t rate, int64_t tag) {
  uint64_t d;
  if (!skim_owe_ok(art, rate, tag)) return 0;
  d = u_mul((uint64_t)art, (uint64_t)rate) / RAY;
  return (int64_t)rmul(d, (uint64_t)tag);
}

static int64_t skim_wad(int64_t ink, int64_t owe) {
  if (ink < 0 || owe < 0) return 0;
  return (int64_t)umin((uint64_t)ink, (uint64_t)owe);
}

static int64_t skim_gap_next(int64_t gap, int64_t owe, int64_t wad) {
  if (gap < 0 || owe < 0 || wad < 0) return 0;
  return (int64_t)u_add((uint64_t)gap, u_sub((uint64_t)owe, (uint64_t)wad));
}

static int64_t flow_fix(int64_t art_ilk, int64_t rate, int64_t tag, int64_t gap,
                        int64_t debt) {
  uint64_t wad, left, num, den;
  if (debt <= 0 || gap < 0) return 0;
  if (!skim_owe_ok(art_ilk, rate, tag)) return 0;
  wad = (uint64_t)skim_owe(art_ilk, rate, tag);
  if (!u_sub_ok(wad, (uint64_t)gap)) return 0;
  left = wad - (uint64_t)gap;
  if (!u_mul_ok(left, RAY)) return 0;
  num = u_mul(left, RAY);
  den = (uint64_t)debt / RAY;
  if (den == 0) return 0;
  return (int64_t)(num / den);
}

static int64_t cash_out(int64_t wad, int64_t fix) {
  if (wad < 0 || fix < 0) return 0;
  return (int64_t)rmul((uint64_t)wad, (uint64_t)fix);
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (u_add_ok_wrap(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  if (u_mul_ok_wrap(7000000000000000000ULL, 2ULL)) return 1;
  use_i128 = 1;
  if (u_add_ok_i128(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  if (u_mul_ok_i128(7000000000000000000ULL, 2ULL)) return 1;
  use_i128 = 0;
  if (cage_tag(0, 0, 1000000000LL, 2000000000LL) != 500000LL) return 1;
  if (cage_tag(1, 0, 1000000000LL, 2000000000LL) != 0) return 1;
  if (skim_owe(100000000LL, 1000000000LL, 500000LL) != 50000LL) return 1;
  if (skim_wad(100000LL, 50000LL) != 50000LL) return 1;
  if (skim_gap_next(0, 50000LL, 50000LL) != 0) return 1;
  if (skim_wad(30000LL, 50000LL) != 30000LL) return 1;
  if (skim_gap_next(0, 50000LL, 30000LL) != 20000LL) return 1;
  if (flow_fix(100000000LL, 1000000000LL, 500000LL, 20000LL,
               100000000000000000LL) != 300000LL)
    return 1;
  if (cash_out(100000000LL, 300000LL) != 30000LL) return 1;
  use_i128 = 1;
  if (flow_fix(100000000LL, 1000000000LL, 500000LL, 20000LL,
               100000000000000000LL) != 300000LL)
    return 1;
  w = (int64_t)(7000000000000000000ULL + 3000000000000000000ULL);
  if (w != -8446744073709551616LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_end_c11 selftest\n", stderr);
  fputs("  add X Y [--i128]\n", stderr);
  fputs("  sub X Y [--i128]\n", stderr);
  fputs("  mul X Y [--i128]\n", stderr);
  fputs("  wdiv X Y [--i128]\n", stderr);
  fputs("  rmul X Y [--i128]\n", stderr);
  fputs("  cage LIVE TAGPREV PAR PIP [--i128]\n", stderr);
  fputs("  owe ART RATE TAG [--i128]\n", stderr);
  fputs("  wad INK OWE [--i128]\n", stderr);
  fputs("  gap GAP OWE WAD [--i128]\n", stderr);
  fputs("  flow ART RATE TAG GAP DEBT [--i128]\n", stderr);
  fputs("  cash WAD FIX [--i128]\n", stderr);
  fputs("  naive_add A B\n", stderr);
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
  if (strcmp(cmd, "add") == 0 && argc >= 4) {
    printf("%d\n", u_add_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "sub") == 0 && argc >= 4) {
    printf("%d\n", u_sub_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "mul") == 0 && argc >= 4) {
    printf("%d\n", u_mul_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "wdiv") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", wdiv(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "rmul") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n", rmul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "cage") == 0 && argc >= 6) {
    printf("%" PRId64 "\n",
           cage_tag(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "owe") == 0 && argc >= 5) {
    printf("%" PRId64 "\n",
           skim_owe(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "wad") == 0 && argc >= 4) {
    printf("%" PRId64 "\n",
           skim_wad(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "gap") == 0 && argc >= 5) {
    printf("%" PRId64 "\n",
           skim_gap_next(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                         strtoll(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "flow") == 0 && argc >= 7) {
    printf("%" PRId64 "\n",
           flow_fix(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "cash") == 0 && argc >= 4) {
    printf("%" PRId64 "\n",
           cash_out(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "naive_add") == 0 && argc >= 4) {
    uint64_t a = strtoull(argv[2], NULL, 10);
    uint64_t b = strtoull(argv[3], NULL, 10);
    printf("%" PRId64 "\n", (int64_t)(a + b));
    return 0;
  }
  usage();
  return 2;
}
