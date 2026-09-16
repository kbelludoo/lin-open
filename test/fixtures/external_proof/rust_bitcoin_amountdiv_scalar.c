/* Scalar C11 extract of rust-bitcoin Amount::from_sat / checked_div /
 * checked_rem (CC0-1.0 semantics). No pointers, no structs: eligible for
 * src/lin_from_c.lin v2. Weight floor needs 128-bit product and lives in
 * test/oracles/rust_bitcoin_amountdiv_c11.c, not this subset.
 */
int64_t rad_max_money(void) {
    return 21000000 * 100000000;
}

int64_t rad_from_sat(int64_t satoshi) {
    if (satoshi < 0) {
        return -1;
    }
    if (satoshi > 21000000 * 100000000) {
        return -1;
    }
    return satoshi;
}

int64_t rad_checked_div(int64_t satoshi, int64_t rhs) {
    if (satoshi < 0) {
        return -1;
    }
    if (satoshi > 21000000 * 100000000) {
        return -1;
    }
    if (rhs <= 0) {
        return -1;
    }
    return satoshi / rhs;
}

int64_t rad_checked_rem(int64_t satoshi, int64_t rhs) {
    if (satoshi < 0) {
        return -1;
    }
    if (satoshi > 21000000 * 100000000) {
        return -1;
    }
    if (rhs <= 0) {
        return -1;
    }
    return satoshi - (satoshi / rhs) * rhs;
}
