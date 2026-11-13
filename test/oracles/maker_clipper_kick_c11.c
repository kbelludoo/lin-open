/*
 * Independent C11 oracle for Maker/Sky Clipper.kick (uint64-scale).
 *
 * mul/add two implementations:
 *   1. wrapping-detect unsigned (p/a == b and p <= INT64_MAX; s >= a)
 *   2. __int128 product / sum in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/clip.sol kick / rmul / rdiv / wmul / add
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy clip.sol.
 *
 * Distinct from clipper.take (buy) and dog.bark (liquidation size):
 * wards-auth auction start, breaker level 1, OSM val*BLN/par * buf, chip/tip suck.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define WAD 1000ULL
#define RAY 1000000ULL
#define BLN 1000ULL

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

static int u_mul_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_mul_ok_i128(a, b) : u_mul_ok_wrap(a, b);
}

static int u_add_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_add_ok_i128(a, b) : u_add_ok_wrap(a, b);
}

static uint64_t u_mul(uint64_t a, uint64_t b) {
  if (!u_mul_ok(a, b)) return 0;
  return a * b;
}

typedef struct {
  uint64_t tab, lot, usr, kicks, val, par, buf, tip, chip, auth, stopped;
} KickIn;

static int parse_in(char **a, KickIn *p) {
  p->tab = strtoull(a[0], NULL, 10);
  p->lot = strtoull(a[1], NULL, 10);
  p->usr = strtoull(a[2], NULL, 10);
  p->kicks = strtoull(a[3], NULL, 10);
  p->val = strtoull(a[4], NULL, 10);
  p->par = strtoull(a[5], NULL, 10);
  p->buf = strtoull(a[6], NULL, 10);
  p->tip = strtoull(a[7], NULL, 10);
  p->chip = strtoull(a[8], NULL, 10);
  p->auth = strtoull(a[9], NULL, 10);
  p->stopped = strtoull(a[10], NULL, 10);
  return 1;
}

static int eval(KickIn p, int want, int64_t *out) {
  uint64_t id, prod1, feed, top, coin, w, sucks, go;
  *out = 0;
  if (p.auth != 1) return 0;
  if (p.stopped >= 1) return 0;
  if (p.tab < 1 || p.lot < 1 || p.usr != 1) return 0;
  if (p.kicks > I64MAX) return 0;
  if (!u_add_ok(p.kicks, 1)) return 0;
  id = p.kicks + 1;
  if (id < 1) return 0;
  if (p.par < 1) return 0;
  if (!u_mul_ok(p.val, BLN)) return 0;
  prod1 = p.val * BLN;
  if (!u_mul_ok(prod1, RAY)) return 0;
  feed = (prod1 * RAY) / p.par;
  if (!u_mul_ok(feed, p.buf)) return 0;
  top = (feed * p.buf) / RAY;
  if (top < 1) return 0;
  coin = 0;
  sucks = 0;
  go = (p.tip > 0 || p.chip > 0);
  if (go) {
    if (!u_mul_ok(p.tab, p.chip)) return 0;
    w = (p.tab * p.chip) / WAD;
    if (!u_add_ok(p.tip, w)) return 0;
    coin = p.tip + w;
    sucks = 1;
  }
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)id;
  else if (want == 2) *out = (int64_t)top;
  else if (want == 3) *out = (int64_t)coin;
  else if (want == 4) *out = (int64_t)sucks;
  else if (want == 5) *out = (int64_t)feed;
  else *out = 0;
  return 1;
}

static int64_t field(KickIn p, int want) {
  int64_t v = 0;
  if (!eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  KickIn p;
  int64_t w, i;
  use_i128 = 0;
  if (!u_mul_ok_wrap(2000, 1000) || u_mul(2000, 1000) != 2000000) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(2000, 1000)) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  p = (KickIn){50000, 1000, 1, 7, 2000, 1000000, 1100000, 100, 10, 1, 0};
  use_i128 = 0;
  if (field(p, 0) != 1 || field(p, 1) != 8 || field(p, 2) != 2200000) return 1;
  if (field(p, 3) != 600 || field(p, 4) != 1 || field(p, 5) != 2000000) return 1;
  use_i128 = 1;
  if (field(p, 2) != 2200000 || field(p, 3) != 600) return 1;
  p.tip = 0;
  use_i128 = 0;
  if (field(p, 3) != 500) return 1;
  p.chip = 0;
  p.tip = 100;
  if (field(p, 3) != 100) return 1;
  p.tip = 0;
  if (field(p, 4) != 0 || field(p, 0) != 1) return 1;
  p = (KickIn){50000, 1000, 1, 7, 2000, 2000000, 1100000, 100, 10, 1, 0};
  if (field(p, 2) != 1100000) return 1;
  p.par = 1000000;
  p.buf = 1000000;
  if (field(p, 2) != 2000000) return 1;
  p.tab = 0;
  if (field(p, 0) != 0) return 1;
  p.tab = 50000;
  p.stopped = 1;
  if (field(p, 0) != 0) return 1;
  p.stopped = 0;
  p.auth = 0;
  if (field(p, 0) != 0) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  i = 2553255926290448384LL;
  if (w != i) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_clipper_kick_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  ok|id|top|coin|sucks|feed TAB LOT USR KICKS VAL PAR BUF TIP CHIP AUTH STOPPED [--i128]\n", stderr);
  fputs("  naive_mul A B\n", stderr);
}

static int last_i128(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++)
    if (strcmp(argv[i], "--i128") == 0) return 1;
  return 0;
}

static int want_of(const char *cmd) {
  if (strcmp(cmd, "ok") == 0) return 0;
  if (strcmp(cmd, "id") == 0) return 1;
  if (strcmp(cmd, "top") == 0) return 2;
  if (strcmp(cmd, "coin") == 0) return 3;
  if (strcmp(cmd, "sucks") == 0) return 4;
  if (strcmp(cmd, "feed") == 0) return 5;
  return -1;
}

int main(int argc, char **argv) {
  const char *cmd;
  KickIn p;
  int w;
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
  w = want_of(cmd);
  if (w >= 0 && argc >= 13) {
    parse_in(argv + 2, &p);
    printf("%" PRId64 "\n", field(p, w));
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
