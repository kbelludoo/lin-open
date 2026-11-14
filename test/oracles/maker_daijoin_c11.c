/*
 * Independent C11 oracle for Maker/Sky DaiJoin.join/exit (uint64-scale).
 *
 * mul/add/sub two implementations:
 *   1. wrapping-detect unsigned (p/a == b and p <= INT64_MAX; s >= a; a >= b)
 *   2. __int128 product / sum / difference in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/join.sol DaiJoin mul/join/exit
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy join.sol.
 *
 * Distinct from vat.move (rad transfer) and GemJoin (ilk slip):
 * wad→rad via RAY'=1e9, join ignores live, exit requires live==1.
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

static uint64_t u_mul(uint64_t a, uint64_t b) {
  if (!u_mul_ok(a, b)) return 0;
  return a * b;
}

typedef struct {
  uint64_t op, live, from_dai, to_dai, token, wad;
} DjIn;

static int parse_in(char **a, DjIn *p) {
  p->op = strtoull(a[0], NULL, 10);
  p->live = strtoull(a[1], NULL, 10);
  p->from_dai = strtoull(a[2], NULL, 10);
  p->to_dai = strtoull(a[3], NULL, 10);
  p->token = strtoull(a[4], NULL, 10);
  p->wad = strtoull(a[5], NULL, 10);
  return 1;
}

static int eval(DjIn p, int want, int64_t *out) {
  uint64_t rad, new_from, new_to, new_token;
  *out = 0;
  if (p.op != 0 && p.op != 1) return 0;
  if (p.from_dai > I64MAX || p.to_dai > I64MAX || p.token > I64MAX || p.wad > I64MAX)
    return 0;
  if (p.op == 1 && p.live != 1) return 0;
  if (!u_mul_ok(RAY, p.wad)) return 0;
  rad = RAY * p.wad;
  if (!u_sub_ok(p.from_dai, rad)) return 0;
  if (!u_add_ok(p.to_dai, rad)) return 0;
  new_token = p.token;
  if (p.op == 0) {
    if (!u_sub_ok(p.token, p.wad)) return 0;
    new_token = p.token - p.wad;
  } else {
    if (!u_add_ok(p.token, p.wad)) return 0;
    new_token = p.token + p.wad;
  }
  new_from = p.from_dai - rad;
  new_to = p.to_dai + rad;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)rad;
  else if (want == 2) *out = (int64_t)new_from;
  else if (want == 3) *out = (int64_t)new_to;
  else if (want == 4) *out = (int64_t)new_token;
  else *out = 0;
  return 1;
}

static int64_t field(DjIn p, int want) {
  int64_t v = 0;
  if (!eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  DjIn p;
  int64_t w, i;
  use_i128 = 0;
  if (!u_mul_ok_wrap(1000, RAY) || u_mul(1000, RAY) != 1000000000000ULL) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(1000, RAY)) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(10000000000ULL, 1000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(10000000000ULL, 1000000000ULL)) return 1;
  p = (DjIn){0, 1, 2000000000000ULL, 5, 1000, 1000};
  use_i128 = 0;
  if (field(p, 0) != 1 || field(p, 1) != 1000000000000LL) return 1;
  if (field(p, 2) != 1000000000000LL || field(p, 3) != 1000000000005LL) return 1;
  if (field(p, 4) != 0) return 1;
  use_i128 = 1;
  if (field(p, 1) != 1000000000000LL || field(p, 3) != 1000000000005LL) return 1;
  p.live = 0;
  use_i128 = 0;
  if (field(p, 0) != 1) return 1;
  p = (DjIn){1, 1, 1000000000000ULL, 0, 7, 1000};
  if (field(p, 0) != 1 || field(p, 2) != 0 || field(p, 3) != 1000000000000LL) return 1;
  if (field(p, 4) != 1007) return 1;
  p.live = 0;
  if (field(p, 0) != 0) return 1;
  p = (DjIn){0, 1, 1, 5, 1000, 1000};
  if (field(p, 0) != 0) return 1;
  w = (int64_t)((uint64_t)10000000000LL * (uint64_t)1000000000LL);
  i = -8446744073709551616LL;
  if (w != i) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_daijoin_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  ok|rad|from|to|token OP LIVE FROM TO TOKEN WAD [--i128]\n", stderr);
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
  if (strcmp(cmd, "rad") == 0) return 1;
  if (strcmp(cmd, "from") == 0) return 2;
  if (strcmp(cmd, "to") == 0) return 3;
  if (strcmp(cmd, "token") == 0) return 4;
  return -1;
}

int main(int argc, char **argv) {
  const char *cmd;
  DjIn p;
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
  if (w >= 0 && argc >= 8) {
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
