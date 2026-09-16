/* Transpilable scalar extract of Bitcoin Core v27.1 PaysForRBF + integer GetFee.
 *
 * Not compiled into lin_c0. Core typedefs CAmount = int64_t; this file uses
 * CAmount as a type name so lin_from_c v2 can strip it. No pointers, no
 * C++ references, no std::ceil, no 1000.0.
 *
 * Algorithm: BIP-125 rules 3 and 4. DEFAULT_INCREMENTAL_RELAY_FEE = 1000.
 * License of the algorithm: MIT (Bitcoin Core). This extract is original C11.
 */
CAmount rbf_overflow_mul(CAmount a, CAmount b) {
    CAmount p;
    if (a < 0) return -1;
    if (b < 0) return -1;
    if (a == 0) return 0;
    if (b == 0) return 0;
    p = a * b;
    if (p < 0) return -1;
    if (p / a != b) return -1;
    return p;
}

CAmount rbf_ceil_div(CAmount n, CAmount d) {
    CAmount q;
    CAmount r;
    if (d <= 0) return -1;
    if (n < 0) return -1;
    if (n == 0) return 0;
    q = n / d;
    r = n - (q * d);
    if (r == 0) return q;
    return q + 1;
}

CAmount rbf_get_fee(CAmount sat_per_kvb, CAmount vbytes) {
    CAmount num;
    CAmount fee;
    if (sat_per_kvb < 0) return -1;
    if (vbytes < 0) return -1;
    if (vbytes == 0) return 0;
    num = rbf_overflow_mul(sat_per_kvb, vbytes);
    if (num < 0) return -1;
    fee = rbf_ceil_div(num, 1000);
    if (fee < 0) return -1;
    if (fee == 0) {
        if (sat_per_kvb > 0) return 1;
    }
    return fee;
}

int rbf_pays_for_rbf(CAmount original_fees, CAmount replacement_fees,
                     CAmount replacement_vsize, CAmount relay_sat_per_kvb) {
    CAmount additional;
    CAmount need;
    if (original_fees < 0) return -1;
    if (replacement_fees < 0) return -1;
    if (replacement_vsize < 0) return -1;
    if (relay_sat_per_kvb < 0) return -1;
    if (replacement_fees < original_fees) return 0;
    additional = replacement_fees - original_fees;
    need = rbf_get_fee(relay_sat_per_kvb, replacement_vsize);
    if (need < 0) return -1;
    if (additional < need) return 0;
    return 1;
}

int rbf_candidates_ok(CAmount n) {
    if (n < 0) return -1;
    if (n > 100) return 0;
    return 1;
}
