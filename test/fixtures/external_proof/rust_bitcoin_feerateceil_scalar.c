/* Scalar C extract of remainder ceil. No pointers, no C++ scope, no lone ref.
 * Matches lin_from_c v2 eligibility (logical-and is not a C++ reference).
 * Algorithm: rust-bitcoin Amount div_by_fee_rate_ceil remainder form.
 */
#include <stdint.h>

static int64_t rfc_max_money(void) {
    return 21000000LL * 100000000LL;
}

static int64_t rfc_kwu_per_mvb(void) {
    return 4000;
}

static int64_t rfc_div_ceil_small(int64_t num, int64_t den) {
    int64_t q;
    int64_t r;
    if (den == 0) {
        return -1;
    }
    q = num / den;
    r = num - q * den;
    if (r == 0) {
        return q;
    }
    return q + 1;
}
