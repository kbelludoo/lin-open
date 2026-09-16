/*
 * C11 scalar restatement of go-ethereum fakeExponential / CalcBlobFee (EIP-4844).
 *
 * Upstream: ethereum/go-ethereum v1.14.12
 *   consensus/misc/eip4844/eip4844.go  (LGPL-3.0)
 *   params/protocol_params.go          (LGPL-3.0)
 *
 * This file is the LIN-eligible subset: no pointers, no structs, no floats.
 * minBlobGasPrice / updateFraction / target blob gas are explicit arguments
 * (go-ethereum reads them from package-level big.Int and params constants).
 *
 * Naive uint64 multiply is intentional: it is what a direct C restatement
 * does, and what the LIN clone improves with 128-bit muldiv.
 *
 * Class: EXPERIMENTAL. Not a Geth node. Not uint256.
 */
#include <stdint.h>

uint64_t eip4844_min_blob_gasprice(void) {
    return 1ULL;
}

uint64_t eip4844_update_fraction(void) {
    return 3338477ULL;
}

uint64_t eip4844_blob_gas_per_blob(void) {
    return 131072ULL;
}

uint64_t eip4844_target_blob_gas(void) {
    return 393216ULL;
}

uint64_t eip4844_calc_excess(uint64_t parent_excess, uint64_t parent_used, uint64_t target) {
    uint64_t excess;
    if (target == 0) {
        return 0;
    }
    excess = parent_excess + parent_used;
    if (excess < parent_excess) {
        return 0;
    }
    if (excess < target) {
        return 0;
    } else {
        return excess - target;
    }
}

uint64_t eip4844_fake_exp_naive(uint64_t factor, uint64_t numerator, uint64_t denominator) {
    uint64_t output;
    uint64_t accum;
    uint64_t i;
    if (denominator == 0) {
        return 0;
    }
    output = 0;
    accum = factor * denominator;
    i = 1ULL;
    while (accum > 0) {
        output = output + accum;
        accum = (accum * numerator) / denominator;
        if (i == 0) {
            return 0;
        }
        accum = accum / i;
        i = i + 1ULL;
    }
    return output / denominator;
}

uint64_t eip4844_cancun_blob_fee_naive(uint64_t excess) {
    return eip4844_fake_exp_naive(eip4844_min_blob_gasprice(), excess, eip4844_update_fraction());
}
