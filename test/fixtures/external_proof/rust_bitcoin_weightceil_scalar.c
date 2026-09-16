/* Scalar C11 extract of rust-bitcoin Amount::from_sat and a small-product
 * integer ceil (CC0-1.0 semantics). No pointers, no structs: eligible for
 * src/lin_from_c.lin v2. Weight ceil of sats times 4e6 needs 128-bit product and
 * lives in rust_bitcoin_weightceil_c11.c, not this subset.
 * Logical and in a signature must not be classified as a C++ reference.
 */
int64_t rwc_max_money(void) {
    return 21000000 * 100000000;
}

int64_t rwc_mvb_per_wu(void) {
    return 4000000;
}

int64_t rwc_from_sat(int64_t satoshi) {
    if (satoshi < 0) {
        return -1;
    }
    if (satoshi > 21000000 * 100000000) {
        return -1;
    }
    return satoshi;
}

int64_t rwc_div_ceil_small(int64_t prod, int64_t wu) {
    int64_t q;
    int64_t r;
    int64_t n;
    if (prod < 0) {
        return -1;
    }
    if (wu <= 0) {
        return -1;
    }
    q = prod / wu;
    r = prod - q * wu;
    if (r == 0) {
        return q;
    }
    n = q + 1;
    if (n <= 0) {
        return -1;
    }
    return n;
}
