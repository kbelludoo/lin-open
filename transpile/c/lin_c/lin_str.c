/* lin_str.c — see lin_str.h. Byte-exact ports of the Zig host helpers. */
#include "lin_str.h"

int64_t lin_str_len(LinStr s) {
    /* _lia_len: i64 of the byte count. */
    return (int64_t)s.len;
}

int64_t lin_str_char_code_at(LinStr s, int64_t i) {
    /* _lia_char_code_at: i<0 → 0; i>=len → 0; else the byte value. */
    if (i < 0) return 0;
    if ((uint64_t)i >= (uint64_t)s.len) return 0;
    return (int64_t)s.p[i];
}

int64_t lin_str_starts_lit(LinStr s, int64_t i, LinStr lit) {
    /* starts_lit (lin.zig:1170): compare lit[0..ln) against s[i..i+ln);
     * any overflow of s ⇒ 0; empty lit ⇒ 1. Negative i never matches a
     * non-empty lit (host semantics: s[i+k] with i+k<0 reads 0 via
     * _lia_char_code_at, which can only equal lit bytes if those are 0) —
     * we fail closed instead: i<0 ⇒ 0 unless lit is empty. */
    int64_t k;
    if (i < 0) return lit.len == 0 ? 1 : 0;
    for (k = 0; k < (int64_t)lit.len; k++) {
        if (i + k >= (int64_t)s.len) return 0;
        if (s.p[i + k] != lit.p[k]) return 0;
    }
    return 1;
}

int64_t lin_str_count_lit(LinStr hay, LinStr needle) {
    /* rg_count_lit (lin.zig:1999): scan i in [0, n); count starts_lit hits. */
    int64_t cnt = 0, i, n = (int64_t)hay.len;
    for (i = 0; i < n; i++)
        if (lin_str_starts_lit(hay, i, needle) == 1) cnt++;
    return cnt;
}

size_t lin_str_from_code(int64_t c, uint8_t *out) {
    /* _lia_from_code: 0<=c<256 → 1 byte; else empty. */
    if (c >= 0 && c < 256) { out[0] = (uint8_t)c; return 1; }
    return 0;
}

size_t lin_str_of_i64(int64_t x, uint8_t *out, size_t cap) {
    /* _lia_str on an integer: std.fmt "{d}" — plain signed decimal. */
    int neg = 0;
    uint64_t v, t;
    uint8_t tmp[24];
    size_t n = 0, need;
    if (x < 0) { neg = 1; v = (uint64_t)(-(x + 1)) + 1; } else v = (uint64_t)x;
    t = v;
    do { tmp[n++] = (uint8_t)('0' + (t % 10)); t /= 10; } while (t);
    need = n + (size_t)neg;
    if (need > cap) return SIZE_MAX;
    if (neg) out[0] = '-';
    for (size_t i = 0; i < n; i++) out[(size_t)neg + i] = tmp[n - 1 - i];
    return need;
}

size_t lin_str_of_bool(int b, uint8_t *out, size_t cap) {
    LinStr s = b ? lin_str_of("true") : lin_str_of("false");
    if (s.len > cap) return SIZE_MAX;
    memcpy(out, s.p, s.len);
    return s.len;
}

size_t lin_str_cat(LinStr sa, LinStr sb, uint8_t *out, size_t cap) {
    /* _lia_cat: empty side = identity of the other; else concat. */
    if (sa.len > cap || sb.len > cap - sa.len) return SIZE_MAX;
    memcpy(out, sa.p, sa.len);
    memcpy(out + sa.len, sb.p, sb.len);
    return sa.len + sb.len;
}
