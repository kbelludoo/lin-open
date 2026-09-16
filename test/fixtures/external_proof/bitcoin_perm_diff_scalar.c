/* Lifted scalar subset of Bitcoin Core v27.1 pow.cpp (MIT).
 * Consensus::Params& / CBlockIndex* are arguments. No pointers, no C++.
 * Transpilable by src/lin_from_c.lin once C++ references are fail-closed.
 */
#include <stdint.h>

int64_t pdt_clamp_timespan(int64_t actual, int64_t target_timespan) {
    int64_t lo;
    int64_t hi;
    if (target_timespan <= 0) {
        return 0;
    }
    lo = target_timespan / 4;
    hi = target_timespan * 4;
    if (actual < lo) {
        actual = lo;
    }
    if (actual > hi) {
        actual = hi;
    }
    return actual;
}

int64_t pdt_on_retarget(int64_t height, int64_t interval) {
    if (interval <= 0) {
        return 0;
    }
    if (height < 0) {
        return 0;
    }
    if (height % interval == 0) {
        return 1;
    }
    return 0;
}

int64_t pdt_off_window_ok(int64_t old_nbits, int64_t new_nbits) {
    if (old_nbits == new_nbits) {
        return 1;
    }
    return 0;
}
