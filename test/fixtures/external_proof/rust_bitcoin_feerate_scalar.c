/* Scalar extract of rust-bitcoin FeeRate::mul_by_weight + Amount::MAX.
 * Not a copy of upstream; integer semantics from
 * units/src/fee_rate/mod.rs @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684 (CC0-1.0).
 * gcc -O2 is an independent oracle. Products use unsigned __int128 like upstream u128.
 */
#include <stdint.h>

#define RB_COIN 100000000LL
#define RB_BTC_MAX 21000000LL
#define RB_MAX_MONEY (RB_BTC_MAX * RB_COIN)
#define RB_DEN 4000000ULL

int64_t rb_coin(void) { return RB_COIN; }
int64_t rb_btc_max(void) { return RB_BTC_MAX; }
int64_t rb_max_money(void) { return RB_MAX_MONEY; }

int64_t rb_from_sat(int64_t satoshi) {
    if (satoshi < 0 || satoshi > RB_MAX_MONEY) return -1;
    return satoshi;
}

int64_t rb_from_sat_per_kwu(int64_t sat_kwu) {
    if (sat_kwu < 0) return -1;
    unsigned __int128 p = (unsigned __int128)(uint64_t)sat_kwu * 4000ull;
    if (p > (unsigned __int128)INT64_MAX) return -1;
    return (int64_t)p;
}

int64_t rb_from_sat_per_vb(int64_t sat_vb) {
    if (sat_vb < 0) return -1;
    unsigned __int128 p = (unsigned __int128)(uint64_t)sat_vb * 1000000ull;
    if (p > (unsigned __int128)INT64_MAX) return -1;
    return (int64_t)p;
}

int64_t rb_from_sat_per_kvb(int64_t sat_kvb) {
    if (sat_kvb < 0) return -1;
    unsigned __int128 p = (unsigned __int128)(uint64_t)sat_kvb * 1000ull;
    if (p > (unsigned __int128)INT64_MAX) return -1;
    return (int64_t)p;
}

int64_t rb_from_vb(int64_t vb) {
    if (vb < 0) return -1;
    unsigned __int128 p = (unsigned __int128)(uint64_t)vb * 4ull;
    if (p > (unsigned __int128)INT64_MAX) return -1;
    return (int64_t)p;
}

int64_t rb_mul_by_weight(int64_t sat_mvb, int64_t wu) {
    unsigned __int128 num, q, r, fee;
    if (sat_mvb < 0 || wu < 0) return -1;
    num = (unsigned __int128)(uint64_t)sat_mvb * (unsigned __int128)(uint64_t)wu;
    q = num / RB_DEN;
    r = num % RB_DEN;
    fee = (r == 0) ? q : q + 1;
    if (fee > (unsigned __int128)RB_MAX_MONEY) return -1;
    return (int64_t)fee;
}

int64_t rb_to_fee(int64_t sat_mvb, int64_t wu) {
    int64_t f = rb_mul_by_weight(sat_mvb, wu);
    if (f < 0) return RB_MAX_MONEY;
    return f;
}

/* Integer Core GetFee stand-in: ceil(sat_per_kvb * vbytes / 1000), min 1 sat. */
int64_t core_get_fee(int64_t sat_per_kvb, int64_t vbytes) {
    unsigned __int128 num, q, r, fee;
    if (sat_per_kvb < 0 || vbytes < 0) return -1;
    if (vbytes == 0) return 0;
    num = (unsigned __int128)(uint64_t)sat_per_kvb * (unsigned __int128)(uint64_t)vbytes;
    q = num / 1000ull;
    r = num % 1000ull;
    fee = (r == 0) ? q : q + 1;
    if (fee == 0 && sat_per_kvb > 0) return 1;
    if (fee > (unsigned __int128)INT64_MAX) return -1;
    return (int64_t)fee;
}
