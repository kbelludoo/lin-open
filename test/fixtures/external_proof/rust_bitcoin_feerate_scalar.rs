// Scalar no_std extract for lin_from_rust v2. CC0-1.0 semantics from
// rust-bitcoin units FeeRate/Amount @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684.
// Underscores, paren-less if, and && must survive (v1 treated && as a borrow).

pub fn rb_coin() -> u64 {
    return 100_000_000;
}

pub fn rb_btc_max() -> u64 {
    return 21_000_000;
}

pub fn rb_max_money() -> u64 {
    return 21_000_000 * 100_000_000;
}

pub fn rb_from_sat(satoshi: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 {
        return -1;
    }
    return satoshi;
}

pub fn rb_from_sat_per_kwu(sat_kwu: u64) -> u64 {
    return sat_kwu * 4_000;
}

pub fn rb_from_sat_per_vb(sat_vb: u64) -> u64 {
    return sat_vb * 1_000_000;
}

pub fn rb_from_vb(vb: u64) -> u64 {
    return vb * 4;
}

pub fn rb_ceil_div(n: u64, d: u64) -> i64 {
    let q = 0;
    let r = 0;
    if d <= 0 {
        return -1;
    }
    if n == 0 {
        return 0;
    }
    q = n / d;
    r = n - (q * d);
    if r == 0 {
        return q;
    }
    return q + 1;
}
