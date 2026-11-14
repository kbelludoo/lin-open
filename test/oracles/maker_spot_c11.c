/*
 * Independent C11 oracle for Maker/Sky Spotter.poke (uint64-scale).
 *
 * mul two implementations:
 *   1. wrapping-detect signed product (p/a == b, p >= 0, result <= INT64_MAX)
 *   2. __int128 product in [0, INT64_MAX]
 *
 * Consensus of wrap-detect XOR __int128 is required before any LIN comparison.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/spot.sol poke (AGPL-3.0-or-later).
 * Original C11. Distinct from Clipper.kick OSM top: returns spot ray, does
 * not execute vat.file. pip.peek val/has, par, mat, wad_ray are arguments.
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

static uint64_t lsp_mul(uint64_t x, uint64_t y) {
  if (!u_mul_ok(x, y)) return 0;
  return use_i128 ? (uint64_t)((__int128)x * (__int128)y) : x * y;
}

static uint64_t lsp_rdiv(uint64_t x, uint64_t y, uint64_t one) {
  uint64_t p;
  if (y == 0 || y > I64MAX || one > I64MAX || x > I64MAX) return 0;
  p = lsp_mul(x, one);
  if (x != 0 && one != 0 && p == 0) return 0;
  return p / y;
}

static int64_t lsp_poke(int64_t has, int64_t val, int64_t wad_ray, int64_t par,
                        int64_t mat, int64_t one) {
  uint64_t scaled, inner;
  if (has != 1) return 0;
  if (val < 0 || wad_ray < 0 || par <= 0 || mat <= 0 || one <= 0) return 0;
  scaled = lsp_mul((uint64_t)val, (uint64_t)wad_ray);
  if (val != 0 && wad_ray != 0 && scaled == 0) return 0;
  inner = lsp_rdiv(scaled, (uint64_t)par, (uint64_t)one);
  if (scaled != 0 && inner == 0) return 0;
  return (int64_t)lsp_rdiv(inner, (uint64_t)mat, (uint64_t)one);
}

static int selftest(void) {
  int64_t ray = (int64_t)RAY_P;
  int64_t w;
  use_i128 = 0;
  if (u_mul_ok_wrap(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 1;
  if (u_mul_ok_i128(7000000000ULL, 3000000000ULL)) return 1;
  use_i128 = 0;
  if (lsp_poke(1, 3000000000LL, 1, ray, 1500000000LL, ray) != 2000000000LL)
    return 1;
  if (lsp_poke(0, 3000000000LL, 1, ray, 1500000000LL, ray) != 0) return 1;
  if (lsp_poke(1, 4000000000LL, 1, ray, 2000000000LL, ray) != 2000000000LL)
    return 1;
  if (lsp_poke(1, 4000000000LL, 1, 2000000000LL, ray, ray) != 2000000000LL)
    return 1;
  if (lsp_poke(1, 0, 1, ray, 1500000000LL, ray) != 0) return 1;
  if (lsp_poke(1, 3000000000LL, 1, ray, 0, ray) != 0) return 1;
  if (lsp_poke(1, 3000000LL, 1000, ray, 1500000000LL, ray) != 2000000000LL)
    return 1;
  if (lsp_poke(1, 7000000000LL, 3000000000LL, ray, 1500000000LL, ray) != 0)
    return 1;
  use_i128 = 1;
  if (lsp_poke(1, 3000000000LL, 1, ray, 1500000000LL, ray) != 2000000000LL)
    return 1;
  if (lsp_poke(1, 6000000000LL, 1, ray, 1500000000LL, ray) != 4000000000LL)
    return 1;
  w = (int64_t)((uint64_t)7000000000LL * (uint64_t)3000000000LL);
  if (w != 2553255926290448384LL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_spot_c11 selftest\n", stderr);
  fputs("  mul A B [--i128]\n", stderr);
  fputs("  rdiv X Y ONE [--i128]\n", stderr);
  fputs("  poke HAS VAL WAD_RAY PAR MAT ONE [--i128]\n", stderr);
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
  if (strcmp(cmd, "rdiv") == 0 && argc >= 5) {
    printf("%" PRIu64 "\n",
           lsp_rdiv(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "poke") == 0 && argc >= 8) {
    printf("%" PRId64 "\n",
           lsp_poke(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                    strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                    strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10)));
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
