/*
 * C11 scalar restatement of go-ethereum CalcBaseFee (EIP-1559).
 *
 * Upstream: ethereum/go-ethereum v1.14.12
 *   consensus/misc/eip1559/eip1559.go  (LGPL-3.0)
 *   params/protocol_params.go          (LGPL-3.0)
 *
 * This file is the LIN-eligible subset: no pointers, no structs, no floats.
 * Chain-config elasticity / denominator / London flag are explicit arguments
 * (go-ethereum reads them from *params.ChainConfig and *types.Header).
 *
 * Naive uint64 multiply is intentional: it is what a direct C restatement
 * does, and what the LIN clone improves with 128-bit muldiv.
 *
 * Class: EXPERIMENTAL. Not a Geth node. Not uint256.
 */
#include <stdint.h>

uint64_t eip1559_initial_base_fee(void) {
    return 1000000000ULL;
}

uint64_t eip1559_default_elasticity(void) {
    return 2ULL;
}

uint64_t eip1559_default_denom(void) {
    return 8ULL;
}

uint64_t eip1559_parent_gas_target(uint64_t parent_gas_limit, uint64_t elasticity) {
    if (elasticity == 0) {
        return 0;
    }
    return parent_gas_limit / elasticity;
}

uint64_t eip1559_fee_delta(uint64_t parent_base_fee, uint64_t gas_used_delta,
                           uint64_t parent_gas_target, uint64_t denom) {
    uint64_t x;
    if (parent_gas_target == 0) {
        return 0;
    }
    if (denom == 0) {
        return 0;
    }
    x = (parent_base_fee * gas_used_delta) / parent_gas_target;
    return x / denom;
}

uint64_t eip1559_calc_base_fee(uint64_t parent_gas_limit, uint64_t parent_gas_used,
                               uint64_t parent_base_fee, uint64_t elasticity,
                               uint64_t denom, uint64_t london) {
    uint64_t target;
    uint64_t delta;
    if (london == 0) {
        return eip1559_initial_base_fee();
    }
    if (elasticity == 0) {
        return 0;
    }
    if (denom == 0) {
        return 0;
    }
    target = eip1559_parent_gas_target(parent_gas_limit, elasticity);
    if (parent_gas_used == target) {
        return parent_base_fee;
    }
    if (parent_gas_used > target) {
        delta = eip1559_fee_delta(parent_base_fee, parent_gas_used - target, target, denom);
        if (delta < 1) {
            delta = 1;
        }
        return parent_base_fee + delta;
    } else {
        delta = eip1559_fee_delta(parent_base_fee, target - parent_gas_used, target, denom);
        if (parent_base_fee < delta) {
            return 0;
        }
        return parent_base_fee - delta;
    }
}
