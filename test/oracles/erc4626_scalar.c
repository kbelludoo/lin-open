/*
 * Pointer-free C11 helpers for ERC-4626 virtual offset (eligible for lin_from_c).
 * Full (a*b)/d convert is NOT claimed here: uint64 multiply wraps; the 128-bit
 * product lives in erc4626_c11.c (__int128 + limbs) and src/lin_erc4626_vault.lin.
 */
static uint64_t e4626_pow10(uint64_t exp) {
    uint64_t p = 1U;
    uint64_t i = 0U;
    if (exp > 18U) {
        return 0U;
    } else {
        while (i < exp) {
            if (p > 1844674407370955161ULL) {
                return 0U;
            }
            p = p * 10U;
            i = i + 1U;
        }
        return p;
    }
}

static uint64_t e4626_virtuals_ok(uint64_t supply, uint64_t total_assets, uint64_t offset) {
    uint64_t vs = e4626_pow10(offset);
    if (vs == 0U) {
        if (offset != 0U) {
            return 0U;
        }
    }
    if (supply > 18446744073709551615ULL - vs) {
        return 0U;
    } else {
        if (total_assets == 18446744073709551615ULL) {
            return 0U;
        } else {
            return 1U;
        }
    }
}
