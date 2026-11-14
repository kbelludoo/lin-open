/*
 * Pointer-free C11 kernel of uint64-scale Maker/Sky Vow heal/kiss/flop/flap.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy vow.sol (hash-pinned elsewhere).
 * Parameter names are dai/vsin/qsin so host vat_dai()/vat_heal() lifts stay rejected.
 */
int lvw_u_lt(int a, int b) {
  if (a < 0) {
    if (b >= 0) {
      return 0;
    }
  }
  if (a >= 0) {
    if (b < 0) {
      return 1;
    }
  }
  if (a < b) {
    return 1;
  }
  return 0;
}

int lvw_add_ok(int x, int y) {
  int z;
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  z = x + y;
  if (z < 0) {
    return 0;
  }
  if (lvw_u_lt(z, x) == 1) {
    return 0;
  }
  return 1;
}

int lvw_sub_ok(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (lvw_u_lt(x, y) == 1) {
    return 0;
  }
  return 1;
}

int lvw_add(int x, int y) {
  if (lvw_add_ok(x, y) == 0) {
    return 0;
  }
  return x + y;
}

int lvw_sub(int x, int y) {
  if (lvw_sub_ok(x, y) == 0) {
    return 0;
  }
  return x - y;
}

int lvw_unqueued_ok(int vsin, int qsin, int ash) {
  int t;
  if (lvw_sub_ok(vsin, qsin) == 0) {
    return 0;
  }
  t = vsin - qsin;
  return lvw_sub_ok(t, ash);
}

int lvw_unqueued(int vsin, int qsin, int ash) {
  int t;
  if (lvw_unqueued_ok(vsin, qsin, ash) == 0) {
    return 0;
  }
  t = vsin - qsin;
  return t - ash;
}

int lvw_heal_ok(int dai, int vsin, int qsin, int ash, int rad) {
  int uq;
  if (rad < 0) {
    return 0;
  }
  if (dai < 0) {
    return 0;
  }
  if (lvw_unqueued_ok(vsin, qsin, ash) == 0) {
    return 0;
  }
  if (lvw_u_lt(dai, rad) == 1) {
    return 0;
  }
  uq = lvw_unqueued(vsin, qsin, ash);
  if (lvw_u_lt(uq, rad) == 1) {
    return 0;
  }
  return 1;
}

int lvw_kiss_ok(int dai, int ash, int rad) {
  if (rad < 0) {
    return 0;
  }
  if (dai < 0) {
    return 0;
  }
  if (ash < 0) {
    return 0;
  }
  if (lvw_u_lt(ash, rad) == 1) {
    return 0;
  }
  if (lvw_u_lt(dai, rad) == 1) {
    return 0;
  }
  return 1;
}

int lvw_flop_ok(int dai, int vsin, int qsin, int ash, int sump) {
  int uq;
  if (dai != 0) {
    return 0;
  }
  if (sump < 0) {
    return 0;
  }
  if (lvw_unqueued_ok(vsin, qsin, ash) == 0) {
    return 0;
  }
  uq = lvw_unqueued(vsin, qsin, ash);
  if (lvw_u_lt(uq, sump) == 1) {
    return 0;
  }
  if (lvw_add_ok(ash, sump) == 0) {
    return 0;
  }
  return 1;
}

int lvw_flap_need(int vsin, int bump, int hump) {
  int inner;
  inner = lvw_add(vsin, bump);
  if (vsin != 0) {
    if (bump != 0) {
      if (inner == 0) {
        return 0;
      }
    }
  }
  return lvw_add(inner, hump);
}

int lvw_flap_ok(int dai, int vsin, int qsin, int ash, int bump, int hump) {
  int uq;
  int need;
  if (dai < 0) {
    return 0;
  }
  if (lvw_unqueued_ok(vsin, qsin, ash) == 0) {
    return 0;
  }
  uq = lvw_unqueued(vsin, qsin, ash);
  if (uq != 0) {
    return 0;
  }
  need = lvw_flap_need(vsin, bump, hump);
  if (need == 0) {
    if (vsin != 0) {
      return 0;
    }
    if (bump != 0) {
      return 0;
    }
    if (hump != 0) {
      return 0;
    }
  }
  if (lvw_u_lt(dai, need) == 1) {
    return 0;
  }
  return 1;
}
