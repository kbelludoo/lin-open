/*
 * Pointer-free C11 kernel of uint64-scale Maker/Sky DssLitePsm rush/gush/cut.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy DssLitePsm.sol (hash-pinned elsewhere).
 */
int lpf_wad(void) {
  return 1000000000;
}

int lpf_ray(void) {
  return 1000000000;
}

int lpf_u_mul_ok(int a, int b) {
  int p;
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  if (a == 0) {
    return 1;
  }
  if (b == 0) {
    return 1;
  }
  p = a * b;
  if (p < 0) {
    return 0;
  }
  if (p / a != b) {
    return 0;
  }
  return 1;
}

int lpf_u_add_ok(int a, int b) {
  int s;
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  s = a + b;
  if (s < 0) {
    return 0;
  }
  if (s < a) {
    return 0;
  }
  return 1;
}

int lpf_u_sub_ok(int a, int b) {
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  if (a < b) {
    return 0;
  }
  return 1;
}

int lpf_min(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (x < y) {
    return x;
  }
  return y;
}

int lpf_max(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (x < y) {
    return y;
  }
  return x;
}

int lpf_subcap(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (x < y) {
    return 0;
  }
  return x - y;
}

int lpf_gem_wad(int gem, int to18) {
  if (gem < 0) {
    return 0;
  }
  if (to18 < 0) {
    return 0;
  }
  if (lpf_u_mul_ok(gem, to18) == 0) {
    return 0;
  }
  return gem * to18;
}

int lpf_t_art(int gem, int to18, int buf) {
  int gw;
  if (buf < 0) {
    return 0;
  }
  gw = lpf_gem_wad(gem, to18);
  if (gem != 0) {
    if (gw == 0) {
      return 0;
    }
  }
  if (lpf_u_add_ok(gw, buf) == 0) {
    return 0;
  }
  return gw + buf;
}

int lpf_div_ray(int rad, int ray) {
  if (ray <= 0) {
    return 0;
  }
  if (rad < 0) {
    return 0;
  }
  return rad / ray;
}

int lpf_rush(int gem, int to18, int buf, int art, int rate, int line, int gline, int debt, int ray) {
  int tArt;
  int line_wad;
  int room_art;
  int room_ilk;
  int room_glo;
  if (rate != ray) {
    return 0;
  }
  if (ray <= 0) {
    return 0;
  }
  if (art < 0) {
    return 0;
  }
  tArt = lpf_t_art(gem, to18, buf);
  if (gem != 0) {
    if (tArt == 0) {
      if (buf == 0) {
        return 0;
      }
    }
  }
  line_wad = lpf_div_ray(line, ray);
  room_art = lpf_subcap(tArt, art);
  room_ilk = lpf_subcap(line_wad, art);
  room_glo = lpf_div_ray(lpf_subcap(gline, debt), ray);
  return lpf_min(lpf_min(room_art, room_ilk), room_glo);
}

int lpf_gush(int gem, int to18, int buf, int art, int rate, int line, int cash, int ray) {
  int tArt;
  int line_wad;
  int over_buf;
  int over_line;
  if (rate != ray) {
    return 0;
  }
  if (ray <= 0) {
    return 0;
  }
  if (art < 0) {
    return 0;
  }
  if (cash < 0) {
    return 0;
  }
  tArt = lpf_t_art(gem, to18, buf);
  if (gem != 0) {
    if (tArt == 0) {
      if (buf == 0) {
        return 0;
      }
    }
  }
  line_wad = lpf_div_ray(line, ray);
  over_buf = lpf_subcap(art, tArt);
  over_line = lpf_subcap(art, line_wad);
  return lpf_min(lpf_max(over_buf, over_line), cash);
}

int lpf_cut(int gem, int to18, int art, int cash) {
  int gw;
  int sum;
  int avail;
  if (art < 0) {
    return 0;
  }
  if (cash < 0) {
    return 0;
  }
  gw = lpf_gem_wad(gem, to18);
  if (gem != 0) {
    if (gw == 0) {
      return 0;
    }
  }
  if (lpf_u_add_ok(cash, gw) == 0) {
    return 0;
  }
  sum = cash + gw;
  if (lpf_u_sub_ok(sum, art) == 0) {
    return 0;
  }
  avail = sum - art;
  return lpf_min(cash, avail);
}

int lpf_fill(int gem, int to18, int buf, int art, int rate, int line, int gline, int debt, int ray) {
  int w;
  w = lpf_rush(gem, to18, buf, art, rate, line, gline, debt, ray);
  if (w <= 0) {
    return 0;
  }
  return w;
}

int lpf_trim(int gem, int to18, int buf, int art, int rate, int line, int cash, int ray) {
  int w;
  w = lpf_gush(gem, to18, buf, art, rate, line, cash, ray);
  if (w <= 0) {
    return 0;
  }
  return w;
}

int lpf_chug(int vow, int gem, int to18, int art, int cash) {
  int w;
  if (vow != 1) {
    return 0;
  }
  w = lpf_cut(gem, to18, art, cash);
  if (w <= 0) {
    return 0;
  }
  return w;
}
