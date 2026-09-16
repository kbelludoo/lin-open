// SPDX-License-Identifier: CC0-1.0
// Scalar excerpt of rust-bitcoin SignedAmount for lin_from_rust v2.
// Free functions only. Not the full newtype, not Result/Option, not fmt/serde.

pub fn sa_coin() -> i64 {
    return 100_000_000;
}

pub fn sa_max() -> i64 {
    return 21_000_000 * 100_000_000;
}

pub fn sa_min() -> i64 {
    return 0 - (21_000_000 * 100_000_000);
}

pub fn sa_from_sat_ok(satoshi: i64) -> i64 {
    if satoshi < (0 - (21_000_000 * 100_000_000)) {
        return 0;
    }
    if satoshi > (21_000_000 * 100_000_000) {
        return 0;
    }
    return 1;
}
