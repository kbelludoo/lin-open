/* Eligible C11 scalar for lin_from_c: same arithmetic as Core dust overhead, no C++. */
int64_t btd_spend_overhead(int is_witness) {
    if (is_witness) {
        return 32 + 4 + 1 + (107 / 4) + 4;
    } else {
        return 32 + 4 + 1 + 107 + 4;
    }
}

int64_t btd_txout_size(int64_t script_len) {
    int64_t cs;
    if (script_len < 253) {
        cs = 1;
    } else {
        cs = 3;
    }
    return 8 + cs + script_len;
}
