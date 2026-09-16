/*
 * Pointer-free C11 scalar helpers for Compound exchange-rate arithmetic.
 * Eligible for src/lin_from_c.lin (no *, ->, struct, float).
 * ULL suffixes are stripped by cfs_strip_ul before emit.
 * Not linked into Compiler 0.
 */
#include <stdint.h>

uint64_t cer_scale(void) {
    return 1000000000000000000ULL;
}

int cer_add_ok(uint64_t a, uint64_t b) {
    uint64_t s = a + b;
    if (s < a) {
        return 0;
    }
    return 1;
}

uint64_t cer_under(uint64_t cash, uint64_t borrows, uint64_t reserves) {
    uint64_t sum;
    if (cer_add_ok(cash, borrows) == 0) {
        return 0;
    }
    sum = cash + borrows;
    if (sum < reserves) {
        return 0;
    }
    return sum - reserves;
}
