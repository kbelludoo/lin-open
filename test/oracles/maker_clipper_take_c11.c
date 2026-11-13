/*
 * Independent C11 oracle for Maker/Sky Clipper.take (uint64-scale).
 *
 * slice*price two implementations:
 *   1. wrapping-detect unsigned mul (p/a == b and p <= INT64_MAX)
 *   2. __int128: (int128)a * (int128)b in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/clip.sol take / min / mul / chost
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy clip.sol.
 *
 * Distinct from vat.slip/flux/move: public Dutch-auction buy, chost dust floor,
 * tab cap, circuit breaker level 3. chip/tip are kick/redo, not take.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

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

typedef struct {
  uint64_t tab, lot, amt, maxp, price, chost, running, done, stopped;
} TakeIn;

static int parse_in(char **a, TakeIn *p) {
  p->tab = strtoull(a[0], NULL, 10);
  p->lot = strtoull(a[1], NULL, 10);
  p->amt = strtoull(a[2], NULL, 10);
  p->maxp = strtoull(a[3], NULL, 10);
  p->price = strtoull(a[4], NULL, 10);
  p->chost = strtoull(a[5], NULL, 10);
  p->running = strtoull(a[6], NULL, 10);
  p->done = strtoull(a[7], NULL, 10);
  p->stopped = strtoull(a[8], NULL, 10);
  return 1;
}

static int eval(TakeIn p, int want, int64_t *out) {
  uint64_t slice, owe, tab_cap, partial, rem, new_tab, new_lot;
  *out = 0;
  if (p.stopped >= 3) return 0;
  if (p.running != 1) return 0;
  if (p.done != 0) return 0;
  if (p.price < 1) return 0;
  if (p.tab > I64MAX || p.lot > I64MAX || p.amt > I64MAX || p.chost > I64MAX)
    return 0;
  if (p.maxp < p.price) return 0;
  slice = p.lot < p.amt ? p.lot : p.amt;
  if (!u_mul_ok(slice, p.price)) return 0;
  owe = slice * p.price;
  tab_cap = p.tab < owe;
  if (tab_cap) {
    owe = p.tab;
    slice = owe / p.price;
  }
  partial = 0;
  if (!tab_cap && owe < p.tab && slice < p.lot) partial = 1;
  if (partial) {
    rem = p.tab - owe;
    if (rem < p.chost) {
      if (p.tab <= p.chost) return 0;
      owe = p.tab - p.chost;
      slice = owe / p.price;
    }
  }
  new_tab = p.tab - owe;
  new_lot = p.lot - slice;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)slice;
  else if (want == 2) *out = (int64_t)owe;
  else if (want == 3) *out = (int64_t)new_tab;
  else if (want == 4) *out = (int64_t)new_lot;
  else if (want == 5) *out = new_lot == 0 ? 1 : 0;
  else if (want == 6) *out = (new_lot != 0 && new_tab == 0) ? 1 : 0;
  else *out = 0;
  return 1;
}

static int64_t field(TakeIn p, int want) {
  int64_t v = 0;
  if (!eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  TakeIn p;
  int64_t w, i;
  use_i128 = 0;
  if (!u_mul_ok_wrap(1000, 100) || u_mul(1000, 100) != 100000) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(1000, 100)) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  p = (TakeIn){200000, 1000, 2000, 100, 100, 1, 1, 0, 0};
  use_i128 = 0;
  if (field(p, 0) != 1 || field(p, 1) != 1000 || field(p, 2) != 100000) return 1;
  use_i128 = 1;
  if (field(p, 1) != 1000 || field(p, 4) != 0) return 1;
  p = (TakeIn){100000, 1000, 1000, 200, 200, 1, 1, 0, 0};
  use_i128 = 0;
  if (field(p, 1) != 500 || field(p, 2) != 100000 || field(p, 6) != 1) return 1;
  p = (TakeIn){100000, 1000, 400, 100, 100, 70000, 1, 0, 0};
  if (field(p, 1) != 300 || field(p, 2) != 30000 || field(p, 3) != 70000) return 1;
  p = (TakeIn){50000, 1000, 400, 100, 100, 70000, 1, 0, 0};
  if (field(p, 0) != 0) return 1;
  p.stopped = 3;
  p.tab = 200000;
  p.chost = 1;
  p.amt = 2000;
  if (field(p, 0) != 0) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  i = 2553255926290448384LL;
  if (w != i) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_clipper_take_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  ok|slice|owe|new_tab|new_lot|clears|returns TAB LOT AMT MAXP PRICE CHOST RUNNING DONE STOPPED [--i128]\n", stderr);
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
  if (strcmp(cmd, "slice") == 0) return 1;
  if (strcmp(cmd, "owe") == 0) return 2;
  if (strcmp(cmd, "new_tab") == 0) return 3;
  if (strcmp(cmd, "new_lot") == 0) return 4;
  if (strcmp(cmd, "clears") == 0) return 5;
  if (strcmp(cmd, "returns") == 0) return 6;
  return -1;
}

int main(int argc, char **argv) {
  const char *cmd;
  TakeIn p;
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
  if (w >= 0 && argc >= 11) {
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
