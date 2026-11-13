/*
 * Independent C11 oracle for Maker/Sky vat.fork (uint64-scale, RAY'=1e9).
 *
 * Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_maker_vat_fork.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/vat.sol fork / signed _add/_sub / _mul
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy vat.sol.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int *ov) {
  __uint128_t q;
  if (ov) *ov = 0;
  if (d == 0) {
    if (ov) *ov = 1;
    return 0;
  }
  q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
  if (q > I64MAX) {
    if (ov) *ov = 1;
    return 0;
  }
  return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
  if (d == 0) return 0;
  return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d, uint64_t *q_out,
                            uint64_t *r_out, int *ov_out) {
  uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
  uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge,
      need_borrow;
  int i, ov;
  if (d == 0) {
    *q_out = 0;
    *r_out = 0;
    *ov_out = 1;
    return;
  }
  a0 = a & 0xffffffffULL;
  a1 = a >> 32;
  b0 = b & 0xffffffffULL;
  b1 = b >> 32;
  p0 = a0 * b0;
  p1 = a0 * b1;
  p2 = a1 * b0;
  p3 = a1 * b1;
  mid = p1 + p2;
  mid_carry = (mid < p1) ? 1 : 0;
  t = (mid & 0xffffffffULL) << 32;
  lo = p0 + t;
  lo_carry = (lo < p0) ? 1 : 0;
  hi = p3 + (mid >> 32);
  hi = hi + (mid_carry << 32);
  hi = hi + lo_carry;
  r_hi = 0;
  r_lo = 0;
  q = 0;
  ov = 0;
  for (i = 127; i >= 0; i--) {
    bit = (i >= 64) ? ((hi >> (i - 64)) & 1ULL) : ((lo >> i) & 1ULL);
    new_hi = (r_hi << 1) | (r_lo >> 63);
    new_lo = (r_lo << 1) | bit;
    r_hi = new_hi;
    r_lo = new_lo;
    ge = (r_hi != 0) || (r_lo >= d);
    if (ge) {
      need_borrow = u_lt(r_lo, d);
      r_lo = r_lo - d;
      if (need_borrow) r_hi = r_hi - 1;
      if (i >= 64)
        ov = 1;
      else
        q = q | (1ULL << i);
    }
  }
  if ((int64_t)q < 0) ov = 1;
  *q_out = ov ? 0 : q;
  *r_out = r_lo;
  *ov_out = ov;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d, int *ov) {
  uint64_t q, r;
  int o = 0;
  muldiv_limbs_qr(a, b, d, &q, &r, &o);
  if (ov) *ov = o;
  return q;
}

static int use_limbs = 0;

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int *ov) {
  return use_limbs ? muldiv_limbs(a, b, d, ov) : muldiv_i128(a, b, d, ov);
}

static int u_sub_ok(uint64_t x, uint64_t y) {
  return x >= y && x <= I64MAX && y <= I64MAX;
}
static uint64_t u_sub(uint64_t x, uint64_t y) {
  return u_sub_ok(x, y) ? x - y : 0;
}
static int u_add_ok(uint64_t x, uint64_t y) {
  uint64_t s;
  if (x > I64MAX || y > I64MAX) return 0;
  s = x + y;
  return (s >= x) && (s <= I64MAX);
}
static uint64_t u_add(uint64_t x, uint64_t y) {
  return u_add_ok(x, y) ? x + y : 0;
}

static int iadd_ok(uint64_t x, int64_t y) {
  if (x > I64MAX) return 0;
  if (y >= 0) return u_add_ok(x, (uint64_t)y);
  if (y == INT64_MIN) return 0;
  return u_sub_ok(x, (uint64_t)(-y));
}
static uint64_t iadd(uint64_t x, int64_t y) {
  if (!iadd_ok(x, y)) return 0;
  return y >= 0 ? x + (uint64_t)y : x - (uint64_t)(-y);
}
static int isub_ok(uint64_t x, int64_t y) {
  if (x > I64MAX) return 0;
  if (y >= 0) return u_sub_ok(x, (uint64_t)y);
  if (y == INT64_MIN) return 0;
  return u_add_ok(x, (uint64_t)(-y));
}
static uint64_t isub(uint64_t x, int64_t y) {
  if (!isub_ok(x, y)) return 0;
  return y >= 0 ? x - (uint64_t)y : x + (uint64_t)(-y);
}

static int mul_ok(uint64_t a, uint64_t b) {
  int ov = 0;
  if (a == 0 || b == 0) return 1;
  (void)md(a, b, 1, &ov);
  return !ov;
}
static int is_safe(uint64_t ink, uint64_t art, uint64_t rate, uint64_t spot) {
  int ov = 0;
  uint64_t tab, col;
  if (!mul_ok(art, rate) || !mul_ok(ink, spot)) return 0;
  tab = md(art, rate, 1, &ov);
  col = md(ink, spot, 1, &ov);
  return col >= tab;
}
static int nondust(uint64_t art, uint64_t rate, uint64_t dust) {
  int ov = 0;
  uint64_t tab;
  if (art == 0) return 1;
  if (!mul_ok(art, rate)) return 0;
  tab = md(art, rate, 1, &ov);
  return tab >= dust;
}

typedef struct {
  uint64_t u_ink, u_art, v_ink, v_art;
  int64_t dink, dart;
  uint64_t rate, spot, dust, wish_src, wish_dst;
} ForkIn;

static int parse_in(char **a, ForkIn *p) {
  p->u_ink = strtoull(a[0], NULL, 10);
  p->u_art = strtoull(a[1], NULL, 10);
  p->v_ink = strtoull(a[2], NULL, 10);
  p->v_art = strtoull(a[3], NULL, 10);
  p->dink = strtoll(a[4], NULL, 10);
  p->dart = strtoll(a[5], NULL, 10);
  p->rate = strtoull(a[6], NULL, 10);
  p->spot = strtoull(a[7], NULL, 10);
  p->dust = strtoull(a[8], NULL, 10);
  p->wish_src = strtoull(a[9], NULL, 10);
  p->wish_dst = strtoull(a[10], NULL, 10);
  return 1;
}

static int fork_ok(ForkIn p) {
  uint64_t nu_ink, nu_art, nv_ink, nv_art;
  if (p.u_ink > I64MAX || p.u_art > I64MAX || p.v_ink > I64MAX ||
      p.v_art > I64MAX || p.rate > I64MAX || p.spot > I64MAX || p.dust > I64MAX)
    return 0;
  if (p.wish_src != 1 || p.wish_dst != 1) return 0;
  if (!isub_ok(p.u_ink, p.dink) || !isub_ok(p.u_art, p.dart)) return 0;
  if (!iadd_ok(p.v_ink, p.dink) || !iadd_ok(p.v_art, p.dart)) return 0;
  nu_ink = isub(p.u_ink, p.dink);
  nu_art = isub(p.u_art, p.dart);
  nv_ink = iadd(p.v_ink, p.dink);
  nv_art = iadd(p.v_art, p.dart);
  return is_safe(nu_ink, nu_art, p.rate, p.spot) &&
         is_safe(nv_ink, nv_art, p.rate, p.spot) &&
         nondust(nu_art, p.rate, p.dust) && nondust(nv_art, p.rate, p.dust);
}

static int selftest(void) {
  uint64_t q1, q2;
  int ov1 = 0, ov2 = 0;
  ForkIn p;
  q1 = muldiv_i128(100, 200, 50, &ov1);
  q2 = muldiv_limbs(100, 200, 50, &ov2);
  if (q1 != 400 || q2 != 400 || ov1 || ov2) return 1;
  q1 = muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov1);
  q2 = muldiv_limbs(7000000000000000000ULL, 3000000000000000000ULL, 1, &ov2);
  if (!ov1 || !ov2 || q1 || q2) return 1;
  p = (ForkIn){5000000000ULL, 2000000000ULL, 3000000000ULL, 1000000000ULL,
               1000000000, 500000000, 1000000000ULL, 1000000000ULL,
               1000000000000000000ULL, 1, 1};
  use_limbs = 0;
  if (fork_ok(p) != 1) return 1;
  use_limbs = 1;
  if (fork_ok(p) != 1) return 1;
  use_limbs = 0;
  p.wish_src = 0;
  if (fork_ok(p) != 0) return 1;
  if (u_add(7000000000000000000ULL, 3000000000000000000ULL) != 0) return 1;
  if (isub(5000000000ULL, -1000000000) != 6000000000ULL) return 1;
  puts("PASS");
  return 0;
}

static void usage(void) {
  fputs("usage: maker_vat_fork_c11 selftest\n", stderr);
  fputs("  muldiv|muldiv_rem A B D [--limbs]\n", stderr);
  fputs("  sub|add|iadd|isub X Y [--limbs]\n", stderr);
  fputs("  ok|new_u_ink|new_u_art|new_v_ink|new_v_art UINK UART VINK VART DINK DART RATE SPOT DUST WS WD [--limbs]\n", stderr);
  fputs("  inkc|artc|moved ...same 11 args...\n", stderr);
  fputs("  naive_mul|naive_add A B\n", stderr);
}

static int last_limbs(int argc, char **argv) {
  int i;
  for (i = 2; i < argc; i++)
    if (strcmp(argv[i], "--limbs") == 0) return 1;
  return 0;
}

int main(int argc, char **argv) {
  const char *cmd;
  ForkIn p;
  if (argc < 2) {
    usage();
    return 2;
  }
  use_limbs = last_limbs(argc, argv);
  cmd = argv[1];
  if (strcmp(cmd, "selftest") == 0) return selftest();
  if (strcmp(cmd, "muldiv") == 0 && argc >= 5) {
    int ov = 0;
    printf("%" PRIu64 "\n",
           md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
              strtoull(argv[4], NULL, 10), &ov));
    return 0;
  }
  if (strcmp(cmd, "muldiv_rem") == 0 && argc >= 5) {
    uint64_t a = strtoull(argv[2], NULL, 10);
    uint64_t b = strtoull(argv[3], NULL, 10);
    uint64_t d = strtoull(argv[4], NULL, 10);
    if (use_limbs) {
      uint64_t q, r;
      int ov = 0;
      muldiv_limbs_qr(a, b, d, &q, &r, &ov);
      printf("%" PRIu64 "\n", r);
    } else {
      printf("%" PRIu64 "\n", muldiv_rem_i128(a, b, d));
    }
    return 0;
  }
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
  if (strcmp(cmd, "iadd") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n",
           iadd(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
    return 0;
  }
  if (strcmp(cmd, "isub") == 0 && argc >= 4) {
    printf("%" PRIu64 "\n",
           isub(strtoull(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
    return 0;
  }
  if (argc >= 13 &&
      (strcmp(cmd, "ok") == 0 || strcmp(cmd, "new_u_ink") == 0 ||
       strcmp(cmd, "new_u_art") == 0 || strcmp(cmd, "new_v_ink") == 0 ||
       strcmp(cmd, "new_v_art") == 0 || strcmp(cmd, "inkc") == 0 ||
       strcmp(cmd, "artc") == 0 || strcmp(cmd, "moved") == 0)) {
    parse_in(argv + 2, &p);
    if (strcmp(cmd, "ok") == 0) {
      printf("%d\n", fork_ok(p));
      return 0;
    }
    if (!fork_ok(p)) {
      printf("0\n");
      return 0;
    }
    if (strcmp(cmd, "new_u_ink") == 0) printf("%" PRIu64 "\n", isub(p.u_ink, p.dink));
    else if (strcmp(cmd, "new_u_art") == 0) printf("%" PRIu64 "\n", isub(p.u_art, p.dart));
    else if (strcmp(cmd, "new_v_ink") == 0) printf("%" PRIu64 "\n", iadd(p.v_ink, p.dink));
    else if (strcmp(cmd, "new_v_art") == 0) printf("%" PRIu64 "\n", iadd(p.v_art, p.dart));
    else if (strcmp(cmd, "inkc") == 0)
      printf("%d\n", u_add(isub(p.u_ink, p.dink), iadd(p.v_ink, p.dink)) ==
                         u_add(p.u_ink, p.v_ink));
    else if (strcmp(cmd, "artc") == 0)
      printf("%d\n", u_add(isub(p.u_art, p.dart), iadd(p.v_art, p.dart)) ==
                         u_add(p.u_art, p.v_art));
    else {
      uint64_t m = p.dink >= 0 ? (uint64_t)p.dink : (uint64_t)(-p.dink);
      printf("%" PRIu64 "\n", m);
    }
    return 0;
  }
  if (strcmp(cmd, "naive_mul") == 0 && argc >= 4) {
    int64_t a = strtoll(argv[2], NULL, 10);
    int64_t b = strtoll(argv[3], NULL, 10);
    printf("%" PRId64 "\n", (int64_t)((uint64_t)a * (uint64_t)b));
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
