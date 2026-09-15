/*
 * Transpilable C11 scalar extract of Bitcoin Core v27.1 fee policy.
 *
 * Upstream (MIT): bitcoin/bitcoin tag v27.1
 *   src/policy/feerate.cpp  CFeeRate GetFee  (IEEE rounding - REJECTED by lin_from_c)
 *   src/policy/policy.cpp   GetVirtualTransactionSize(weight, 0, 0)
 *   src/consensus/amount.h  COIN / MAX_MONEY / MoneyRange
 *
 * This file is the integer-only stand-in that lin_from_c v2 will accept:
 * no pointers, no IEEE types, no C++ scope, no libm rounding. Core's published
 * GetFee body still contains std ceil of (rate * size / 1000) after comment-strip,
 * which is why the C++ original must stay rejected.
 *
 * gcc compiles this as the independent integer oracle. Compiler 0 runs the
 * matching LIN clone. Neither is Bitcoin Core.
 */
#include <stdint.h>

int64_t btc_coin(void) {
    return 100000000LL;
}

int64_t btc_btc_max(void) {
    return 21000000LL;
}

int64_t btc_max_money(void) {
    return 21000000LL * 100000000LL;
}

int64_t btc_witness_scale(void) {
    return 4;
}

int64_t btc_money_range(int64_t n) {
    if (n < 0) {
        return 0;
    }
    if (n > (21000000LL * 100000000LL)) {
        return 0;
    }
    return 1;
}

int64_t btc_overflow_mul(int64_t a, int64_t b) {
    int64_t p;
    if (a < 0) {
        return -1;
    }
    if (b < 0) {
        return -1;
    }
    if (a == 0) {
        return 0;
    }
    if (b == 0) {
        return 0;
    }
    p = a * b;
    if (p < 0) {
        return -1;
    }
    if (p / a != b) {
        return -1;
    }
    return p;
}

int64_t btc_ceil_div(int64_t n, int64_t d) {
    int64_t q;
    int64_t r;
    if (d <= 0) {
        return -1;
    }
    if (n < 0) {
        return -1;
    }
    if (n == 0) {
        return 0;
    }
    q = n / d;
    r = n - (q * d);
    if (r == 0) {
        return q;
    } else {
        return q + 1;
    }
}

int64_t btc_vsize_from_weight(int64_t wu) {
    if (wu < 0) {
        return -1;
    }
    return (wu + 3) / 4;
}

int64_t btc_get_fee(int64_t sat_per_kvb, int64_t vbytes) {
    int64_t num;
    int64_t fee;
    if (sat_per_kvb < 0) {
        return -1;
    }
    if (vbytes < 0) {
        return -1;
    }
    if (vbytes == 0) {
        return 0;
    }
    num = btc_overflow_mul(sat_per_kvb, vbytes);
    if (num < 0) {
        return -1;
    }
    fee = btc_ceil_div(num, 1000);
    if (fee < 0) {
        return -1;
    }
    if (fee == 0) {
        if (sat_per_kvb > 0) {
            return 1;
        }
    }
    return fee;
}

int64_t btc_get_fee_from_weight(int64_t sat_per_kvb, int64_t wu) {
    int64_t vs;
    vs = btc_vsize_from_weight(wu);
    if (vs < 0) {
        return -1;
    }
    return btc_get_fee(sat_per_kvb, vs);
}

int64_t btc_fee_weight_native(int64_t sat_per_kwu, int64_t wu) {
    int64_t num;
    int64_t fee;
    if (sat_per_kwu < 0) {
        return -1;
    }
    if (wu < 0) {
        return -1;
    }
    if (wu == 0) {
        return 0;
    }
    num = btc_overflow_mul(sat_per_kwu, wu);
    if (num < 0) {
        return -1;
    }
    fee = btc_ceil_div(num, 1000);
    if (fee < 0) {
        return -1;
    }
    if (fee == 0) {
        if (sat_per_kwu > 0) {
            return 1;
        }
    }
    return fee;
}

int64_t btc_feerate_from_fee(int64_t fee_paid, int64_t vbytes) {
    int64_t num;
    if (vbytes <= 0) {
        return 0;
    } else {
        if (fee_paid < 0) {
            return -1;
        }
        num = btc_overflow_mul(fee_paid, 1000);
        if (num < 0) {
            return -1;
        }
        return num / vbytes;
    }
}

int64_t btc_kwu_to_kvb(int64_t sat_per_kwu) {
    return btc_overflow_mul(sat_per_kwu, 4);
}

int64_t btc_gap_vsize_vs_weight(int64_t sat_per_kwu, int64_t wu) {
    int64_t kvb;
    int64_t core;
    int64_t native;
    kvb = btc_kwu_to_kvb(sat_per_kwu);
    if (kvb < 0) {
        return -1;
    }
    core = btc_get_fee_from_weight(kvb, wu);
    native = btc_fee_weight_native(sat_per_kwu, wu);
    if (core < 0) {
        return -1;
    }
    if (native < 0) {
        return -1;
    }
    return core - native;
}

int64_t btc_getfee_gate(void) {
    if (btc_coin() != 100000000LL) {
        return -1;
    }
    if (btc_max_money() != 2100000000000000LL) {
        return -2;
    }
    if (btc_money_range(0) != 1) {
        return -3;
    }
    if (btc_money_range(-1) != 0) {
        return -4;
    }
    if (btc_money_range(2100000000000000LL) != 1) {
        return -5;
    }
    if (btc_money_range(2100000000000001LL) != 0) {
        return -6;
    }
    if (btc_vsize_from_weight(0) != 0) {
        return -7;
    }
    if (btc_vsize_from_weight(1) != 1) {
        return -8;
    }
    if (btc_vsize_from_weight(4) != 1) {
        return -9;
    }
    if (btc_vsize_from_weight(381) != 96) {
        return -10;
    }
    if (btc_get_fee(10, 500) != 5) {
        return -11;
    }
    if (btc_get_fee(1, 1) != 1) {
        return -12;
    }
    if (btc_get_fee(0, 100) != 0) {
        return -13;
    }
    if (btc_get_fee(3456, 95) != 329) {
        return -14;
    }
    if (btc_get_fee(3456, 96) != 332) {
        return -15;
    }
    if (btc_fee_weight_native(864, 381) != 330) {
        return -16;
    }
    if (btc_get_fee_from_weight(3456, 381) != 332) {
        return -17;
    }
    if (btc_gap_vsize_vs_weight(864, 381) != 2) {
        return -18;
    }
    if (btc_get_fee(100000, 96) != 9600) {
        return -19;
    }
    if (btc_fee_weight_native(25000, 381) != 9525) {
        return -20;
    }
    if (btc_gap_vsize_vs_weight(25000, 381) != 75) {
        return -21;
    }
    if (btc_feerate_from_fee(1, 2000) != 0) {
        return -22;
    }
    if (btc_feerate_from_fee(3, 2) != 1500) {
        return -23;
    }
    if (btc_get_fee(-1, 10) != -1) {
        return -24;
    }
    return 1;
}
