/* Scalar C11 rewrite of OpenZeppelin Math.log10 for non-negative i64.
 * Algorithm: OpenZeppelin Contracts v5.0.2 (MIT). Not uint256.
 * No pointers, no float, no libc sqrt — cfs_reason should be OK.
 */
int64_t ozl_log10(int64_t value) {
    int64_t result = 0;
    if (value < 0) {
        return 0;
    }
    if (value >= 10000000000000000LL) {
        value = value / 10000000000000000LL;
        result = result + 16;
    }
    if (value >= 100000000LL) {
        value = value / 100000000LL;
        result = result + 8;
    }
    if (value >= 10000LL) {
        value = value / 10000LL;
        result = result + 4;
    }
    if (value >= 100LL) {
        value = value / 100LL;
        result = result + 2;
    }
    if (value >= 10LL) {
        result = result + 1;
    }
    return result;
}
