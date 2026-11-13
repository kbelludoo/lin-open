/*
 * Independent C11 oracle for Maker/Sky Dog.bark (uint64-scale).
 *
 * ink*spot, art*rate, room*WAD, dart*rate, due*chop two implementations:
 *   1. wrapping-detect unsigned mul (p/a == b and p <= INT64_MAX)
 *   2. __int128: (int128)a * (int128)b in [0, INT64_MAX]
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/dog.sol bark / min / mul / Hole / Dirt
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy dog.sol.
 *
 * Distinct from clipper.take (auction buy) and vat.slip/flux/move.
 * bark is public (not wards-auth). chip/tip are clipper.kick/redo, not bark.
 * vat.grab / vow.fess / ClipperLike.kick are return values / next_id, not calls.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define WAD 1000ULL

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

static int u_add_ok(uint64_t a, uint64_t b) {
  uint64_t s;
  if (a > I64MAX || b > I64MAX) return 0;
  s = a + b;
  return s >= a && s <= I64MAX;
}

typedef struct {
  uint64_t live, ink, art, rate, spot, dust;
  uint64_t g_hole, g_dirt, i_hole, i_dirt, chop, next_id;
} BarkIn;

static int parse_in(char **a, BarkIn *p) {
  p->live = strtoull(a[0], NULL, 10);
  p->ink = strtoull(a[1], NULL, 10);
  p->art = strtoull(a[2], NULL, 10);
  p->rate = strtoull(a[3], NULL, 10);
  p->spot = strtoull(a[4], NULL, 10);
  p->dust = strtoull(a[5], NULL, 10);
  p->g_hole = strtoull(a[6], NULL, 10);
  p->g_dirt = strtoull(a[7], NULL, 10);
  p->i_hole = strtoull(a[8], NULL, 10);
  p->i_dirt = strtoull(a[9], NULL, 10);
  p->chop = strtoull(a[10], NULL, 10);
  p->next_id = strtoull(a[11], NULL, 10);
  return 1;
}

static int eval(BarkIn p, int want, int64_t *out) {
  uint64_t room, dart, dink, due, tab, left_ink, left_art, g2, i2;
  *out = 0;
  if (p.live != 1) return 0;
  if (p.ink > I64MAX || p.art < 1 || p.art > I64MAX) return 0;
  if (p.rate < 1 || p.spot > I64MAX || p.dust > I64MAX) return 0;
  if (p.g_hole > I64MAX || p.g_dirt > I64MAX) return 0;
  if (p.i_hole > I64MAX || p.i_dirt > I64MAX) return 0;
  if (p.chop < 1 || p.next_id > I64MAX) return 0;
  if (!u_mul_ok(p.ink, p.spot) || !u_mul_ok(p.art, p.rate)) return 0;
  if (p.spot < 1 || !(p.ink * p.spot < p.art * p.rate)) return 0;
  if (!(p.g_hole > p.g_dirt && p.i_hole > p.i_dirt)) return 0;
  room = p.g_hole - p.g_dirt;
  if (p.i_hole - p.i_dirt < room) room = p.i_hole - p.i_dirt;
  if (!u_mul_ok(room, WAD)) return 0;
  dart = (room * WAD) / p.rate / p.chop;
  if (p.art < dart) dart = p.art;
  if (p.art > dart) {
    if (!u_mul_ok(p.art - dart, p.rate)) return 0;
    if ((p.art - dart) * p.rate < p.dust) {
      dart = p.art;
    } else {
      if (!u_mul_ok(dart, p.rate)) return 0;
      if (dart * p.rate < p.dust) return 0;
    }
  }
  if (!u_mul_ok(p.ink, dart)) return 0;
  dink = (p.ink * dart) / p.art;
  if (dink < 1) return 0;
  if (!u_mul_ok(dart, p.rate)) return 0;
  due = dart * p.rate;
  if (!u_mul_ok(due, p.chop)) return 0;
  tab = (due * p.chop) / WAD;
  if (!u_add_ok(p.g_dirt, tab) || !u_add_ok(p.i_dirt, tab)) return 0;
  left_ink = p.ink - dink;
  left_art = p.art - dart;
  g2 = p.g_dirt + tab;
  i2 = p.i_dirt + tab;
  if (want == 0) {
    *out = 1;
    return 1;
  }
  if (want == 1) *out = (int64_t)dart;
  else if (want == 2) *out = (int64_t)dink;
  else if (want == 3) *out = (int64_t)due;
  else if (want == 4) *out = (int64_t)tab;
  else if (want == 5) *out = (int64_t)left_ink;
  else if (want == 6) *out = (int64_t)left_art;
  else if (want == 7) *out = (int64_t)g2;
  else if (want == 8) *out = (int64_t)i2;
  else if (want == 9) *out = (int64_t)p.next_id;
  else if (want == 10) *out = (left_ink == 0 && left_art == 0) ? 1 : 0;
  else if (want == 11) *out = left_art > 0 ? 1 : 0;
  else *out = 0;
  return 1;
}

static int64_t field(BarkIn p, int want) {
  int64_t v = 0;
  if (!eval(p, want, &v)) return 0;
  return v;
}

static int selftest(void) {
  BarkIn p;
  int64_t w, i;
  use_i128 = 0;
  if (!u_mul_ok_wrap(800, 1500) || u_mul(800, 1500) != 1200000) return 1;
  use_i128 = 1;
  if (!u_mul_ok_i128(800, 1500) || u_mul(800, 1500) != 1200000) return 1;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  p = (BarkIn){1, 1000, 800, 1500, 1000, 100, 1000000000ULL, 0, 1000000000ULL, 0, 1130, 7};
  use_i128 = 0;
  if (field(p, 0) != 1 || field(p, 1) != 800 || field(p, 2) != 1000) return 1;
  if (field(p, 3) != 1200000 || field(p, 4) != 1356000 || field(p, 10) != 1) return 1;
  if (field(p, 9) != 7) return 1;
  use_i128 = 1;
  if (field(p, 2) != 1000 || field(p, 4) != 1356000) return 1;
  p = (BarkIn){1, 10000, 8000, 1200, 800, 500000, 1000000000ULL, 0, 2000000ULL, 0, 1130, 3};
  use_i128 = 0;
  if (field(p, 1) != 1474 || field(p, 2) != 1842 || field(p, 11) != 1) return 1;
  if (field(p, 4) != 1998744) return 1;
  p = (BarkIn){1, 1000, 800, 1000, 700, 200000, 1000000000ULL, 0, 791000ULL, 0, 1130, 1};
  if (field(p, 10) != 1 || field(p, 1) != 800) return 1;
  p = (BarkIn){1, 1000, 800, 1000, 700, 500000, 1000000000ULL, 0, 113000ULL, 0, 1130, 1};
  if (field(p, 0) != 0) return 1;
  p.live = 0;
  p.i_hole = 1000000000ULL;
  p.dust = 100;
  p.rate = 1500;
  p.spot = 1000;
  if (field(p, 0) != 0) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  i = 2553255926290448384LL;
  if (w != i) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_dog_bark_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  ok|dart|dink|due|tab|left_ink|left_art|dirt_new|id|full|partial LIVE INK ART RATE SPOT DUST G_HOLE G_DIRT I_HOLE I_DIRT CHOP NEXT_ID [--i128]\n", stderr);
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
  if (strcmp(cmd, "dart") == 0) return 1;
  if (strcmp(cmd, "dink") == 0) return 2;
  if (strcmp(cmd, "due") == 0) return 3;
  if (strcmp(cmd, "tab") == 0) return 4;
  if (strcmp(cmd, "left_ink") == 0) return 5;
  if (strcmp(cmd, "left_art") == 0) return 6;
  if (strcmp(cmd, "dirt_new") == 0) return 7;
  if (strcmp(cmd, "id") == 0) return 9;
  if (strcmp(cmd, "full") == 0) return 10;
  if (strcmp(cmd, "partial") == 0) return 11;
  return -1;
}

int main(int argc, char **argv) {
  const char *cmd;
  BarkIn p;
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
  if (w >= 0 && argc >= 14) {
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
