/*
 * Independent C11 oracle for Maker/Sky vat.flux (uint64-scale gem transfer).
 *
 * Two unsigned add implementations:
 *   1. wrapping-detect: s = x + y; require s >= x && s <= INT64_MAX
 *   2. __uint128_t: (x + y) <= INT64_MAX
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol flux / unsigned _add/_sub / wish
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy vat.sol.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

static int use_i128 = 0;

static int u_add_ok_wrap(uint64_t x, uint64_t y) {
  uint64_t s;
  if (x > I64MAX || y > I64MAX) return 0;
  s = x + y;
  return (s >= x) && (s <= I64MAX);
}

static int u_add_ok_i128(uint64_t x, uint64_t y) {
  if (x > I64MAX || y > I64MAX) return 0;
  return ((__uint128_t)x + (__uint128_t)y) <= (__uint128_t)I64MAX;
}

static int u_add_ok(uint64_t x, uint64_t y) {
  return use_i128 ? u_add_ok_i128(x, y) : u_add_ok_wrap(x, y);
}

static uint64_t u_add(uint64_t x, uint64_t y) {
  return u_add_ok(x, y) ? x + y : 0;
}

static int u_sub_ok(uint64_t x, uint64_t y) {
  return x >= y && x <= I64MAX && y <= I64MAX;
}

static uint64_t u_sub(uint64_t x, uint64_t y) {
  return u_sub_ok(x, y) ? x - y : 0;
}

typedef struct {
  uint64_t src, dst, wad, wish_src;
} FluxIn;

static int parse_in(char **a, FluxIn *p) {
  p->src = strtoull(a[0], NULL, 10);
  p->dst = strtoull(a[1], NULL, 10);
  p->wad = strtoull(a[2], NULL, 10);
  p->wish_src = strtoull(a[3], NULL, 10);
  return 1;
}

static int flux_ok(FluxIn p) {
  if (p.src > I64MAX || p.dst > I64MAX || p.wad > I64MAX) return 0;
  if (p.wish_src != 1) return 0;
  if (!u_sub_ok(p.src, p.wad)) return 0;
  if (!u_add_ok(p.dst, p.wad)) return 0;
  return 1;
}

static int selftest(void) {
  FluxIn p;
  int w, i;
  use_i128 = 0;
  w = u_add_ok_wrap(2000000000ULL, 1000000000ULL);
  use_i128 = 1;
  i = u_add_ok_i128(2000000000ULL, 1000000000ULL);
  if (!w || !i) return 1;
  use_i128 = 0;
  w = u_add_ok_wrap(7000000000000000000ULL, 3000000000000000000ULL);
  use_i128 = 1;
  i = u_add_ok_i128(7000000000000000000ULL, 3000000000000000000ULL);
  if (w || i) return 1;
  p = (FluxIn){5000000000ULL, 3000000000ULL, 1000000000ULL, 1};
  use_i128 = 0;
  if (flux_ok(p) != 1) return 1;
  use_i128 = 1;
  if (flux_ok(p) != 1) return 1;
  use_i128 = 0;
  p.wish_src = 0;
  if (flux_ok(p) != 0) return 1;
  if (u_add(7000000000000000000ULL, 3000000000000000000ULL) != 0) return 1;
  if (u_sub(3000000000ULL, 1000000000ULL) != 2000000000ULL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_vat_flux_c11 selftest\n", stderr);
  fputs("  sub|add X Y [--i128]\n", stderr);
  fputs("  ok|new_src|new_dst|conserved|moved SRC DST WAD WISH [--i128]\n", stderr);
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
  FluxIn p;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "sub") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n",
           u_sub(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "add") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n",
           u_add(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (argc >= 6 &&
      (strcmp(cmd, "ok") == 0 || strcmp(cmd, "new_src") == 0 ||
       strcmp(cmd, "new_dst") == 0 || strcmp(cmd, "conserved") == 0 ||
       strcmp(cmd, "moved") == 0)) {
    parse_in(argv + 2, &p);
    if (strcmp(cmd, "ok") == 0) {
      printf("%d\n", flux_ok(p));
      return 0;
    }
    if (!flux_ok(p)) {
      printf("0\n");
      return 0;
    }
    if (strcmp(cmd, "new_src") == 0)
      printf("%" PRIu64 "\n", u_sub(p.src, p.wad));
    else if (strcmp(cmd, "new_dst") == 0)
      printf("%" PRIu64 "\n", u_add(p.dst, p.wad));
    else if (strcmp(cmd, "conserved") == 0)
      printf("%d\n", u_add(u_sub(p.src, p.wad), u_add(p.dst, p.wad)) ==
                         u_add(p.src, p.dst));
    else
      printf("%" PRIu64 "\n", p.wad);
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
