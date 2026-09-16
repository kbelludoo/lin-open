/* Pointer-free C11 subset of EIP-7918 scaled/cancun excess.
 * Eligible for src/lin_from_c.lin v2 (no *, no ::, no lone & in signatures).
 * Math proofs use src/lin_geth_eip7918.lin + the C11 __int128 oracle, not this file.
 */
#include <stdint.h>

uint64_t e7918_scaled_excess(uint64_t used, uint64_t maxv, uint64_t target) {
    if (maxv == 0) {
        return 0;
    }
    if (maxv < target) {
        return 0;
    }
    return used * (maxv - target) / maxv;
}

uint64_t e7918_cancun_excess(uint64_t parent_excess, uint64_t parent_used, uint64_t target_gas) {
    uint64_t s;
    if (parent_excess > (uint64_t)-1 - parent_used) {
        return 0;
    }
    s = parent_excess + parent_used;
    if (s < target_gas) {
        return 0;
    }
    return s - target_gas;
}
