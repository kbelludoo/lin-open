// Scalar no_std extract for lin_from_rust v2. CC0-1.0 semantics from
// rust-bitcoin units Amount::div_by_weight_ceil
// @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684.
// Underscores, &&, and || must survive (v1 treated && as a borrow).
// Small-product ceil only: full (sats*4_000_000) needs 128-bit and lives
// in lin_rust_bitcoin_weightceil.lin, not this subset.

pub fn rwc_max_money() -> u64 {
    return 21_000_000 * 100_000_000;
}

pub fn rwc_mvb_per_wu() -> u64 {
    return 4_000_000;
}

pub fn rwc_from_sat(satoshi: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 {
        return -1;
    }
    return satoshi;
}

pub fn rwc_div_ceil_small(prod: u64, wu: u64) -> i64 {
    if wu == 0 || (prod > 21_000_000 * 100_000_000 && wu < 2) {
        return -1;
    }
    if wu == 0 {
        return -1;
    }
    let q = prod / wu;
    let r = prod - q * wu;
    if r == 0 {
        return q;
    }
    return q + 1;
}
