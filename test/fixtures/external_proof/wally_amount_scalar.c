/* Scalar extract of ElementsProject/libwally-core monetary invariants.
 *
 * Constants from include/wally_transaction.h (release_1.5.6):
 *   WALLY_SATOSHI_PER_BTC 100000000
 *   WALLY_BTC_MAX         21000000
 * Cap macro from src/transaction.c:
 *   WALLY_SATOSHI_MAX ((uint64_t)WALLY_BTC_MAX * WALLY_SATOSHI_PER_BTC)
 * Overflow rule from wally_tx_get_total_output_satoshi:
 *   v = a + b; if (v < a || v > WALLY_SATOSHI_MAX) -> WALLY_EINVAL
 *
 * Signed domain follows Bitcoin Core CAmount / MoneyRange
 * (src/consensus/amount.h): negatives are invalid. Pointer/struct
 * transaction APIs are intentionally absent (REJ_C_POINTER).
 *
 * Status: EXPERIMENTAL fixture for LIN Compiler 0. Not libwally.
 */
#define WALLY_OK 0
#define WALLY_EINVAL -2
#define WALLY_SATOSHI_PER_BTC 100000000
#define WALLY_BTC_MAX 21000000
#define WALLY_SATOSHI_MAX ((uint64_t)WALLY_BTC_MAX * WALLY_SATOSHI_PER_BTC)

int64_t wally_satoshi_per_btc(void) {
    return WALLY_SATOSHI_PER_BTC;
}

int64_t wally_btc_max(void) {
    return WALLY_BTC_MAX;
}

int64_t wally_satoshi_max(void) {
    return WALLY_SATOSHI_MAX;
}

int wally_satoshi_in_range(int64_t satoshi) {
    if (satoshi < 0)
        return WALLY_EINVAL;
    if (satoshi > WALLY_SATOSHI_MAX)
        return WALLY_EINVAL;
    return WALLY_OK;
}

int64_t wally_btc_to_satoshi(int64_t btc) {
    int64_t v;
    if (btc < 0)
        return WALLY_EINVAL;
    if (btc > WALLY_BTC_MAX)
        return WALLY_EINVAL;
    v = btc * WALLY_SATOSHI_PER_BTC;
    if (v < 0)
        return WALLY_EINVAL;
    return v;
}

int64_t wally_satoshi_add(int64_t a, int64_t b) {
    int64_t v;
    if (a < 0)
        return WALLY_EINVAL;
    if (b < 0)
        return WALLY_EINVAL;
    if (a > WALLY_SATOSHI_MAX)
        return WALLY_EINVAL;
    if (b > WALLY_SATOSHI_MAX)
        return WALLY_EINVAL;
    v = a + b;
    if (v < a)
        return WALLY_EINVAL;
    if (v > WALLY_SATOSHI_MAX)
        return WALLY_EINVAL;
    return v;
}

int64_t wally_satoshi_sub(int64_t a, int64_t b) {
    if (a < 0)
        return WALLY_EINVAL;
    if (b < 0)
        return WALLY_EINVAL;
    if (b > a)
        return WALLY_EINVAL;
    return a - b;
}

int64_t wally_fee_satoshi(int64_t vin, int64_t vout) {
    return wally_satoshi_sub(vin, vout);
}
