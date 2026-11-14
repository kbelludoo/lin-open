/*
 * Pointer-free C11 kernel of uint64-scale Maker/Sky Spotter.poke.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy spot.sol (hash-pinned elsewhere).
 */
int lsp_wad(void) {
  return 1000000000;
}

int lsp_ray(void) {
  return 1000000000;
}

int lsp_u_mul_ok(int a, int b) {
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

int lsp_mul(int x, int y) {
  if (lsp_u_mul_ok(x, y) == 0) {
    return 0;
  }
  return x * y;
}

int lsp_rdiv(int x, int y, int one) {
  int p;
  if (y <= 0) {
    return 0;
  }
  if (x < 0) {
    return 0;
  }
  if (one < 0) {
    return 0;
  }
  p = lsp_mul(x, one);
  if (x != 0) {
    if (one != 0) {
      if (p == 0) {
        return 0;
      }
    }
  }
  return p / y;
}

int lsp_poke(int has, int val, int wad_ray, int par, int mat, int one) {
  int scaled;
  int inner;
  if (has != 1) {
    return 0;
  }
  if (val < 0) {
    return 0;
  }
  if (wad_ray < 0) {
    return 0;
  }
  if (par <= 0) {
    return 0;
  }
  if (mat <= 0) {
    return 0;
  }
  if (one <= 0) {
    return 0;
  }
  scaled = lsp_mul(val, wad_ray);
  if (val != 0) {
    if (wad_ray != 0) {
      if (scaled == 0) {
        return 0;
      }
    }
  }
  inner = lsp_rdiv(scaled, par, one);
  if (scaled != 0) {
    if (inner == 0) {
      return 0;
    }
  }
  return lsp_rdiv(inner, mat, one);
}
