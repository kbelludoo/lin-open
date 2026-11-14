/*
 * Independent C11 oracle for Maker/Sky DssLitePsm rush/gush/cut (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect signed product (p/a == b, p >= 0, result <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Consensus of wrap-detect XOR __int128 is required before any LIN comparison.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: sky-ecosystem/dss-lite-psm src/DssLitePsm.sol
 * rush / gush / cut / fill / trim / chug (AGPL-3.0-or-later). Original C11.
 *
 * Distinct from sellGem/buyGem (no tin/tout): pocket gem*to18 + buf vs Art,
 * ilk line/RAY, global Line-debt/RAY, dai cash, vow.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define WAD_P 1000000000ULL
#define RAY_P 1000000000ULL

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

static int u_add_ok(uint64_t a, uint64_t b) {
  if (a > I64MAX || b > I64MAX) return 0;
  if (use_i128) return ((__int128)a + (__int128)b) <= (__int128)I64MAX;
  if (a > I64MAX - b) return 0;
  return 1;
}

static uint64_t lpf_min(uint64_t x, uint64_t y) { return x < y ? x : y; }
static uint64_t lpf_max(uint64_t x, uint64_t y) { return x > y ? x : y; }
static uint64_t lpf_subcap(uint64_t x, uint64_t y) { return x > y ? x - y : 0; }

static uint64_t lpf_gem_wad(uint64_t gem, uint64_t to18) {
  if (!u_mul_ok(gem, to18)) return 0;
  return use_i128 ? (uint64_t)((__int128)gem * (__int128)to18) : gem * to18;
}

static uint64_t lpf_t_art(uint64_t gem, uint64_t to18, uint64_t buf) {
  uint64_t gw;
  if (buf > I64MAX) return 0;
  gw = lpf_gem_wad(gem, to18);
  if (gem != 0 && gw == 0) return 0;
  if (!u_add_ok(gw, buf)) return 0;
  return gw + buf;
}

static int64_t lpf_rush(int64_t gem, int64_t to18, int64_t buf, int64_t art,
                        int64_t rate, int64_t line, int64_t gline, int64_t debt,
                        int64_t ray) {
  uint64_t tArt, line_wad, room_art, room_ilk, room_glo;
  if (gem < 0 || to18 < 0 || buf < 0 || art < 0 || rate < 0 || line < 0 ||
      gline < 0 || debt < 0 || ray <= 0)
    return 0;
  if (rate != ray) return 0;
  tArt = lpf_t_art((uint64_t)gem, (uint64_t)to18, (uint64_t)buf);
  if (gem != 0 && tArt == 0 && buf == 0) return 0;
  line_wad = (uint64_t)line / (uint64_t)ray;
  room_art = lpf_subcap(tArt, (uint64_t)art);
  room_ilk = lpf_subcap(line_wad, (uint64_t)art);
  room_glo = lpf_subcap((uint64_t)gline, (uint64_t)debt) / (uint64_t)ray;
  return (int64_t)lpf_min(lpf_min(room_art, room_ilk), room_glo);
}

static int64_t lpf_gush(int64_t gem, int64_t to18, int64_t buf, int64_t art,
                        int64_t rate, int64_t line, int64_t cash, int64_t ray) {
  uint64_t tArt, line_wad, over_buf, over_line;
  if (gem < 0 || to18 < 0 || buf < 0 || art < 0 || rate < 0 || line < 0 ||
      cash < 0 || ray <= 0)
    return 0;
  if (rate != ray) return 0;
  tArt = lpf_t_art((uint64_t)gem, (uint64_t)to18, (uint64_t)buf);
  if (gem != 0 && tArt == 0 && buf == 0) return 0;
  line_wad = (uint64_t)line / (uint64_t)ray;
  over_buf = lpf_subcap((uint64_t)art, tArt);
  over_line = lpf_subcap((uint64_t)art, line_wad);
  return (int64_t)lpf_min(lpf_max(over_buf, over_line), (uint64_t)cash);
}

static int64_t lpf_cut(int64_t gem, int64_t to18, int64_t art, int64_t cash) {
  uint64_t gw, sum, avail;
  if (gem < 0 || to18 < 0 || art < 0 || cash < 0) return 0;
  gw = lpf_gem_wad((uint64_t)gem, (uint64_t)to18);
  if (gem != 0 && gw == 0) return 0;
  if (!u_add_ok((uint64_t)cash, gw)) return 0;
  sum = (uint64_t)cash + gw;
  if (sum < (uint64_t)art) return 0;
  avail = sum - (uint64_t)art;
  return (int64_t)lpf_min((uint64_t)cash, avail);
}

static int64_t lpf_fill(int64_t gem, int64_t to18, int64_t buf, int64_t art,
                        int64_t rate, int64_t line, int64_t gline, int64_t debt,
                        int64_t ray) {
  int64_t w =
      lpf_rush(gem, to18, buf, art, rate, line, gline, debt, ray);
  return w <= 0 ? 0 : w;
}

static int64_t lpf_trim(int64_t gem, int64_t to18, int64_t buf, int64_t art,
                        int64_t rate, int64_t line, int64_t cash, int64_t ray) {
  int64_t w = lpf_gush(gem, to18, buf, art, rate, line, cash, ray);
  return w <= 0 ? 0 : w;
}

static int64_t lpf_chug(int64_t vow, int64_t gem, int64_t to18, int64_t art,
                        int64_t cash) {
  int64_t w;
  if (vow != 1) return 0;
  w = lpf_cut(gem, to18, art, cash);
  return w <= 0 ? 0 : w;
}

static int selftest(void) {
  int64_t ray = (int64_t)RAY_P;
  int64_t wad = (int64_t)WAD_P;
  int64_t line2 = 2000000000000000000LL;
  int64_t w;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (lpf_rush(1000000, 1000, 0, 0, ray, line2, line2, 0, ray) != wad) return 1;
  if (lpf_rush(1000000, 1000, 0, 600000000, ray, line2, line2, 0, ray) !=
      400000000)
    return 1;
  if (lpf_gush(400000, 1000, 0, wad, ray, line2, wad, ray) != 600000000)
    return 1;
  if (lpf_cut(1000000, 1000, 1200000000, 500000000) != 300000000) return 1;
  if (lpf_cut(100000, 1000, 500000000, 100000000) != 0) return 1;
  if (lpf_chug(0, 1000000, 1000, 1200000000, 500000000) != 0) return 1;
  if (lpf_fill(1000000, 1000, 0, wad, ray, line2, line2, 0, ray) != 0) return 1;
  use_i128 = 1;
  if (lpf_rush(1000000, 1000, 0, 0, ray, line2, line2, 0, ray) != wad) return 1;
  if (lpf_cut(1000000, 1000, 1200000000, 500000000) != 300000000) return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_litepsm_fill_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  t_art GEM TO18 BUF [--i128]\n", stderr);
  fputs("  rush GEM TO18 BUF ART RATE LINE GLINE DEBT RAY [--i128]\n", stderr);
  fputs("  gush GEM TO18 BUF ART RATE LINE CASH RAY [--i128]\n", stderr);
  fputs("  cut GEM TO18 ART CASH [--i128]\n", stderr);
  fputs("  fill GEM TO18 BUF ART RATE LINE GLINE DEBT RAY [--i128]\n", stderr);
  fputs("  trim GEM TO18 BUF ART RATE LINE CASH RAY [--i128]\n", stderr);
  fputs("  chug VOW GEM TO18 ART CASH [--i128]\n", stderr);
  fputs("  naive_mul A B\n", stderr);
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
  if (strcmp(cmd, "mul") == 0 && argc >= 4) {
    printf("%d\n", u_mul_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "t_art") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n",
           lpf_t_art(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "rush") == 0 && argc >= 11) {
    printf("%" PRId64 "\n",
           lpf_rush(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                    strtoll(argv[8], NULL, 10), strtoll(argv[9], NULL, 10),
                    strtoll(argv[10], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "gush") == 0 && argc >= 10) {
    printf("%" PRId64 "\n",
           lpf_gush(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                    strtoll(argv[8], NULL, 10), strtoll(argv[9], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "cut") == 0 && argc >= 6) {
    printf("%" PRId64 "\n",
           lpf_cut(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                   strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "fill") == 0 && argc >= 11) {
    printf("%" PRId64 "\n",
           lpf_fill(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                    strtoll(argv[8], NULL, 10), strtoll(argv[9], NULL, 10),
                    strtoll(argv[10], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "trim") == 0 && argc >= 10) {
    printf("%" PRId64 "\n",
           lpf_trim(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                    strtoll(argv[8], NULL, 10), strtoll(argv[9], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "chug") == 0 && argc >= 7) {
    printf("%" PRId64 "\n",
           lpf_chug(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10)));
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
