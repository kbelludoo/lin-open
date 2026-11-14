/*
 * Pointer-free C11 kernel of uint64-scale GemJoin.join/exit.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed + is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss join.sol (AGPL, hash-pinned elsewhere).
 */
int gj_u_add_ok(int a, int b) {
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

int gj_u_sub_ok(int a, int b) {
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

int gj_join_ok(int usr_gem, int sender_gem, int adapter_token, int sender_token, int usr_token, int wad) {
  if (usr_gem < 0) {
    return 0;
  }
  if (sender_gem < 0) {
    return 0;
  }
  if (adapter_token < 0) {
    return 0;
  }
  if (sender_token < 0) {
    return 0;
  }
  if (usr_token < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (gj_u_add_ok(usr_gem, wad) == 0) {
    return 0;
  }
  if (gj_u_add_ok(adapter_token, wad) == 0) {
    return 0;
  }
  if (gj_u_sub_ok(sender_token, wad) == 0) {
    return 0;
  }
  return 1;
}

int gj_exit_ok(int live, int usr_gem, int sender_gem, int adapter_token, int sender_token, int usr_token, int wad) {
  if (usr_gem < 0) {
    return 0;
  }
  if (sender_gem < 0) {
    return 0;
  }
  if (adapter_token < 0) {
    return 0;
  }
  if (sender_token < 0) {
    return 0;
  }
  if (usr_token < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (gj_u_sub_ok(sender_gem, wad) == 0) {
    return 0;
  }
  if (gj_u_sub_ok(adapter_token, wad) == 0) {
    return 0;
  }
  if (gj_u_add_ok(usr_token, wad) == 0) {
    return 0;
  }
  return 1;
}
