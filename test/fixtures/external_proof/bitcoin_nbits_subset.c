/* C11 scalar subset of Bitcoin compact-nBits flags and timespan clamp.
 * No pointers, structs, or C++. Eligible for src/lin_from_c.lin.
 * Algorithm from bitcoin/bitcoin v27.1 (MIT). Not a node.
 */
#include <stdint.h>

uint32_t btc_timespan_clamp(int64_t actual, int64_t target) {
    int64_t lo;
    int64_t hi;
    if (target <= 0) {
        return 0;
    }
    lo = target / 4;
    hi = target * 4;
    if (actual < lo) {
        actual = lo;
    }
    if (actual > hi) {
        actual = hi;
    }
    if (actual < 0) {
        return 0;
    }
    return (uint32_t)actual;
}

int btc_compact_negative(uint32_t ncompact) {
    uint32_t nWord;
    nWord = ncompact & 0x007fffffu;
    if (nWord != 0) {
        if ((ncompact & 0x00800000u) != 0) {
            return 1;
        }
    }
    return 0;
}

int btc_compact_overflow(uint32_t ncompact) {
    uint32_t nSize;
    uint32_t nWord;
    nSize = ncompact >> 24;
    nWord = ncompact & 0x007fffffu;
    if (nWord != 0) {
        if (nSize > 34) {
            return 1;
        }
        if (nWord > 255) {
            if (nSize > 33) {
                return 1;
            }
        }
        if (nWord > 65535) {
            if (nSize > 32) {
                return 1;
            }
        }
    }
    return 0;
}
