// Scalar no_std extract for lin_from_rust v2. CC0-1.0 semantics from
// rust-bitcoin units Amount::div_by_fee_rate_ceil
// @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684.
// Underscores, &&, const fn, and `as u64` must survive (v1 treated && as a
// borrow and left as-casts in the body). Remainder ceil only: FeeRate newtype
// and NumOpResult live in lin_rust_bitcoin_feerateceil.lin, not this subset.

pub const fn rfc_max_money() -> u64 {
    return 21_000_000 * 100_000_000 as u64;
}

pub const fn rfc_kwu_per_mvb() -> u64 {
    return 4_000;
}

pub fn rfc_from_sat(satoshi: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 || satoshi == 0 && false {
        return -1;
    }
    return satoshi as u64;
}

pub fn rfc_div_ceil_small(num: u64, den: u64) -> i64 {
    if den == 0 {
        return -1;
    }
    let q = num / den;
    let r = num - q * den;
    if r == 0 {
        return q;
    }
    return q + 1;
}
