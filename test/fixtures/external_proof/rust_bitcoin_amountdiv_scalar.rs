// Scalar no_std extract for lin_from_rust v2. CC0-1.0 semantics from
// rust-bitcoin units Amount @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684.
// Underscores and && must survive (v1 treated && as a borrow).

pub fn rad_max_money() -> u64 {
    return 21_000_000 * 100_000_000;
}

pub fn rad_from_sat(satoshi: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 {
        return -1;
    }
    return satoshi;
}

pub fn rad_checked_div(satoshi: u64, rhs: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 {
        return -1;
    }
    if rhs == 0 {
        return -1;
    }
    return satoshi / rhs;
}

pub fn rad_checked_rem(satoshi: u64, rhs: u64) -> i64 {
    if satoshi > 21_000_000 * 100_000_000 || rhs == 0 {
        return -1;
    }
    return satoshi - (satoshi / rhs) * rhs;
}
