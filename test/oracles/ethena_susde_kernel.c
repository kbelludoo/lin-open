/*
 * Pointer-free C11 kernel of uint64-scale Ethena sUSDe vest + ERC4626 convert.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy StakedUSDe.sol (GPL-3.0, hash-pinned elsewhere).
 */
int es_vesting_period(void) {
  return 8;
}

int es_min_shares(void) {
  return 1000;
}

int es_u_mul_ok(int a, int b) {
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

int es_unvested(int now, int last_ts, int vest_amt) {
  int elapsed;
  int remaining;
  int period;
  if (now < 0) {
    return 0;
  }
  if (last_ts < 0) {
    return 0;
  }
  if (now < last_ts) {
    return 0;
  }
  if (vest_amt < 0) {
    return 0;
  }
  period = es_vesting_period();
  elapsed = now - last_ts;
  if (elapsed >= period) {
    return 0;
  }
  remaining = period - elapsed;
  if (es_u_mul_ok(remaining, vest_amt) == 0) {
    return 0;
  }
  return (remaining * vest_amt) / period;
}

int es_to_shares(int assets, int supply, int total_assets) {
  if (assets < 0) {
    return 0;
  }
  if (supply < 0) {
    return 0;
  }
  if (total_assets < 0) {
    return 0;
  }
  if (assets == 0) {
    return 0;
  }
  if (supply == 0) {
    return assets;
  }
  if (total_assets == 0) {
    return 0;
  }
  if (es_u_mul_ok(assets, supply) == 0) {
    return 0;
  }
  return (assets * supply) / total_assets;
}

int es_min_shares_ok(int new_supply) {
  if (new_supply < 0) {
    return 0;
  }
  if (new_supply == 0) {
    return 1;
  }
  if (new_supply < es_min_shares()) {
    return 0;
  }
  return 1;
}
