/*
 * lin_str.h — HOST-ABI-1 string intrinsics (abi_id 3..8), byte-exact with the
 * semantics of the Zig Stage0 host helpers (`_lia_len` lin.zig:108,
 * `_lia_str`/`_lia_cat` lin.zig:23-51, `_lia_char_code_at` :57, `_lia_from_code`
 * :63, `starts_lit` :1170, `rg_count_lit` :1999).
 *
 * Spec: docs/HOST_ABI_1.rulel (golden vectors S0..S18 live in test_linbc1.c).
 * Enabled by amendment R6 (AGENTS.md@1.4.4): HOST_RUNTIME_MINIMO_C11_PERMITIDO.
 *
 * Strings are immutable byte sequences (UTF-8 agnostic, byte-indexed), all
 * pure and total: out-of-range reads yield 0/empty rather than trapping.
 * Buffers are caller-provided; nothing here allocates (heap-free ethos).
 */
#ifndef LIN_C_STR_H
#define LIN_C_STR_H

#include "lin_common.h"

/* abi_id 3 — `s.length`: number of bytes of `s`. */
int64_t  lin_str_len(LinStr s);

/* abi_id 4 — `s.charCodeAt(i)`: byte at `i` as i64; i<0 or i>=len → 0. */
int64_t  lin_str_char_code_at(LinStr s, int64_t i);

/* abi_id 5 — `starts_lit(s, i, lit)`: 1 iff `lit` matches byte-wise at `i`;
 * running past the end ⇒ 0; empty `lit` ⇒ 1. */
int64_t  lin_str_starts_lit(LinStr s, int64_t i, LinStr lit);

/* abi_id 6 — `rg_count_lit(hay, needle)`: number of positions i in [0,len)
 * where starts_lit(hay, i, needle)==1 (overlaps count; empty needle counts
 * len positions, never len+1). */
int64_t  lin_str_count_lit(LinStr hay, LinStr needle);

/* abi_id 7 — `String.fromCharCode(c)`: writes the single byte if 0<=c<256,
 * else the empty string. Returns the output length (0|1). `out` >= 1 byte. */
size_t   lin_str_from_code(int64_t c, uint8_t *out);

/* `_lia_str` coercions for cat: i64 → decimal ASCII; bool → "true"/"false". */
size_t   lin_str_of_i64(int64_t x, uint8_t *out, size_t cap);
size_t   lin_str_of_bool(int b, uint8_t *out, size_t cap);

/* abi_id 8 — `_lia_cat(a, b)` over already-coerced byte strings: writes
 * sa||sb into `out` (cap). Per the host, an empty side is the identity of the
 * other — result is the plain concatenation either way. Returns the length
 * written, or 0xFF..FF (SIZE_MAX) if cap is insufficient (nothing partial
 * is guaranteed). */
size_t   lin_str_cat(LinStr sa, LinStr sb, uint8_t *out, size_t cap);

#endif /* LIN_C_STR_H */
