/*
 * Independent C11 oracle for Maker/Sky vat.slip (uint64-scale auth gem wad).
 *
 * Signed _add(uint x, int y) at uint64 scale, two implementations:
 *   1. wrapping-detect unsigned add/sub of |wad|
 *   2. __int128: (int128)x + (int128)y in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol slip / signed _add / auth
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy vat.sol.
 *
 * Distinct from vat.flux: wards required, signed wad, single usr slot, no wish.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

static int use_i128 = 0;

static uint64_t i64_mag(int64_t y) {
  if (y >= 0) return (uint64_t)y;
  return ~((uint64_t)y) + 1ULL;
}

static int u_add_ok_wrap(uint64_t x, uint64_t y) {
  uint64_t s;
  if (x > I64MAX || y > I64MAX) return 0;
  s = x + y;
  return (s >= x) && (s <= I64MAX);
}

static int u_sub_ok(uint64_t x, uint64_t y) {
  return x >= y && x <= I64MAX && y <= I64MAX;
}

static int s_add_ok_wrap(uint64_t x, int64_t y) {
  if (x > I64MAX) return 0;
  if (y >= 0) return u_add_ok_wrap(x, (uint64_t)y);
  return u_sub_ok(x, i64_mag(y));
}

static int s_add_ok_i128(uint64_t x, int64_t y) {
  __int128 z;
  if (x > I64MAX) return 0;
  z = (__int128)x + (__int128)y;
  return z >= 0 && z <= (__int128)I64MAX;
}

static int s_add_ok(uint64_t x, int64_t y) {
  return use_i128 ? s_add_ok_i128(x, y) : s_add_ok_wrap(x, y);
}

static int64_t s_add(uint64_t x, int64_t y) {
  if (!s_add_ok(x, y)) return 0;
  return (int64_t)((int64_t)x + y);
}

typedef struct {
  uint64_t gem;
  int64_t wad;
  uint64_t wards;
} SlipIn;

static int parse_in(char **a, SlipIn *p) {
  p->gem = strtoull(a[0], NULL, 10);
  p->wad = strtoll(a[1], NULL, 10);
  p->wards = strtoull(a[2], NULL, 10);
  return 1;
}

static int slip_ok(SlipIn p) {
  if (p.gem > I64MAX) return 0;
  if (p.wards != 1) return 0;
  return s_add_ok(p.gem, p.wad);
}

static int64_t new_gem(SlipIn p) {
  if (!slip_ok(p)) return 0;
  return s_add(p.gem, p.wad);
}

static int64_t join_amt(SlipIn p) {
  if (!slip_ok(p) || p.wad < 1) return 0;
  return p.wad;
}

static int64_t exit_amt(SlipIn p) {
  if (!slip_ok(p) || p.wad >= 0) return 0;
  return (int64_t)i64_mag(p.wad);
}

static int selftest(void) {
  SlipIn p;
  int w, i;
  use_i128 = 0;
  w = s_add_ok_wrap(5000000000ULL, 1000000000LL);
  use_i128 = 1;
  i = s_add_ok_i128(5000000000ULL, 1000000000LL);
  if (!w || !i) return 1;
  use_i128 = 0;
  w = s_add_ok_wrap(5000000000ULL, -1000000000LL);
  use_i128 = 1;
  i = s_add_ok_i128(5000000000ULL, -1000000000LL);
  if (!w || !i) return 1;
  use_i128 = 0;
  w = s_add_ok_wrap(7000000000000000000ULL, 3000000000000000000LL);
  use_i128 = 1;
  i = s_add_ok_i128(7000000000000000000ULL, 3000000000000000000LL);
  if (w || i) return 1;
  p = (SlipIn){5000000000ULL, 1000000000LL, 1};
  use_i128 = 0;
  if (slip_ok(p) != 1 || new_gem(p) != 6000000000LL) return 1;
  use_i128 = 1;
  if (slip_ok(p) != 1 || new_gem(p) != 6000000000LL) return 1;
  use_i128 = 0;
  p.wad = -1000000000LL;
  if (slip_ok(p) != 1 || new_gem(p) != 4000000000LL) return 1;
  p.wards = 0;
  if (slip_ok(p) != 0) return 1;
  p = (SlipIn){1000000000ULL, -2000000000LL, 1};
  if (slip_ok(p) != 0) return 1;
  if (s_add(7000000000000000000ULL, 3000000000000000000LL) != 0) return 1;
  if (s_add_ok(0ULL, INT64_MIN) != 0) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_vat_slip_c11 selftest\n", stderr);
  fputs("  add X Y [--i128]\n", stderr);
  fputs("  ok|new|applied|join|exit GEM WAD WARDS [--i128]\n", stderr);
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
  SlipIn p;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "add") == 0 && argc >= 4) {
    printf("%" PRId64 "\n",
           s_add(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
    return 0;
  }
  if (argc >= 5 &&
      (strcmp(cmd, "ok") == 0 || strcmp(cmd, "new") == 0 ||
       strcmp(cmd, "applied") == 0 || strcmp(cmd, "join") == 0 ||
       strcmp(cmd, "exit") == 0)) {
    parse_in(argv + 2, &p);
    if (strcmp(cmd, "ok") == 0) {
      printf("%d\n", slip_ok(p));
      return 0;
    }
    if (!slip_ok(p)) {
      printf("0\n");
      return 0;
    }
    if (strcmp(cmd, "new") == 0)
      printf("%" PRId64 "\n", new_gem(p));
    else if (strcmp(cmd, "applied") == 0)
      printf("%" PRId64 "\n", p.wad);
    else if (strcmp(cmd, "join") == 0)
      printf("%" PRId64 "\n", join_amt(p));
    else
      printf("%" PRId64 "\n", exit_amt(p));
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
