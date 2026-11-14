/*
 * Independent C11 oracle for Maker/Sky GemJoin.join/exit (uint64-scale).
 *
 * add/sub two implementations:
 *   1. wrapping-detect unsigned (s >= a; a >= b; result <= INT64_MAX)
 *   2. __int128 sum / difference in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/join.sol GemJoin join/exit
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy join.sol.
 *
 * Distinct from DaiJoin (wad*RAY rad + mint/burn):
 * join requires live==1, exit after cage is ok, vat.slip ±wad + ERC20.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

static int use_i128 = 0;

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

static int u_add_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_add_ok_i128(a, b) : u_add_ok_wrap(a, b);
}

static int u_sub_ok(uint64_t a, uint64_t b) {
  return use_i128 ? u_sub_ok_i128(a, b) : u_sub_ok_wrap(a, b);
}

typedef struct {
  uint64_t op, live, usr_gem, sender_gem, adapter, sender_tok, usr_tok, wad;
} GjIn;

static int parse_in(char **a, GjIn *p) {
  p->op = strtoull(a[0], NULL, 10);
  p->live = strtoull(a[1], NULL, 10);
  p->usr_gem = strtoull(a[2], NULL, 10);
  p->sender_gem = strtoull(a[3], NULL, 10);
  p->adapter = strtoull(a[4], NULL, 10);
  p->sender_tok = strtoull(a[5], NULL, 10);
  p->usr_tok = strtoull(a[6], NULL, 10);
  p->wad = strtoull(a[7], NULL, 10);
  return 1;
}

static int eval(GjIn p, int want, int64_t *out) {
  uint64_t n_usr, n_sg, n_ad, n_st, n_ut;
  *out = 0;
  if (p.op != 0 && p.op != 1) return 0;
  if (p.usr_gem > I64MAX || p.sender_gem > I64MAX || p.adapter > I64MAX ||
      p.sender_tok > I64MAX || p.usr_tok > I64MAX || p.wad > I64MAX)
    return 0;
  if (p.op == 0 && p.live != 1) return 0;
  n_usr = p.usr_gem;
  n_sg = p.sender_gem;
  n_ad = p.adapter;
  n_st = p.sender_tok;
  n_ut = p.usr_tok;
  if (p.op == 0) {
    if (!u_add_ok(p.usr_gem, p.wad)) return 0;
    if (!u_add_ok(p.adapter, p.wad)) return 0;
    if (!u_sub_ok(p.sender_tok, p.wad)) return 0;
    n_usr = p.usr_gem + p.wad;
    n_ad = p.adapter + p.wad;
    n_st = p.sender_tok - p.wad;
  } else {
    if (!u_sub_ok(p.sender_gem, p.wad)) return 0;
    if (!u_sub_ok(p.adapter, p.wad)) return 0;
    if (!u_add_ok(p.usr_tok, p.wad)) return 0;
    n_sg = p.sender_gem - p.wad;
    n_ad = p.adapter - p.wad;
    n_ut = p.usr_tok + p.wad;
  }
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)n_usr;
  else if (want == 2) *out = (int64_t)n_sg;
  else if (want == 3) *out = (int64_t)n_ad;
  else if (want == 4) *out = (int64_t)n_st;
  else if (want == 5) *out = (int64_t)n_ut;
  else *out = 0;
  return 1;
}

static int64_t field(GjIn p, int want) {
  int64_t v = 0;
  if (!eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  GjIn p;
  int64_t w, i;
  use_i128 = 0;
  if (u_add_ok_wrap(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  use_i128 = 1;
  if (u_add_ok_i128(7000000000000000000ULL, 3000000000000000000ULL)) return 1;
  p = (GjIn){0, 1, 5000000000ULL, 0, 0, 1000, 7, 1000};
  use_i128 = 0;
  if (field(p, 0) != 1 || field(p, 1) != 5000001000LL) return 1;
  if (field(p, 3) != 1000 || field(p, 4) != 0 || field(p, 5) != 7) return 1;
  use_i128 = 1;
  if (field(p, 1) != 5000001000LL || field(p, 3) != 1000) return 1;
  p.live = 0;
  use_i128 = 0;
  if (field(p, 0) != 0) return 1;
  p = (GjIn){1, 1, 0, 1000, 1000, 0, 7, 1000};
  if (field(p, 0) != 1 || field(p, 2) != 0 || field(p, 5) != 1007) return 1;
  p.live = 0;
  if (field(p, 0) != 1) return 1;
  p = (GjIn){0, 1, 5000000000ULL, 0, 0, 999, 7, 1000};
  if (field(p, 0) != 0) return 1;
  w = (int64_t)((uint64_t)7000000000000000000LL + (uint64_t)3000000000000000000LL);
  i = -8446744073709551616LL;
  if (w != i) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_gemjoin_c11 selftest\n", stderr);
  fputs("  add A B [--i128]\n", stderr);
  fputs("  ok|usr|sender|adapter|stok|utok OP LIVE UG SG AD ST UT WAD [--i128]\n", stderr);
  fputs("  naive_add A B\n", stderr);
}

static int last_i128(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++)
    if (strcmp(argv[i], "--i128") == 0) return 1;
  return 0;
}

static int want_of(const char *cmd) {
  if (strcmp(cmd, "ok") == 0) return 0;
  if (strcmp(cmd, "usr") == 0) return 1;
  if (strcmp(cmd, "sender") == 0) return 2;
  if (strcmp(cmd, "adapter") == 0) return 3;
  if (strcmp(cmd, "stok") == 0) return 4;
  if (strcmp(cmd, "utok") == 0) return 5;
  return -1;
}

int main(int argc, char **argv) {
  const char *cmd;
  GjIn p;
  int w;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_i128 = last_i128(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "add") == 0 && argc >= 4) {
    uint64_t a = strtoull(argv[2], NULL, 10);
    uint64_t b = strtoull(argv[3], NULL, 10);
    printf("%d\n", u_add_ok(a, b));
    return 0;
  }
  w = want_of(cmd);
  if (w >= 0 && argc >= 10) {
    parse_in(argv + 2, &p);
    printf("%" PRId64 "\n", field(p, w));
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
