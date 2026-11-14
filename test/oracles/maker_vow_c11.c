/*
 * Independent C11 oracle for Maker/Sky Vow heal/kiss/flop/flap (uint64-scale).
 *
 * add two implementations:
 *   1. wrapping-detect unsigned sum (z >= a, z <= INT64_MAX)
 *   2. __int128 sum in [0, INT64_MAX]
 *
 * Consensus of wrap-detect XOR __int128 is required before any LIN comparison.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vow.sol (AGPL-3.0-or-later).
 * Original C11. Distinct from vat.heal: vat.dai/sin and kick are arguments
 * or not executed. add/sub underflow/overflow fail-close.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

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

static uint64_t lvw_add(uint64_t x, uint64_t y) {
  if (!u_add_ok(x, y)) return 0;
  return use_i128 ? (uint64_t)((__int128)x + (__int128)y) : x + y;
}

static uint64_t lvw_sub(uint64_t x, uint64_t y) {
  if (!u_sub_ok(x, y)) return 0;
  return x - y;
}

static int unqueued_ok(uint64_t vat_sin, uint64_t queued_sin, uint64_t ash) {
  uint64_t t;
  if (!u_sub_ok(vat_sin, queued_sin)) return 0;
  t = vat_sin - queued_sin;
  return u_sub_ok(t, ash);
}

static uint64_t unqueued(uint64_t vat_sin, uint64_t queued_sin, uint64_t ash) {
  if (!unqueued_ok(vat_sin, queued_sin, ash)) return 0;
  return (vat_sin - queued_sin) - ash;
}

static int64_t heal_ok(int64_t vat_dai, int64_t vat_sin, int64_t queued_sin,
                       int64_t ash, int64_t rad) {
  uint64_t uq;
  if (rad < 0 || vat_dai < 0 || vat_sin < 0 || queued_sin < 0 || ash < 0)
    return 0;
  if (!unqueued_ok((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash))
    return 0;
  if ((uint64_t)vat_dai < (uint64_t)rad) return 0;
  uq = unqueued((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash);
  if (uq < (uint64_t)rad) return 0;
  return 1;
}

static int64_t kiss_ok(int64_t vat_dai, int64_t ash, int64_t rad) {
  if (rad < 0 || vat_dai < 0 || ash < 0) return 0;
  if ((uint64_t)ash < (uint64_t)rad) return 0;
  if ((uint64_t)vat_dai < (uint64_t)rad) return 0;
  return 1;
}

static int64_t kiss_ash_next(int64_t vat_dai, int64_t ash, int64_t rad) {
  if (!kiss_ok(vat_dai, ash, rad)) return 0;
  return (int64_t)lvw_sub((uint64_t)ash, (uint64_t)rad);
}

static int64_t flop_ok(int64_t vat_dai, int64_t vat_sin, int64_t queued_sin,
                       int64_t ash, int64_t sump) {
  uint64_t uq;
  if (vat_dai != 0 || sump < 0 || vat_sin < 0 || queued_sin < 0 || ash < 0)
    return 0;
  if (!unqueued_ok((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash))
    return 0;
  uq = unqueued((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash);
  if (uq < (uint64_t)sump) return 0;
  if (!u_add_ok((uint64_t)ash, (uint64_t)sump)) return 0;
  return 1;
}

static int64_t flop_ash_next(int64_t vat_dai, int64_t vat_sin, int64_t queued_sin,
                             int64_t ash, int64_t sump) {
  if (!flop_ok(vat_dai, vat_sin, queued_sin, ash, sump)) return 0;
  return (int64_t)lvw_add((uint64_t)ash, (uint64_t)sump);
}

static uint64_t flap_need(uint64_t vat_sin, uint64_t bump, uint64_t hump) {
  uint64_t inner = lvw_add(vat_sin, bump);
  if (vat_sin != 0 && bump != 0 && inner == 0) return 0;
  return lvw_add(inner, hump);
}

static int64_t flap_ok(int64_t vat_dai, int64_t vat_sin, int64_t queued_sin,
                       int64_t ash, int64_t bump, int64_t hump) {
  uint64_t uq, need;
  if (vat_dai < 0 || vat_sin < 0 || queued_sin < 0 || ash < 0 || bump < 0 ||
      hump < 0)
    return 0;
  if (!unqueued_ok((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash))
    return 0;
  uq = unqueued((uint64_t)vat_sin, (uint64_t)queued_sin, (uint64_t)ash);
  if (uq != 0) return 0;
  need = flap_need((uint64_t)vat_sin, (uint64_t)bump, (uint64_t)hump);
  if (need == 0 && (vat_sin != 0 || bump != 0 || hump != 0)) return 0;
  if ((uint64_t)vat_dai < need) return 0;
  return 1;
}

static int selftest(void) {
  int64_t w;
  use_i128 = 0;
  if (u_add_ok_wrap(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  use_i128 = 1;
  if (u_add_ok_i128(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  use_i128 = 0;
  if (heal_ok(5000000000LL, 10000000000LL, 3000000000LL, 1000000000LL,
              5000000000LL) != 1)
    return 1;
  if (heal_ok(5000000000LL, 10000000000LL, 3000000000LL, 1000000000LL,
              6000000000LL) != 0)
    return 1;
  if (kiss_ok(3000000000LL, 2000000000LL, 2000000000LL) != 1) return 1;
  if (kiss_ash_next(3000000000LL, 2000000000LL, 2000000000LL) != 0) return 1;
  if (flop_ok(0, 10000000000LL, 3000000000LL, 1000000000LL, 2000000000LL) != 1)
    return 1;
  if (flop_ash_next(0, 10000000000LL, 3000000000LL, 1000000000LL, 2000000000LL) !=
      3000000000LL)
    return 1;
  if (flap_ok(10000000000LL, 0, 0, 0, 1000000000LL, 2000000000LL) != 1) return 1;
  if (flap_ok(2000000000LL, 0, 0, 0, 1000000000LL, 2000000000LL) != 0) return 1;
  if (flap_ok(2000000000LL, 0, 0, 0, 1000000000LL, 0) != 1) return 1;
  if (flap_ok(10000000000LL, 3000000000LL, 0, 0, 1000000000LL, 2000000000LL) != 0)
    return 1;
  if (flap_ok(5000000000LL, 0, 0, 0, 1000000000LL, 2000000000LL) != 1) return 1;
  if (flap_ok(5000000000LL, 3000000000LL, 3000000000LL, 0, 1000000000LL,
              2000000000LL) != 0)
    return 1;
  use_i128 = 1;
  if (heal_ok(5000000000LL, 10000000000LL, 3000000000LL, 1000000000LL,
              5000000000LL) != 1)
    return 1;
  w = (int64_t)(7000000000000000000ULL + 3000000000000000000ULL);
  if (w != -8446744073709551616LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_vow_c11 selftest\n", stderr);
  fputs("  add X Y [--i128]\n", stderr);
  fputs("  sub X Y [--i128]\n", stderr);
  fputs("  unqueued SIN QS ASH [--i128]\n", stderr);
  fputs("  heal DAI SIN QS ASH RAD [--i128]\n", stderr);
  fputs("  kiss DAI ASH RAD [--i128]\n", stderr);
  fputs("  kiss_ash DAI ASH RAD [--i128]\n", stderr);
  fputs("  flop DAI SIN QS ASH SUMP [--i128]\n", stderr);
  fputs("  flop_ash DAI SIN QS ASH SUMP [--i128]\n", stderr);
  fputs("  flap DAI SIN QS ASH BUMP HUMP [--i128]\n", stderr);
  fputs("  flap_need SIN BUMP HUMP [--i128]\n", stderr);
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
  if (strcmp(cmd, "unqueued") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n",
           unqueued(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "heal") == 0 && argc >= 7) {
    printf("%" PRId64 "\n",
           heal_ok(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                   strtoll(argv[6], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "kiss") == 0 && argc >= 5) {
    printf("%" PRId64 "\n",
           kiss_ok(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "kiss_ash") == 0 && argc >= 5) {
    printf("%" PRId64 "\n",
           kiss_ash_next(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                         strtoll(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "flop") == 0 && argc >= 7) {
    printf("%" PRId64 "\n",
           flop_ok(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                   strtoll(argv[6], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "flop_ash") == 0 && argc >= 7) {
    printf("%" PRId64 "\n",
           flop_ash_next(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                         strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                         strtoll(argv[6], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "flap") == 0 && argc >= 8) {
    printf("%" PRId64 "\n",
           flap_ok(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                   strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "flap_need") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n",
           flap_need(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10)));
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
