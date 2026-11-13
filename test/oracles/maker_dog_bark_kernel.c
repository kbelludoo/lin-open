/*
 * Pointer-free C11 kernel of uint64-scale Dog.bark dart/dink/Hole/Dirt.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss dog.sol (AGPL, hash-pinned elsewhere).
 */
int db_u_mul_ok(int a, int b) {
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

int db_min(int a, int b) {
  if (a < b) {
    return a;
  }
  return b;
}

int db_bark_ok(int live, int ink, int art, int rate, int spot, int dust, int g_hole, int g_dirt, int i_hole, int i_dirt, int chop, int next_id) {
  int room;
  int dart;
  int dink;
  int wad;
  if (next_id < 0) {
    return 0;
  }
  if (live != 1) {
    return 0;
  }
  if (art < 1) {
    return 0;
  }
  if (rate < 1) {
    return 0;
  }
  if (chop < 1) {
    return 0;
  }
  if (db_u_mul_ok(ink, spot) == 0) {
    return 0;
  }
  if (db_u_mul_ok(art, rate) == 0) {
    return 0;
  }
  if (spot < 1) {
    return 0;
  }
  if (ink * spot >= art * rate) {
    return 0;
  }
  if (g_hole <= g_dirt) {
    return 0;
  }
  if (i_hole <= i_dirt) {
    return 0;
  }
  room = db_min(g_hole - g_dirt, i_hole - i_dirt);
  wad = 1000;
  if (db_u_mul_ok(room, wad) == 0) {
    return 0;
  }
  dart = db_min(art, (room * wad) / rate / chop);
  if (art > dart) {
    if (db_u_mul_ok(art - dart, rate) == 0) {
      return 0;
    }
    if ((art - dart) * rate < dust) {
      dart = art;
    }
    if (dart != art) {
      if (db_u_mul_ok(dart, rate) == 0) {
        return 0;
      }
      if (dart * rate < dust) {
        return 0;
      }
    }
  }
  if (db_u_mul_ok(ink, dart) == 0) {
    return 0;
  }
  dink = (ink * dart) / art;
  if (dink < 1) {
    return 0;
  }
  return 1;
}
