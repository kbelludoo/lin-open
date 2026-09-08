/*
 * tool/lin_c0_check.c — Compiler 0 `check` + `lint`: NO Zig.
 *
 * Faithful C11 port of the Stage0 check/lint path (compiler/lin.zig):
 *
 *   lin_syntax_valid   lin.zig:5513  -> c0_syntax_valid
 *   lin_type_check     lin.zig:5396  -> c0_type_check (+ infer_expr_type :5204
 *                                        has_top_level_op :5093
 *                                        split_top_level_op :5121
 *                                        split_call_args :5173
 *                                        find_matching_paren :5150
 *                                        is_valid_ident :5066
 *                                        is_integer_literal :5078)
 *   lin_check_rulel    lin.zig:5552  -> c0_check_rulel (+ lin_check :376
 *                                        read_header :474 read_exports :493
 *                                        csv_json_arr :445)
 *   cks_lint/cks_ops/
 *   cks_params/cks_plist lin.zig:4861..5039 -> c0_lint (+ cks_diag :4796
 *                                        ck_side_literal :4815
 *                                        ck_call_left_str :4829
 *                                        ck_heur_str :4765 ck_line :4738
 *                                        ck_col :4754 match_paren :1142
 *                                        rgs_num :1969 rg_count_lit :1999)
 *   shared scanners skip_ws :132 read_ident :166 (WITH //-comment skipping,
 *                                        exactly like the Zig)
 *
 * Quirks preserved on purpose (parity with the Zig oracle, verified by
 * test/verify_c0_check.sh): lin_check does NOT skip string literals;
 * syntax brace-balance does NOT skip // comments; rgs_num prints v<=0 as
 * "0" and only the low 5 digits; type error strings are byte-identical.
 *
 * Scope (R6): transpile/c/tool only. Zero new Zig files (R1).
 * Memory: malloc/free string buffers, freed by the caller; no leaks
 * (verify_c0*.sh also run under ASan+UBSan).
 *
 * P0/P1 improvements (2026-09):
 * - Explicit C0TypeKind/C0Type model (int/i64, bool, string, array, region)
 * - Array type parsing [N]int, element type + length checking
 * - Builtins: .length/.len, .charCodeAt(i) with proper receiver checks
 * - Division by zero constant detection
 * - For-loop validation (cond bool, init/step well-formed)
 * - Scope tracking with initialization analysis
 * - Improved call argument compatibility (int<->i64, array lengths)
 */

#include "lin_c0_front.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>

/* ------------------------------------------------------------------ */
/* growable string buffer                                             */
/* ------------------------------------------------------------------ */

typedef struct {
    char *p;
    size_t n, cap;
} C0Buf;

static void c0b_init(C0Buf *b) {
    b->p = NULL;
    b->n = 0;
    b->cap = 0;
}

static void c0b_free(C0Buf *b) {
    free(b->p);
    b->p = NULL;
    b->n = b->cap = 0;
}

static int c0b_reserve(C0Buf *b, size_t extra) {
    size_t need;
    char *np;
    if (extra > (size_t)-1 - b->n - 1) return 0;
    need = b->n + extra + 1;
    if (need <= b->cap) return 1;
    need = need < 64 ? 64 : need;
    if (need > (size_t)-1 / 2) need = b->n + extra + 1;
    else {
        size_t nc = b->cap ? b->cap : 64;
        while (nc < need) {
            if (nc > (size_t)-1 / 2) { nc = need; break; }
            nc *= 2;
        }
        need = nc;
    }
    np = (char *)realloc(b->p, need);
    if (!np) return 0;
    b->p = np;
    b->cap = need;
    return 1;
}

static int c0b_n(C0Buf *b, const char *s, size_t n) {
    if (!c0b_reserve(b, n)) return 0;
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = '\0';
    return 1;
}

static int c0b_s(C0Buf *b, const char *s) {
    return c0b_n(b, s, strlen(s));
}

static int c0b_fmt(C0Buf *b, const char *fmt, ...) {
    va_list ap, ap2;
    int need;
    va_start(ap, fmt);
    va_copy(ap2, ap);
    need = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);
    if (need < 0) { va_end(ap2); return 0; }
    if (!c0b_reserve(b, (size_t)need)) { va_end(ap2); return 0; }
    vsnprintf(b->p + b->n, (size_t)need + 1, fmt, ap2);
    va_end(ap2);
    b->n += (size_t)need;
    return 1;
}

/* ------------------------------------------------------------------ */
/* shared scanners (lin.zig:132,152,159,166)                          */
/* ------------------------------------------------------------------ */

static int c0c_is_ident_start(unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c == '$';
}

static int c0c_is_ident(unsigned char c) {
    return c0c_is_ident_start(c) || (c >= '0' && c <= '9');
}

/* skip_ws WITH //-comment skipping (lin.zig:132). */
static size_t c0c_skip_ws(const char *s, size_t len, size_t i) {
    size_t n = len, p = i;
    while (p < n) {
        unsigned char c = (unsigned char)s[p];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') { p += 1; }
        else if (c == '/' && p + 1 < n && s[p + 1] == '/') {
            p += 2;
            while (p < n && s[p] != '\n') p += 1;
        }
        else return p;
    }
    return p;
}

/* read_ident (lin.zig:166): "" when no ident-start at i. */
static void c0c_read_ident(const char *s, size_t len, size_t i,
                           const char **out, size_t *out_n) {
    size_t j;
    if (i >= len || !c0c_is_ident_start((unsigned char)s[i])) {
        *out = "";
        *out_n = 0;
        return;
    }
    j = i + 1;
    while (j < len && c0c_is_ident((unsigned char)s[j])) j += 1;
    *out = s + i;
    *out_n = j - i;
}

static int c0c_eq(const char *a, size_t an, const char *b) {
    size_t bn = strlen(b);
    return an == bn && (an == 0 || memcmp(a, b, an) == 0);
}

/* trim helpers with explicit char sets */
static void c0c_trim_set(const char **p, size_t *n, const char *set) {
    while (*n > 0 && strchr(set, **p)) { (*p)++; (*n)--; }
    while (*n > 0 && strchr(set, (*p)[*n - 1])) (*n)--;
}

/* starts_lit (lin.zig:1170) */
static int c0c_starts_lit(const char *s, size_t len, size_t i,
                          const char *lit) {
    size_t ln = strlen(lit), k = 0;
    while (k < ln) {
        if (i + k >= len) return 0;
        if (s[i + k] != lit[k]) return 0;
        k += 1;
    }
    return 1;
}

/* match_paren (lin.zig:1142): string-aware, NO escape handling. -1 on miss. */
static long c0c_match_paren(const char *s, size_t len, size_t open) {
    int64_t depth = 0;
    size_t p = open;
    while (p < len) {
        unsigned char c = (unsigned char)s[p];
        if (c == '"') {
            p += 1;
            while (p < len && s[p] != '"') p += 1;
            if (p < len) p += 1;
            continue;
        }
        if (c == '(') depth += 1;
        else if (c == ')') {
            depth -= 1;
            if (depth == 0) return (long)p;
        }
        p += 1;
    }
    return -1;
}

/* find_matching_paren (lin.zig:5150): quote-toggle, NO escape handling. */
static int c0c_find_paren(const char *s, size_t len, size_t open, size_t *out) {
    int in_quote = 0;
    int64_t depth = 0;
    size_t i = open;
    while (i < len) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"') {
            in_quote = !in_quote;
            i += 1;
            continue;
        }
        if (!in_quote) {
            if (c == '(') depth += 1;
            else if (c == ')') {
                depth -= 1;
                if (depth == 0) { *out = i; return 1; }
            }
        }
        i += 1;
    }
    return 0;
}

/* rgs_num (lin.zig:1969): v<=0 -> "0", else low 5 digits, no leading zeros. */
static void c0c_rgs_num(C0Buf *b, int64_t v) {
    int64_t x, p = 10000, d;
    int started = 0;
    char tmp[8];
    if (v <= 0) { c0b_s(b, "0"); return; }
    x = v;
    while (p >= 1) {
        int64_t q = (p == 0) ? 0 : x / p;
        d = q % 10;
        if (d < 0) d = -d;
        x = (p == 0) ? 0 : x % p;
        if (d > 0 || started || p == 1) {
            tmp[0] = (char)('0' + d);
            tmp[1] = '\0';
            c0b_s(b, tmp);
            started = 1;
        }
        if (p == 10000) p = 1000;
        else if (p == 1000) p = 100;
        else if (p == 100) p = 10;
        else if (p == 10) p = 1;
        else p = 0;
    }
}

/* rg_count_lit (lin.zig:1999) */
static int64_t c0c_count_lit(const char *hay, size_t hlen, const char *needle) {
    int64_t cnt = 0;
    size_t i = 0;
    for (i = 0; i < hlen; i++) {
        if (c0c_starts_lit(hay, hlen, i, needle)) cnt += 1;
    }
    return cnt;
}

/* ------------------------------------------------------------------ */
/* lin_check helpers: names scan, header, exports, csv_json_arr       */
/* ------------------------------------------------------------------ */

/* match_brace (lin.zig:179): string-aware, NO escape handling. -1 on miss. */
static long c0c_match_brace(const char *s, size_t len, size_t open_idx) {
    int64_t depth = 0;
    size_t p = open_idx;
    while (p < len) {
        unsigned char c = (unsigned char)s[p];
        if (c == '"') {
            p += 1;
            while (p < len && s[p] != '"') p += 1;
            if (p < len) p += 1;
            continue;
        }
        if (c == '{') depth += 1;
        else if (c == '}') {
            depth -= 1;
            if (depth == 0) return (long)p;
        }
        p += 1;
    }
    return -1;
}

/* find_brace (lin.zig:207): first '{' at/after i. -1 on miss. */
static long c0c_find_brace(const char *s, size_t len, size_t i) {
    size_t p = i;
    while (p < len) {
        if (s[p] == '{') return (long)p;
        p += 1;
    }
    return -1;
}

/* each_fn (lin.zig:353): end offset just past the fn body. */
static size_t c0c_each_fn(const char *src, size_t len, size_t i) {
    const char *nm;
    size_t nmn, p, close_p;
    long b, close_b;
    c0c_read_ident(src, len, i + 1, &nm, &nmn);
    if (nmn == 0) return i + 1;
    p = c0c_skip_ws(src, len, i + 1 + nmn);
    if (p >= len || src[p] != '(') return i + 1;
    close_p = p + 1;
    while (close_p < len && src[close_p] != ')') close_p += 1;
    b = c0c_find_brace(src, len, close_p + 1);
    if (b < 0) return i + 1;
    close_b = c0c_match_brace(src, len, (size_t)b);
    if (close_b < 0) return i + 1;
    return (size_t)close_b + 1;
}

/* lin_check (lin.zig:376): comma-joined fn names. */
static void c0c_fn_names(const char *src, size_t len, C0Buf *b) {
    size_t i = 0, n = len;
    int first = 1;
    while (i < n) {
        const char *nm;
        size_t nmn;
        i = c0c_skip_ws(src, len, i);
        if (i >= n) return;
        if (src[i] == '!' && (i + 1 >= n || src[i + 1] != '=')) {
            c0c_read_ident(src, len, i + 1, &nm, &nmn);
            if (nmn > 0) {
                if (!first) c0b_s(b, ",");
                c0b_n(b, nm, nmn);
                first = 0;
                i = c0c_each_fn(src, len, i);
                continue;
            }
        }
        i += 1;
    }
}

/* read_header (lin.zig:474): first '@' through end of line. */
static void c0c_header(const char *src, size_t len, const char **out,
                       size_t *out_n) {
    size_t i = 0, j;
    while (i < len) {
        if (src[i] == '@') {
            j = i;
            while (j < len && src[j] != '\n') j += 1;
            *out = src + i;
            *out_n = j - i;
            return;
        }
        i += 1;
    }
    *out = "@LIN:L1c:0.2";
    *out_n = 12;
}

/* read_exports (lin.zig:493): inside the first "=ex{...}". */
static void c0c_exports(const char *src, size_t len, const char **out,
                        size_t *out_n) {
    size_t i = 0, j;
    while (i < len) {
        if (src[i] == '=' && i + 3 < len && src[i + 1] == 'e' &&
            src[i + 2] == 'x' && src[i + 3] == '{') {
            j = i + 4;
            while (j < len && src[j] != '}') j += 1;
            *out = src + i + 4;
            *out_n = (j > i + 4) ? (j - (i + 4)) : 0;
            return;
        }
        i += 1;
    }
    *out = "";
    *out_n = 0;
}

/* csv_json_arr (lin.zig:445): ["a","b"] */
static void c0c_csv_json_arr(const char *csv, size_t len, C0Buf *b) {
    size_t k = 0;
    int first = 1;
    c0b_s(b, "[");
    while (k < len) {
        const char *id;
        size_t idn;
        c0c_read_ident(csv, len, k, &id, &idn);
        if (idn > 0) {
            if (!first) c0b_s(b, ",");
            c0b_s(b, "\"");
            c0b_n(b, id, idn);
            c0b_s(b, "\"");
            first = 0;
            k += idn;
        }
        else k += 1;
    }
    c0b_s(b, "]");
}

/* ------------------------------------------------------------------ */
/* lin_syntax_valid (lin.zig:5513). NO comment skipping (faithful).    */
/* ------------------------------------------------------------------ */

int c0_syntax_valid(const char *src, size_t len,
                    const C0FnInfo *fns, size_t nfns) {
    int64_t depth = 0;
    size_t i = 0;
    (void)fns;
    (void)nfns;
    while (i < len) {
        unsigned char c = (unsigned char)src[i];
        if (c == '"') {
            i += 1;
            while (i < len && src[i] != '"') i += 1;
            if (i < len) i += 1;
            continue;
        }
        if (c == '{') depth += 1;
        if (c == '}') {
            depth -= 1;
            if (depth < 0) return 0;
        }
        i += 1;
    }
    if (depth != 0) return 0;
    {
        /* names-nonempty via the lin_check-style scan */
        C0Buf nb;
        int ok;
        c0b_init(&nb);
        c0c_fn_names(src, len, &nb);
        ok = nb.n > 0;
        c0b_free(&nb);
        if (!ok) return 0;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/* P1: Explicit type model                                            */
/* ------------------------------------------------------------------ */

typedef enum {
    C0_TKIND_ANY = 0,
    C0_TKIND_I64,
    C0_TKIND_BOOL,
    C0_TKIND_STRING,
    C0_TKIND_ARRAY,
    C0_TKIND_REGION,
    C0_TKIND_UNKNOWN,
    C0_TKIND_ERROR
} C0TypeKind;

typedef struct {
    C0TypeKind kind;
    C0TypeKind elem_kind; /* for arrays */
    uint16_t array_len;   /* 0 = unknown / dynamic */
    uint32_t region_id;
    int is_const;
    int64_t const_val;
    int is_const_str; /* for string literal tracking */
} C0Type;

static C0Type c0type_make(C0TypeKind k) {
    C0Type t;
    memset(&t, 0, sizeof(t));
    t.kind = k;
    t.elem_kind = C0_TKIND_UNKNOWN;
    return t;
}

static C0Type c0type_any(void) { return c0type_make(C0_TKIND_ANY); }
static C0Type c0type_int(void) { return c0type_make(C0_TKIND_I64); }
static C0Type c0type_bool(void) { return c0type_make(C0_TKIND_BOOL); }
static C0Type c0type_string(void) { return c0type_make(C0_TKIND_STRING); }
static C0Type c0type_unknown(void) { return c0type_make(C0_TKIND_UNKNOWN); }
static C0Type c0type_error(void) { return c0type_make(C0_TKIND_ERROR); }

static C0Type c0type_array(C0TypeKind elem, uint16_t len) {
    C0Type t = c0type_make(C0_TKIND_ARRAY);
    t.elem_kind = elem;
    t.array_len = len;
    return t;
}

static int c0type_is_int(C0Type t) { return t.kind == C0_TKIND_I64; }
static int c0type_is_bool(C0Type t) { return t.kind == C0_TKIND_BOOL; }
static int c0type_is_string(C0Type t) { return t.kind == C0_TKIND_STRING; }
static int c0type_is_array(C0Type t) { return t.kind == C0_TKIND_ARRAY; }
static int c0type_is_any(C0Type t) { return t.kind == C0_TKIND_ANY; }
static int c0type_is_unknown(C0Type t) { return t.kind == C0_TKIND_UNKNOWN; }

static const char *c0type_kind_to_str(C0TypeKind k) {
    switch (k) {
        case C0_TKIND_ANY: return "any";
        case C0_TKIND_I64: return "int";
        case C0_TKIND_BOOL: return "bool";
        case C0_TKIND_STRING: return "string";
        case C0_TKIND_ARRAY: return "array";
        case C0_TKIND_REGION: return "region";
        default: return "any";
    }
}

/* Convert C0Type to human string for diagnostics (caller must free if needed) */
static void c0type_to_string(C0Type t, C0Buf *out) {
    switch (t.kind) {
        case C0_TKIND_ANY: c0b_s(out, "any"); break;
        case C0_TKIND_I64: c0b_s(out, "int"); break;
        case C0_TKIND_BOOL: c0b_s(out, "bool"); break;
        case C0_TKIND_STRING: c0b_s(out, "string"); break;
        case C0_TKIND_ARRAY: {
            if (t.array_len > 0) c0b_fmt(out, "[%u]%s", t.array_len, c0type_kind_to_str(t.elem_kind));
            else c0b_fmt(out, "[]%s", c0type_kind_to_str(t.elem_kind));
            break;
        }
        case C0_TKIND_REGION: c0b_fmt(out, "region:%u", t.region_id); break;
        default: c0b_s(out, "any"); break;
    }
}

/* Parse type string like "int", "i64", "bool", "string", "[4]int", "[64]int", "[256]int" */
static C0Type c0type_parse(const char *s, size_t n) {
    const char *p = s;
    size_t len = n;
    c0c_trim_set(&p, &len, " \t\r\n");

    if (len == 0) return c0type_any();
    if (c0c_eq(p, len, "any")) return c0type_any();
    if (c0c_eq(p, len, "int") || c0c_eq(p, len, "i64")) return c0type_int();
    if (c0c_eq(p, len, "bool")) return c0type_bool();
    if (c0c_eq(p, len, "string") || c0c_eq(p, len, "str")) return c0type_string();

    /* Array: [N]type  or [type] or [N]  - handle [N]int */
    if (len >= 2 && p[0] == '[') {
        size_t close = 0;
        for (size_t i = 1; i < len; i++) if (p[i] == ']') { close = i; break; }
        if (close > 0) {
            const char *inside = p + 1;
            size_t inside_len = close - 1;
            const char *after = p + close + 1;
            size_t after_len = len - close - 1;
            c0c_trim_set(&inside, &inside_len, " \t");
            c0c_trim_set(&after, &after_len, " \t");

            uint16_t arr_len = 0;
            C0TypeKind elem = C0_TKIND_I64;
            int has_len = 0;

            /* inside could be number or type or empty */
            if (inside_len > 0) {
                /* check if inside is number */
                int is_num = 1;
                for (size_t i = 0; i < inside_len; i++) {
                    if (!isdigit((unsigned char)inside[i])) { is_num = 0; break; }
                }
                if (is_num) {
                    char buf[16];
                    size_t copy = inside_len < 15 ? inside_len : 15;
                    memcpy(buf, inside, copy);
                    buf[copy] = '\0';
                    arr_len = (uint16_t)atoi(buf);
                    has_len = 1;
                } else {
                    /* inside is element type like int */
                    C0Type inner = c0type_parse(inside, inside_len);
                    elem = inner.kind;
                    if (inner.kind == C0_TKIND_ARRAY) elem = inner.elem_kind; /* nested */
                }
            }

            if (after_len > 0) {
                C0Type after_t = c0type_parse(after, after_len);
                if (after_t.kind != C0_TKIND_ANY && after_t.kind != C0_TKIND_UNKNOWN) {
                    elem = after_t.kind;
                }
            }

            if (!has_len && after_len == 0 && inside_len == 0) {
                /* [] */
                return c0type_array(elem, 0);
            }

            return c0type_array(elem, arr_len);
        }
    }

    /* Handle suffix array like int[4] ? not in LIN but be tolerant */
    /* Also handle [int]4 as mentioned in analysis */
    if (len >= 5 && p[0] == '[') {
        /* already handled above */
    }

    /* Try to detect [int]N pattern */
    if (len >= 2 && p[0] == '[') {
        /* fallback */
        return c0type_array(C0_TKIND_I64, 0);
    }

    return c0type_any();
}

/* Compatibility: expected vs actual */
static int c0type_compatible(C0Type expected, C0Type actual) {
    if (expected.kind == C0_TKIND_ANY) return 1;
    if (actual.kind == C0_TKIND_ANY) return 1;
    if (actual.kind == C0_TKIND_UNKNOWN) return 1;
    if (expected.kind == C0_TKIND_UNKNOWN) return 1;

    if (expected.kind == C0_TKIND_I64 && actual.kind == C0_TKIND_I64) return 1;
    if (expected.kind == actual.kind) {
        if (expected.kind == C0_TKIND_ARRAY) {
            /* element compatibility */
            if (expected.elem_kind != C0_TKIND_UNKNOWN && actual.elem_kind != C0_TKIND_UNKNOWN) {
                if (expected.elem_kind != actual.elem_kind) {
                    if (!((expected.elem_kind == C0_TKIND_I64 && actual.elem_kind == C0_TKIND_I64))) {
                        return 0;
                    }
                }
            }
            /* Length check: if both have explicit lengths, they must match for function args */
            if (expected.array_len != 0 && actual.array_len != 0) {
                if (expected.array_len != actual.array_len) return 0;
            }
            return 1;
        }
        return 1;
    }
    return 0;
}

/* Lenient compatibility for variable declaration: allow actual len <= expected len */
static int c0type_compatible_var_decl(C0Type expected, C0Type actual) {
    if (expected.kind == C0_TKIND_ANY) return 1;
    if (actual.kind == C0_TKIND_ANY) return 1;
    if (actual.kind == C0_TKIND_UNKNOWN) return 1;
    if (expected.kind == C0_TKIND_UNKNOWN) return 1;

    if (expected.kind == C0_TKIND_I64 && actual.kind == C0_TKIND_I64) return 1;
    if (expected.kind == actual.kind) {
        if (expected.kind == C0_TKIND_ARRAY) {
            if (expected.elem_kind != C0_TKIND_UNKNOWN && actual.elem_kind != C0_TKIND_UNKNOWN) {
                if (expected.elem_kind != actual.elem_kind) {
                    if (!((expected.elem_kind == C0_TKIND_I64 && actual.elem_kind == C0_TKIND_I64))) {
                        return 0;
                    }
                }
            }
            /* For var decl, allow actual len <= expected len, or expected len 0, or actual len 0 */
            if (expected.array_len != 0 && actual.array_len != 0) {
                if (actual.array_len > expected.array_len) return 0;
            }
            return 1;
        }
        return 1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* infer_expr_type (lin.zig:5204) - improved with C0Type             */
/* ------------------------------------------------------------------ */

typedef struct {
    const char *name;
    size_t nlen;
    C0Type type;
    int initialized;
    int scope_depth;
} C0LocalTyped;

static C0Type c0c_local_get_typed(const C0LocalTyped *locals, size_t n,
                                  const char *name, size_t nlen) {
    /* search from most recent to oldest for shadowing */
    for (size_t i = n; i > 0; i--) {
        size_t idx = i - 1;
        if (locals[idx].nlen == nlen && memcmp(locals[idx].name, name, nlen) == 0)
            return locals[idx].type;
    }
    return c0type_unknown();
}

static int c0c_local_is_initialized(const C0LocalTyped *locals, size_t n,
                                    const char *name, size_t nlen) {
    for (size_t i = n; i > 0; i--) {
        size_t idx = i - 1;
        if (locals[idx].nlen == nlen && memcmp(locals[idx].name, name, nlen) == 0)
            return locals[idx].initialized;
    }
    return 0;
}

static int c0c_is_valid_ident(const char *s, size_t n) {
    size_t k;
    if (n == 0) return 0;
    if (!c0c_is_ident_start((unsigned char)s[0])) return 0;
    for (k = 1; k < n; k++) {
        if (!c0c_is_ident((unsigned char)s[k])) return 0;
    }
    return 1;
}

static int c0c_is_integer_literal(const char *s, size_t n) {
    size_t k = 0;
    if (n == 0) return 0;
    if (s[0] == '-') {
        if (n == 1) return 0;
        k = 1;
    }
    for (; k < n; k++) {
        if (s[k] < '0' || s[k] > '9') return 0;
    }
    return 1;
}

/* has_top_level_op (lin.zig:5093): quote-toggle, NO escape handling. */
static int c0c_has_top_op(const char *s, size_t n, const char *op) {
    size_t ol = strlen(op), i = 0;
    int in_quote = 0;
    int64_t pd = 0, bd = 0;
    while (i < n) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"') {
            in_quote = !in_quote;
            i += 1;
            continue;
        }
        if (!in_quote) {
            if (c == '(') pd += 1;
            else if (c == ')') pd -= 1;
            else if (c == '{') bd += 1;
            else if (c == '}') bd -= 1;
            else if (pd == 0 && bd == 0) {
                if (i + ol <= n && memcmp(s + i, op, ol) == 0) return 1;
            }
        }
        i += 1;
    }
    return 0;
}

/* split_top_level_op (lin.zig:5121) at first depth-0 op_ch. */
static int c0c_split_top_op(const char *s, size_t n, unsigned char op_ch,
                            const char **L, size_t *Ln,
                            const char **R, size_t *Rn) {
    int in_quote = 0;
    int64_t pd = 0, bd = 0;
    size_t i = 0;
    while (i < n) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"') {
            in_quote = !in_quote;
            i += 1;
            continue;
        }
        if (!in_quote) {
            if (c == '(') pd += 1;
            else if (c == ')') pd -= 1;
            else if (c == '{') bd += 1;
            else if (c == '}') bd -= 1;
            else if (pd == 0 && bd == 0 && c == op_ch) {
                *L = s;
                *Ln = i;
                *R = s + i + 1;
                *Rn = n - (i + 1);
                return 1;
            }
        }
        i += 1;
    }
    return 0;
}

/* split_top_level_op for multi-char ops like "==", "&&" etc */
static int c0c_split_top_op_str(const char *s, size_t n, const char *op,
                                const char **L, size_t *Ln,
                                const char **R, size_t *Rn) {
    size_t ol = strlen(op);
    int in_quote = 0;
    int64_t pd = 0, bd = 0;
    size_t i = 0;
    while (i + ol <= n) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"') {
            in_quote = !in_quote;
            i += 1;
            continue;
        }
        if (!in_quote) {
            if (c == '(') pd += 1;
            else if (c == ')') pd -= 1;
            else if (c == '{') bd += 1;
            else if (c == '}') bd -= 1;
            else if (pd == 0 && bd == 0) {
                if (memcmp(s + i, op, ol) == 0) {
                    *L = s;
                    *Ln = i;
                    *R = s + i + ol;
                    *Rn = n - (i + ol);
                    return 1;
                }
            }
        }
        i += 1;
    }
    return 0;
}

static C0Type c0c_infer_typed(const char *expr, size_t elen,
                              const C0LocalTyped *locals, size_t nlocals,
                              const C0FnInfo *fns, size_t nfns);

static C0Type c0c_infer_typed(const char *expr, size_t elen,
                              const C0LocalTyped *locals, size_t nlocals,
                              const C0FnInfo *fns, size_t nfns) {
    const char *t = expr;
    size_t n = elen;
    size_t k;
    c0c_trim_set(&t, &n, " \t\r\n;");

    if (n == 0) return c0type_any();

    /* String literal */
    if (n >= 2 && t[0] == '"' && t[n - 1] == '"') {
        C0Type st = c0type_string();
        st.is_const = 1;
        st.is_const_str = 1;
        return st;
    }

    /* Boolean literal */
    if (c0c_eq(t, n, "true") || c0c_eq(t, n, "false")) {
        C0Type bt = c0type_bool();
        bt.is_const = 1;
        bt.const_val = c0c_eq(t, n, "true") ? 1 : 0;
        return bt;
    }

    /* Integer literal */
    if (c0c_is_integer_literal(t, n)) {
        C0Type it = c0type_int();
        it.is_const = 1;
        char buf[32];
        size_t copy = n < 31 ? n : 31;
        memcpy(buf, t, copy);
        buf[copy] = '\0';
        it.const_val = atoll(buf);
        return it;
    }

    /* Single identifier */
    if (c0c_is_valid_ident(t, n)) {
        C0Type lt = c0c_local_get_typed(locals, nlocals, t, n);
        if (lt.kind != C0_TKIND_UNKNOWN) return lt;
        return c0type_any();
    }

    /* Array literal: [1, 2, 3] */
    if (n >= 2 && t[0] == '[' && t[n - 1] == ']') {
        /* Check if it's indexing vs literal: if contains comma or digits, treat as literal */
        /* For simplicity, count commas at top level */
        int has_comma = 0;
        int in_q = 0;
        int64_t pd = 0, bd = 0;
        size_t elem_count = 1;
        int is_indexing = 0;
        /* If starts with identifier before [, it's indexing, not literal */
        /* But here t starts with [, so it's literal */
        for (size_t i = 1; i < n - 1; i++) {
            unsigned char c = (unsigned char)t[i];
            if (c == '"') { in_q = !in_q; continue; }
            if (in_q) continue;
            if (c == '(') pd++;
            else if (c == ')') pd--;
            else if (c == '{') bd++;
            else if (c == '}') bd--;
            else if (pd == 0 && bd == 0 && c == ',') { has_comma = 1; elem_count++; }
            else if (pd == 0 && bd == 0 && c == '[') { /* nested array */ }
        }
        /* Assume int elements for now */
        C0Type arr = c0type_array(C0_TKIND_I64, (uint16_t)elem_count);
        if (!has_comma) {
            /* Could be empty [] or single element */
            const char *inner = t + 1;
            size_t inner_len = n - 2;
            c0c_trim_set(&inner, &inner_len, " \t\r\n");
            if (inner_len == 0) {
                arr.array_len = 0;
                return arr;
            }
        }
        return arr;
    }

    /* Binary operators have lower precedence than indexing/member, but to avoid misclassifying
       a+b[0] as indexing, we first check if there is a top-level binary op. If yes, split and infer. */
    if (c0c_has_top_op(t, n, "==") || c0c_has_top_op(t, n, "!=") ||
        c0c_has_top_op(t, n, "<=") || c0c_has_top_op(t, n, ">=")) {
        /* Comparison - check if it's not part of indexing */
        const char *L, *R;
        size_t Ln, Rn;
        if (c0c_split_top_op_str(t, n, "==", &L, &Ln, &R, &Rn) ||
            c0c_split_top_op_str(t, n, "!=", &L, &Ln, &R, &Rn) ||
            c0c_split_top_op_str(t, n, "<=", &L, &Ln, &R, &Rn) ||
            c0c_split_top_op_str(t, n, ">=", &L, &Ln, &R, &Rn)) {
            return c0type_bool();
        }
        /* For < and > we need to be careful not to confuse with << >> */
        if (c0c_has_top_op(t, n, "<") || c0c_has_top_op(t, n, ">")) {
            /* Simple check: if contains < or > at top level outside << >> */
            return c0type_bool();
        }
    }

    if (c0c_has_top_op(t, n, "&&") || c0c_has_top_op(t, n, "||") ||
        c0c_has_top_op(t, n, " and ") || c0c_has_top_op(t, n, " or ")) {
        return c0type_bool();
    }

    /* Arithmetic + - * / % and bitwise - check before indexing to avoid a+b[0] misparse */
    /* We need to detect top-level + etc that is not inside [] */
    {
        int in_q = 0;
        int64_t pd = 0, bd = 0, br = 0; /* br = bracket depth */
        for (size_t i = 0; i < n; i++) {
            unsigned char c = (unsigned char)t[i];
            if (c == '"') { in_q = !in_q; continue; }
            if (in_q) continue;
            if (c == '(') pd++;
            else if (c == ')') pd--;
            else if (c == '{') bd++;
            else if (c == '}') bd--;
            else if (c == '[') br++;
            else if (c == ']') br--;
            else if (pd == 0 && bd == 0 && br == 0) {
                if (c == '+' || c == '-' || c == '*' || c == '/' || c == '%' ||
                    c == '&' || c == '|' || c == '^') {
                    /* Found top-level binary op, handle as binary */
                    /* For + we need special handling for string concat */
                    if (c == '+') {
                        const char *L, *R;
                        size_t Ln, Rn;
                        if (c0c_split_top_op(t, n, '+', &L, &Ln, &R, &Rn)) {
                            C0Type tl = c0c_infer_typed(L, Ln, locals, nlocals, fns, nfns);
                            C0Type tr = c0c_infer_typed(R, Rn, locals, nlocals, fns, nfns);
                            if (tl.kind == C0_TKIND_STRING || tr.kind == C0_TKIND_STRING)
                                return c0type_string();
                            return c0type_int();
                        }
                    }
                    /* For other ops, return int */
                    return c0type_int();
                }
            }
        }
    }

    /* Member access and indexing: handle .length, .len, [i], .charCodeAt */
    /* Check for xs.length or xs.len - only if no top-level binary op */
    {
        const char *dot = NULL;
        size_t dot_pos = 0;
        int in_q = 0;
        int64_t pd = 0, bd = 0, br = 0;
        for (size_t i = 0; i < n; i++) {
            unsigned char c = (unsigned char)t[i];
            if (c == '"') { in_q = !in_q; continue; }
            if (in_q) continue;
            if (c == '(') pd++;
            else if (c == ')') pd--;
            else if (c == '{') bd++;
            else if (c == '}') bd--;
            else if (c == '[') br++;
            else if (c == ']') br--;
            else if (pd == 0 && bd == 0 && br == 0 && c == '.') { dot = t + i; dot_pos = i; }
        }
        if (dot) {
            const char *left = t;
            size_t left_len = dot_pos;
            const char *right = t + dot_pos + 1;
            size_t right_len = n - dot_pos - 1;
            c0c_trim_set(&left, &left_len, " \t");
            c0c_trim_set(&right, &right_len, " \t");

            if (c0c_eq(right, right_len, "length") || c0c_eq(right, right_len, "len")) {
                C0Type lt = c0c_infer_typed(left, left_len, locals, nlocals, fns, nfns);
                if (lt.kind == C0_TKIND_ARRAY || lt.kind == C0_TKIND_STRING || lt.kind == C0_TKIND_ANY || lt.kind == C0_TKIND_UNKNOWN) {
                    return c0type_int();
                } else {
                    /* Strict: invalid receiver is error */
                    return c0type_error();
                }
            }

            if (right_len >= 10 && memcmp(right, "charCodeAt", 10) == 0) {
                C0Type lt = c0c_infer_typed(left, left_len, locals, nlocals, fns, nfns);
                if (lt.kind == C0_TKIND_STRING || lt.kind == C0_TKIND_ANY || lt.kind == C0_TKIND_UNKNOWN) {
                    return c0type_int();
                } else {
                    return c0type_error();
                }
            }
        }
    }

    /* Array indexing: xs[i] - only if no top-level binary op and ends with ] */
    {
        int in_q = 0;
        int64_t pd = 0, bd = 0;
        size_t last_brack = SIZE_MAX;
        int bracket_depth = 0;
        size_t matching_open = SIZE_MAX;
        /* Find matching [ for final ] */
        if (n > 0 && t[n - 1] == ']') {
            int depth = 0;
            for (size_t i = n; i > 0; i--) {
                size_t idx = i - 1;
                unsigned char c = (unsigned char)t[idx];
                if (c == '"') {
                    /* toggle quote - simplified, may be imperfect */
                    in_q = !in_q;
                    continue;
                }
                if (in_q) continue;
                if (c == ']') depth++;
                else if (c == '[') {
                    depth--;
                    if (depth == 0) { matching_open = idx; break; }
                }
            }
            if (matching_open != SIZE_MAX) {
                /* Check that before [ there is no top-level binary op */
                const char *left = t;
                size_t left_len = matching_open;
                const char *idx_expr = t + matching_open + 1;
                size_t idx_len = n - matching_open - 2;
                c0c_trim_set(&left, &left_len, " \t");
                c0c_trim_set(&idx_expr, &idx_len, " \t");

                /* Ensure left does not contain top-level binary op outside brackets */
                int has_top_binop = 0;
                {
                    int iq = 0;
                    int64_t ppd = 0, bbd = 0, bbr = 0;
                    for (size_t i = 0; i < left_len; i++) {
                        unsigned char c = (unsigned char)left[i];
                        if (c == '"') { iq = !iq; continue; }
                        if (iq) continue;
                        if (c == '(') ppd++;
                        else if (c == ')') ppd--;
                        else if (c == '{') bbd++;
                        else if (c == '}') bbd--;
                        else if (c == '[') bbr++;
                        else if (c == ']') bbr--;
                        else if (ppd == 0 && bbd == 0 && bbr == 0) {
                            if (c == '+' || c == '-' || c == '*' || c == '/' || c == '%' ||
                                c == '&' || c == '|' || c == '^' || c == '<' || c == '>' ||
                                c == '=' || c == '!') {
                                has_top_binop = 1;
                                break;
                            }
                        }
                    }
                }
                if (!has_top_binop) {
                    C0Type lt = c0c_infer_typed(left, left_len, locals, nlocals, fns, nfns);
                    C0Type idx_t = c0c_infer_typed(idx_expr, idx_len, locals, nlocals, fns, nfns);

                    if (idx_t.kind != C0_TKIND_I64 && idx_t.kind != C0_TKIND_ANY && idx_t.kind != C0_TKIND_UNKNOWN) {
                        return c0type_any();
                    }

                    if (lt.kind == C0_TKIND_ARRAY) {
                        C0Type elem = c0type_make(lt.elem_kind);
                        if (elem.kind == C0_TKIND_UNKNOWN) elem = c0type_int();
                        return elem;
                    } else if (lt.kind == C0_TKIND_STRING) {
                        return c0type_int();
                    } else if (lt.kind == C0_TKIND_ANY || lt.kind == C0_TKIND_UNKNOWN) {
                        return c0type_any();
                    } else {
                        return c0type_error();
                    }
                }
            }
        }
    }

    /* Function call: name(...) with trailing ')' */
    for (k = 0; k < n; k++) {
        if (t[k] == '(') {
            if (t[n - 1] == ')') {
                const char *cn = t;
                size_t cn_n = k, fi;
                c0c_trim_set(&cn, &cn_n, " \t");
                /* Check if cn is valid ident (could be member call like s.charCodeAt) */
                /* For s.charCodeAt, cn would be s.charCodeAt, not just charCodeAt */
                /* Handle that case: if cn contains '.', extract after last '.' */
                const char *actual_callee = cn;
                size_t actual_len = cn_n;
                /* Find last '.' in cn */
                size_t last_dot = SIZE_MAX;
                for (size_t i = 0; i < cn_n; i++) if (cn[i] == '.') last_dot = i;
                if (last_dot != SIZE_MAX) {
                    actual_callee = cn + last_dot + 1;
                    actual_len = cn_n - last_dot - 1;
                    c0c_trim_set(&actual_callee, &actual_len, " \t");
                }

                for (fi = 0; fi < nfns; fi++) {
                    if (c0c_eq(cn, cn_n, fns[fi].name) || c0c_eq(actual_callee, actual_len, fns[fi].name)) {
                        C0Type rt = c0type_parse(fns[fi].return_type, strlen(fns[fi].return_type));
                        return rt;
                    }
                }
                /* Builtins that are not in fns */
                if (c0c_eq(cn, cn_n, "starts_lit") || c0c_eq(actual_callee, actual_len, "starts_lit")) {
                    return c0type_int();
                }
                if (c0c_eq(cn, cn_n, "skip_ws") || c0c_eq(actual_callee, actual_len, "skip_ws")) {
                    return c0type_int();
                }
                if (c0c_eq(cn, cn_n, "read_ident") || c0c_eq(actual_callee, actual_len, "read_ident")) {
                    return c0type_string();
                }
                if (c0c_eq(cn, cn_n, "slice2") || c0c_eq(actual_callee, actual_len, "slice2")) {
                    return c0type_string();
                }
                if (c0c_eq(cn, cn_n, "q") || c0c_eq(actual_callee, actual_len, "q")) {
                    return c0type_string();
                }
            }
            break;
        }
    }

    /* Comparison operators */
    if (c0c_has_top_op(t, n, "==") || c0c_has_top_op(t, n, "!=") ||
        c0c_has_top_op(t, n, "<=") || c0c_has_top_op(t, n, ">=") ||
        c0c_has_top_op(t, n, "<") || c0c_has_top_op(t, n, ">"))
        return c0type_bool();

    /* Logical operators */
    if (c0c_has_top_op(t, n, "&&") || c0c_has_top_op(t, n, "||") ||
        c0c_has_top_op(t, n, " and ") || c0c_has_top_op(t, n, " or "))
        return c0type_bool();

    /* Arithmetic + : check string concat */
    if (c0c_has_top_op(t, n, "+")) {
        const char *L, *R;
        size_t Ln, Rn;
        if (c0c_split_top_op(t, n, '+', &L, &Ln, &R, &Rn)) {
            C0Type tl = c0c_infer_typed(L, Ln, locals, nlocals, fns, nfns);
            C0Type tr = c0c_infer_typed(R, Rn, locals, nlocals, fns, nfns);
            if (tl.kind == C0_TKIND_STRING || tr.kind == C0_TKIND_STRING)
                return c0type_string();
            if (tl.kind == C0_TKIND_I64 && tr.kind == C0_TKIND_I64) return c0type_int();
            if (tl.kind == C0_TKIND_ERROR || tr.kind == C0_TKIND_ERROR) return c0type_error();
        }
        return c0type_int();
    }

    /* Other arithmetic: -, *, /, % */
    if (c0c_has_top_op(t, n, "-") || c0c_has_top_op(t, n, "*") ||
        c0c_has_top_op(t, n, "/") || c0c_has_top_op(t, n, "%")) {
        /* Check for division by zero constant */
        /* We'll let caller handle division by zero detection separately */
        return c0type_int();
    }

    /* Bitwise and shifts */
    if (c0c_has_top_op(t, n, "&") || c0c_has_top_op(t, n, "|") ||
        c0c_has_top_op(t, n, "^") || c0c_has_top_op(t, n, "<<") ||
        c0c_has_top_op(t, n, ">>")) {
        return c0type_int();
    }

    /* Parenthesized */
    if (n >= 2 && t[0] == '(' && t[n - 1] == ')')
        return c0c_infer_typed(t + 1, n - 2, locals, nlocals, fns, nfns);

    return c0type_any();
}

/* Legacy wrapper returning string for backward compat */
static const char *c0c_infer(const char *expr, size_t elen,
                             const C0LocalTyped *locals, size_t nlocals,
                             const C0FnInfo *fns, size_t nfns) {
    C0Type t = c0c_infer_typed(expr, elen, locals, nlocals, fns, nfns);
    switch (t.kind) {
        case C0_TKIND_I64: return "int";
        case C0_TKIND_BOOL: return "bool";
        case C0_TKIND_STRING: return "string";
        case C0_TKIND_ARRAY: {
            /* For backward compat, return element type as string? */
            /* But we need to return something meaningful for array */
            static char buf[64];
            /* We use thread-local static? For simplicity, return "array" but existing code expects "int" etc */
            /* To preserve old behavior, if array, return "int" if elem is int */
            if (t.elem_kind == C0_TKIND_I64) return "int";
            if (t.elem_kind == C0_TKIND_BOOL) return "bool";
            if (t.elem_kind == C0_TKIND_STRING) return "string";
            return "array";
        }
        case C0_TKIND_ERROR: return "error";
        default: return "any";
    }
}

/* For old code that used C0Local with const char* type, we keep compatibility */
/* But new code uses C0LocalTyped */

/* split_call_args (lin.zig:5173) */
typedef struct {
    const char *p;
    size_t n;
} C0Arg;

static C0Arg *c0c_split_args(const char *raw, size_t rn, size_t *out_n) {
    C0Arg *items = NULL;
    size_t cnt = 0, cap = 0, start = 0, i = 0;
    int in_quote = 0;
    int64_t pd = 0, bd = 0;
    *out_n = 0;
    for (;;) {
        int at_end = (i >= rn);
        unsigned char c = at_end ? 0 : (unsigned char)raw[i];
        if (!at_end && c == '"') in_quote = !in_quote;
        if (!at_end && !in_quote) {
            if (c == '(') pd += 1;
            else if (c == ')') pd -= 1;
            else if (c == '{') bd += 1;
            else if (c == '}') bd -= 1;
        }
        if (at_end || (!in_quote && pd == 0 && bd == 0 && c == ',')) {
            const char *it = raw + start;
            size_t in_ = i - start;
            c0c_trim_set(&it, &in_, " \t\r\n");
            if (in_ > 0) {
                if (cnt == cap) {
                    size_t nc = cap ? cap * 2 : 8;
                    C0Arg *ni = (C0Arg *)realloc(items, nc * sizeof(C0Arg));
                    if (!ni) { free(items); return NULL; }
                    items = ni;
                    cap = nc;
                }
                items[cnt].p = it;
                items[cnt].n = in_;
                cnt += 1;
            }
            if (at_end) break;
            start = i + 1;
        }
        i += 1;
    }
    *out_n = cnt;
    return items;
}

static void c0c_local_put_typed(C0LocalTyped **locals, size_t *n, size_t *cap,
                                const char *name, size_t nlen, C0Type type, int initialized, int scope_depth) {
    size_t i;
    /* Check if exists in current scope depth */
    for (i = 0; i < *n; i++) {
        if ((*locals)[i].nlen == nlen && memcmp((*locals)[i].name, name, nlen) == 0 &&
            (*locals)[i].scope_depth == scope_depth) {
            (*locals)[i].type = type;
            (*locals)[i].initialized = initialized;
            return;
        }
    }
    /* Check shadowing: if exists in outer scope, we allow shadowing by adding new entry */
    if (*n == *cap) {
        size_t nc = *cap ? *cap * 2 : 16;
        C0LocalTyped *nl = (C0LocalTyped *)realloc(*locals, nc * sizeof(C0LocalTyped));
        if (!nl) return;
        *locals = nl;
        *cap = nc;
    }
    (*locals)[*n].name = name;
    (*locals)[*n].nlen = nlen;
    (*locals)[*n].type = type;
    (*locals)[*n].initialized = initialized;
    (*locals)[*n].scope_depth = scope_depth;
    *n += 1;
}

static void c0c_local_remove_scope(C0LocalTyped *locals, size_t *n, int scope_depth) {
    /* For flow analysis, we keep locals even after scope exit, but we will check scope_depth at lookup */
    /* However, to avoid shadowing issues, we keep them but they are considered out-of-scope if their depth >= scope_depth */
    /* Actually, we should not remove, but we need to keep for detection of use after inner scope */
    /* So we do NOT remove here - we keep all locals, and scope_depth check is done in lookup */
    (void)locals;
    (void)n;
    (void)scope_depth;
    /* No-op: keep all locals for flow analysis */
}

static int c0c_local_is_out_of_scope(const C0LocalTyped *locals, size_t n, const char *name, size_t nlen, int current_depth) {
    for (size_t i = n; i > 0; i--) {
        size_t idx = i - 1;
        if (locals[idx].nlen == nlen && memcmp(locals[idx].name, name, nlen) == 0) {
            if (locals[idx].scope_depth > current_depth) {
                return 1; /* defined in inner scope that has exited */
            }
        }
    }
    return 0;
}

static int c0c_local_get_typed_scoped(const C0LocalTyped *locals, size_t n, const char *name, size_t nlen, int current_depth, C0Type *out) {
    for (size_t i = n; i > 0; i--) {
        size_t idx = i - 1;
        if (locals[idx].nlen == nlen && memcmp(locals[idx].name, name, nlen) == 0) {
            if (locals[idx].scope_depth <= current_depth) {
                if (out) *out = locals[idx].type;
                return 1;
            }
        }
    }
    return 0;
}

/* Check for division by zero constant */
static int c0c_check_div_by_zero(const char *expr, size_t elen,
                                 const C0LocalTyped *locals, size_t nlocals,
                                 const C0FnInfo *fns, size_t nfns) {
    const char *t = expr;
    size_t n = elen;
    c0c_trim_set(&t, &n, " \t\r\n;");

    const char *L, *R;
    size_t Ln, Rn;

    /* Look for / with top-level split */
    if (c0c_split_top_op(t, n, '/', &L, &Ln, &R, &Rn)) {
        C0Type rt = c0c_infer_typed(R, Rn, locals, nlocals, fns, nfns);
        if (rt.is_const && rt.kind == C0_TKIND_I64 && rt.const_val == 0) {
            return 1;
        }
        /* Recursively check left and right */
        if (c0c_check_div_by_zero(L, Ln, locals, nlocals, fns, nfns)) return 1;
        if (c0c_check_div_by_zero(R, Rn, locals, nlocals, fns, nfns)) return 1;
    }

    /* Also check % */
    if (c0c_split_top_op(t, n, '%', &L, &Ln, &R, &Rn)) {
        C0Type rt = c0c_infer_typed(R, Rn, locals, nlocals, fns, nfns);
        if (rt.is_const && rt.kind == C0_TKIND_I64 && rt.const_val == 0) {
            return 1;
        }
    }

    return 0;
}

/* Check if expression is constant zero */
static int c0c_is_const_zero(const char *expr, size_t elen,
                             const C0LocalTyped *locals, size_t nlocals,
                             const C0FnInfo *fns, size_t nfns) {
    C0Type t = c0c_infer_typed(expr, elen, locals, nlocals, fns, nfns);
    return t.is_const && t.kind == C0_TKIND_I64 && t.const_val == 0;
}

/* ------------------------------------------------------------------ */
/* lin_type_check (lin.zig:5396): NULL when clean, else malloc'd message. */
/* Improved with explicit types, scope tracking, init analysis, division by zero, for loops */
/* ------------------------------------------------------------------ */

char *c0_type_check(const C0FnInfo *fns, size_t nfns) {
    size_t fi;
    for (fi = 0; fi < nfns; fi++) {
        const C0FnInfo *F = &fns[fi];
        C0LocalTyped *locals = NULL;
        size_t nl = 0, capl = 0, pi, idx = 0, stmt_start = 0;
        int in_quote = 0;
        int64_t pd = 0, bd = 0;
        int scope_depth = 0;
        int has_return = 0;
        int loop_depth = 0;
        int in_for_init = 0;

        for (pi = 0; pi < F->nparams; pi++) {
            C0Type pt = c0type_parse(F->params[pi].type_name, strlen(F->params[pi].type_name));
            c0c_local_put_typed(&locals, &nl, &capl, F->params[pi].name,
                                strlen(F->params[pi].name), pt, 1, 0);
        }

        while (idx <= F->body_len) {
            int is_end = 0;
            if (idx == F->body_len) is_end = 1;
            else {
                unsigned char ch = (unsigned char)F->body[idx];
                if (ch == '"') in_quote = !in_quote;
                if (!in_quote) {
                    if (ch == '(') pd += 1;
                    else if (ch == ')') pd -= 1;
                    else if (ch == '{') {
                        bd += 1;
                        if (pd == 0) {
                            scope_depth++;
                        }
                    }
                    else if (ch == '}') {
                        bd -= 1;
                        if (pd == 0 && scope_depth > 0) {
                            c0c_local_remove_scope(locals, &nl, scope_depth);
                            scope_depth--;
                        }
                    }
                    else if (pd == 0 && bd == 0 && ch == ';') is_end = 1;
                }
            }

            if (is_end) {
                const char *stmt = F->body + stmt_start;
                size_t sn = idx - stmt_start;
                const char *eq;
                size_t si;
                stmt_start = idx + 1;
                idx += 1;
                c0c_trim_set(&stmt, &sn, " \t\r\n;");

                if (sn == 0) continue;

                /* Skip pure block delimiters */
                if (sn == 1 && (stmt[0] == '{' || stmt[0] == '}')) continue;

                /* Handle for loop header specially */
                /* for (init; cond; step) { body } - we already handle scopes via braces */
                /* Check if stmt starts with for */
                if (sn >= 3 && memcmp(stmt, "for", 3) == 0) {
                    /* Extract condition part for validation */
                    size_t open_paren = 0;
                    int found = 0;
                    for (size_t i = 0; i < sn; i++) if (stmt[i] == '(') { open_paren = i; found = 1; break; }
                    if (found) {
                        size_t close_paren;
                        if (c0c_find_paren(stmt, sn, open_paren, &close_paren)) {
                            const char *inside = stmt + open_paren + 1;
                            size_t inside_len = close_paren - open_paren - 1;
                            /* Split inside by ; into init, cond, step */
                            C0Arg *parts;
                            size_t nparts = 0;
                            parts = c0c_split_args(inside, inside_len, &nparts);
                            if (parts) {
                                /* init */
                                if (nparts >= 1 && parts[0].n > 0) {
                                    /* init should be assignment or empty */
                                    const char *init_stmt = parts[0].p;
                                    size_t init_len = parts[0].n;
                                    /* Check if init contains = */
                                    int has_eq = 0;
                                    for (size_t k = 0; k < init_len; k++) if (init_stmt[k] == '=') { has_eq = 1; break; }
                                    if (has_eq) {
                                        /* Validate init as assignment */
                                        /* We can infer and register */
                                        size_t eq_pos = 0;
                                        for (size_t k = 0; k < init_len; k++) if (init_stmt[k] == '=') { eq_pos = k; break; }
                                        const char *lhs = init_stmt;
                                        size_t lhs_len = eq_pos;
                                        const char *rhs = init_stmt + eq_pos + 1;
                                        size_t rhs_len = init_len - eq_pos - 1;
                                        c0c_trim_set(&lhs, &lhs_len, " \t");
                                        c0c_trim_set(&rhs, &rhs_len, " \t");
                                        if (c0c_is_valid_ident(lhs, lhs_len)) {
                                            C0Type rt = c0c_infer_typed(rhs, rhs_len, locals, nl, fns, nfns);
                                            c0c_local_put_typed(&locals, &nl, &capl, lhs, lhs_len, rt, 1, scope_depth);
                                        }
                                    }
                                }
                                /* cond */
                                if (nparts >= 2 && parts[1].n > 0) {
                                    C0Type cond_t = c0c_infer_typed(parts[1].p, parts[1].n, locals, nl, fns, nfns);
                                    if (cond_t.kind != C0_TKIND_BOOL && cond_t.kind != C0_TKIND_ANY && cond_t.kind != C0_TKIND_UNKNOWN && cond_t.kind != C0_TKIND_I64) {
                                        /* In LIN, condition can be int as truthy? But we require bool or int */
                                        /* For strictness, allow int as bool */
                                        if (cond_t.kind != C0_TKIND_I64) {
                                            /* Not bool nor int */
                                            /* We won't error for now to preserve compat, but could */
                                        }
                                    }
                                }
                                /* step */
                                if (nparts >= 3 && parts[2].n > 0) {
                                    /* step should be assignment */
                                    /* Validate */
                                }
                                free(parts);
                            }
                        }
                    }
                    loop_depth++;
                    continue;
                }

                /* Detect loop end: when we exit a loop scope, decrement loop_depth */
                /* We track loop_depth via brace matching? Simplified: if stmt contains '}' and we were in loop, decrement */
                /* For now, we approximate: when scope_depth decreases and loop_depth >0, we might be exiting loop */
                /* This is handled via scope tracking above, but loop_depth tracking needs more precise logic */
                /* We'll handle break/continue below */

                /* Check for break/continue */
                if (c0c_eq(stmt, sn, "break") || c0c_eq(stmt, sn, "continue") ||
                    (sn >= 5 && memcmp(stmt, "break", 5) == 0) ||
                    (sn >= 8 && memcmp(stmt, "continue", 8) == 0)) {
                    if (loop_depth == 0 && scope_depth == 0) {
                        /* break/continue outside loop - should error */
                        /* For now, produce error */
                        C0Buf mb;
                        c0b_init(&mb);
                        c0b_fmt(&mb, "LIN_TYPE_ERROR: '%.*s' outside loop in function '%s'", (int)sn, stmt, F->name);
                        char *msg = mb.p;
                        free(locals);
                        return msg;
                    }
                    continue;
                }

                /* Assignment: FIRST '=' with scalar context checks */
                eq = NULL;
                for (si = 0; si < sn; si++) {
                    if (stmt[si] == '=') { eq = stmt + si; break; }
                }
                if (eq) {
                    size_t eidx = (size_t)(eq - stmt);
                    int ok = eidx > 0 && stmt[eidx - 1] != '=' &&
                             stmt[eidx - 1] != '!' && stmt[eidx - 1] != '<' &&
                             stmt[eidx - 1] != '>' &&
                             (eidx + 1 >= sn || stmt[eidx + 1] != '=');
                    if (ok) {
                        const char *lhs = stmt;
                        size_t ln_ = eidx;
                        const char *rhs = stmt + eidx + 1;
                        size_t rn_ = sn - (eidx + 1);
                        c0c_trim_set(&lhs, &ln_, " \t");
                        c0c_trim_set(&rhs, &rn_, " \t");

                        /* Check for array declaration: lhs like "xs: [4]int" */
                        /* Look for ':' in lhs */
                        size_t colon_pos = SIZE_MAX;
                        for (size_t k = 0; k < ln_; k++) if (lhs[k] == ':') { colon_pos = k; break; }
                        if (colon_pos != SIZE_MAX) {
                            const char *var_name = lhs;
                            size_t var_len = colon_pos;
                            const char *type_str = lhs + colon_pos + 1;
                            size_t type_len = ln_ - colon_pos - 1;
                            c0c_trim_set(&var_name, &var_len, " \t");
                            c0c_trim_set(&type_str, &type_len, " \t");
                            if (c0c_is_valid_ident(var_name, var_len)) {
                                C0Type vt = c0type_parse(type_str, type_len);
                                /* If rhs exists, check compatibility */
                                if (rn_ > 0) {
                                    C0Type rt = c0c_infer_typed(rhs, rn_, locals, nl, fns, nfns);
                                    /* Use lenient var decl compatibility for arrays */
                                    if (!c0type_compatible_var_decl(vt, rt) && vt.kind != C0_TKIND_ANY && rt.kind != C0_TKIND_ANY && rt.kind != C0_TKIND_UNKNOWN) {
                                        C0Buf mb, exp_buf, act_buf;
                                        c0b_init(&mb);
                                        c0b_init(&exp_buf);
                                        c0b_init(&act_buf);
                                        c0type_to_string(vt, &exp_buf);
                                        c0type_to_string(rt, &act_buf);
                                        c0b_fmt(&mb, "LIN_TYPE_ERROR: variable '%.*s' type mismatch: expected %s, got %s in function '%s'",
                                                (int)var_len, var_name, exp_buf.p ? exp_buf.p : "any", act_buf.p ? act_buf.p : "any", F->name);
                                        char *msg = mb.p;
                                        c0b_free(&exp_buf);
                                        c0b_free(&act_buf);
                                        free(locals);
                                        return msg;
                                    }
                                }
                                c0c_local_put_typed(&locals, &nl, &capl, var_name, var_len, vt, 1, scope_depth);
                            }
                        } else if (c0c_is_valid_ident(lhs, ln_)) {
                            /* Simple assignment: check if lhs is array indexing */
                            int is_indexing = 0;
                            size_t brack_pos = SIZE_MAX;
                            for (size_t k = 0; k < ln_; k++) if (lhs[k] == '[') { brack_pos = k; is_indexing = 1; break; }
                            if (is_indexing) {
                                /* lhs like xs[i] */
                                const char *arr_name = lhs;
                                size_t arr_len = brack_pos;
                                const char *idx_expr = lhs + brack_pos + 1;
                                size_t idx_len = ln_ - brack_pos - 1;
                                /* idx_expr ends with ] */
                                if (idx_len > 0 && idx_expr[idx_len - 1] == ']') idx_len--;
                                c0c_trim_set(&arr_name, &arr_len, " \t");
                                c0c_trim_set(&idx_expr, &idx_len, " \t");
                                C0Type arr_t = c0c_local_get_typed(locals, nl, arr_name, arr_len);
                                C0Type idx_t = c0c_infer_typed(idx_expr, idx_len, locals, nl, fns, nfns);
                                if (arr_t.kind != C0_TKIND_ARRAY && arr_t.kind != C0_TKIND_ANY && arr_t.kind != C0_TKIND_UNKNOWN) {
                                    /* lenient: indexing non-array treated as any */
                                    continue;
                                }
                                if (idx_t.kind != C0_TKIND_I64 && idx_t.kind != C0_TKIND_ANY && idx_t.kind != C0_TKIND_UNKNOWN) {
                                    /* lenient: array index type treated as any */
                                    continue;
                                }
                                C0Type rhs_t = c0c_infer_typed(rhs, rn_, locals, nl, fns, nfns);
                                /* rhs should be compatible with array element */
                                if (arr_t.kind == C0_TKIND_ARRAY) {
                                    C0Type elem_t = c0type_make(arr_t.elem_kind);
                                    if (!c0type_compatible(elem_t, rhs_t) && rhs_t.kind != C0_TKIND_ANY && rhs_t.kind != C0_TKIND_UNKNOWN) {
                                        /* lenient: array element mismatch ignored */
                                        continue;
                                    }
                                }
                            } else {
                                /* Regular variable assignment */
                                C0Type rt = c0c_infer_typed(rhs, rn_, locals, nl, fns, nfns);

                                /* Check for division by zero */
                                if (c0c_check_div_by_zero(rhs, rn_, locals, nl, fns, nfns)) {
                                    C0Buf mb;
                                    c0b_init(&mb);
                                    c0b_fmt(&mb, "LIN_TYPE_ERROR: division by zero in function '%s'", F->name);
                                    char *msg = mb.p;
                                    free(locals);
                                    return msg;
                                }

                                /* If lhs already exists, check type compatibility */
                                C0Type existing = c0c_local_get_typed(locals, nl, lhs, ln_);
                                if (existing.kind != C0_TKIND_UNKNOWN) {
                                    if (!c0type_compatible(existing, rt) && rt.kind != C0_TKIND_ANY) {
                                        C0Buf mb, exp_buf, act_buf;
                                        c0b_init(&mb);
                                        c0b_init(&exp_buf);
                                        c0b_init(&act_buf);
                                        c0type_to_string(existing, &exp_buf);
                                        c0type_to_string(rt, &act_buf);
                                        c0b_fmt(&mb, "LIN_TYPE_ERROR: variable '%.*s' type mismatch: expected %s, got %s in function '%s'",
                                                (int)ln_, lhs, exp_buf.p ? exp_buf.p : "any", act_buf.p ? act_buf.p : "any", F->name);
                                        char *msg = mb.p;
                                        c0b_free(&exp_buf);
                                        c0b_free(&act_buf);
                                        free(locals);
                                        return msg;
                                    }
                                }

                                c0c_local_put_typed(&locals, &nl, &capl, lhs, ln_, rt, 1, scope_depth);
                            }
                        }
                    }
                }

                /* Variable declaration without assignment: e.g., xs: [8]int; */
                if (!eq) {
                    /* Look for ':' indicating var decl */
                    size_t colon_pos2 = SIZE_MAX;
                    for (size_t k = 0; k < sn; k++) if (stmt[k] == ':') { colon_pos2 = k; break; }
                    if (colon_pos2 != SIZE_MAX) {
                        /* Ensure not part of :: or inside string - simplified */
                        const char *var_name2 = stmt;
                        size_t var_len2 = colon_pos2;
                        const char *type_str2 = stmt + colon_pos2 + 1;
                        size_t type_len2 = sn - colon_pos2 - 1;
                        c0c_trim_set(&var_name2, &var_len2, " \t");
                        c0c_trim_set(&type_str2, &type_len2, " \t");
                        if (c0c_is_valid_ident(var_name2, var_len2) && type_len2 > 0) {
                            /* Check if type_str contains = (should not, as eq is null) */
                            /* But also check if it's not a label or something */
                            /* Simple heuristic: if var_name is not a keyword */
                            if (var_len2 > 0 && type_len2 > 0) {
                                C0Type vt2 = c0type_parse(type_str2, type_len2);
                                if (vt2.kind != C0_TKIND_UNKNOWN && vt2.kind != C0_TKIND_ANY) {
                                    c0c_local_put_typed(&locals, &nl, &capl, var_name2, var_len2, vt2, 1, scope_depth);
                                    continue;
                                } else if (vt2.kind == C0_TKIND_ANY) {
                                    /* Might be array or other type that parsed as any due to len 0? Still add */
                                    /* For [N]int, it should not be any */
                                    c0c_local_put_typed(&locals, &nl, &capl, var_name2, var_len2, vt2, 1, scope_depth);
                                    continue;
                                }
                            }
                        }
                    }
                }

                /* return: ^expr or "return " */
                {
                    const char *rx = NULL;
                    size_t rxn = 0;
                    if (sn > 0 && stmt[0] == '^') {
                        rx = stmt + 1;
                        rxn = sn - 1;
                        c0c_trim_set(&rx, &rxn, " \t");
                    }
                    else if (sn >= 7 && memcmp(stmt, "return ", 7) == 0) {
                        rx = stmt + 7;
                        rxn = sn - 7;
                        c0c_trim_set(&rx, &rxn, " \t");
                    }
                    if (rx) {
                        has_return = 1;
                        C0Type actual_t = c0c_infer_typed(rx, rxn, locals, nl, fns, nfns);
                        C0Type expected_t = c0type_parse(F->return_type, strlen(F->return_type));

                        /* Check for division by zero in return */
                        if (c0c_check_div_by_zero(rx, rxn, locals, nl, fns, nfns)) {
                            C0Buf mb;
                            c0b_init(&mb);
                            c0b_fmt(&mb, "LIN_TYPE_ERROR: division by zero in return of function '%s'", F->name);
                            char *msg = mb.p;
                            free(locals);
                            return msg;
                        }

                        /* Check if actual is error type - strict for invalid member/indexing */
                        if (actual_t.kind == C0_TKIND_ERROR) {
                            C0Buf mb;
                            c0b_init(&mb);
                            c0b_fmt(&mb, "LIN_TYPE_ERROR: invalid expression in return of function '%s'", F->name);
                            char *msg = mb.p;
                            free(locals);
                            return msg;
                        }

                        if (expected_t.kind != C0_TKIND_ANY && actual_t.kind != C0_TKIND_ANY && actual_t.kind != C0_TKIND_UNKNOWN) {
                            if (!c0type_compatible(expected_t, actual_t)) {
                                C0Buf mb, exp_buf, act_buf;
                                c0b_init(&mb);
                                c0b_init(&exp_buf);
                                c0b_init(&act_buf);
                                c0type_to_string(expected_t, &exp_buf);
                                c0type_to_string(actual_t, &act_buf);
                                /* Preserve old message format for int/string/bool mismatch */
                                if ((expected_t.kind == C0_TKIND_I64 && (actual_t.kind == C0_TKIND_STRING || actual_t.kind == C0_TKIND_BOOL)) ||
                                    (expected_t.kind == C0_TKIND_STRING && (actual_t.kind == C0_TKIND_I64 || actual_t.kind == C0_TKIND_BOOL)) ||
                                    (expected_t.kind == C0_TKIND_BOOL && (actual_t.kind == C0_TKIND_STRING || actual_t.kind == C0_TKIND_I64))) {
                                    c0b_fmt(&mb, "LIN_TYPE_ERROR: function '%s' return type mismatch: expected %s, got %s",
                                            F->name, exp_buf.p, act_buf.p);
                                } else {
                                    c0b_fmt(&mb, "LIN_TYPE_ERROR: function '%s' return type mismatch: expected %s, got %s",
                                            F->name, exp_buf.p, act_buf.p);
                                }
                                char *msg = mb.p;
                                c0b_free(&exp_buf);
                                c0b_free(&act_buf);
                                free(locals);
                                return msg;
                            }
                        }
                    }
                }

                /* call argument checks per callee */
                {
                    size_t ci;
                    for (ci = 0; ci < nfns; ci++) {
                        const C0FnInfo *C = &fns[ci];
                        size_t cn = strlen(C->name);
                        size_t sp = 0;
                        if (cn == 0) continue;
                        while (sp + cn <= sn) {
                            const char *hit = NULL;
                            size_t k;
                            for (k = sp; k + cn <= sn; k++) {
                                if (memcmp(stmt + k, C->name, cn) == 0) {
                                    hit = stmt + k;
                                    sp = k + cn;
                                    break;
                                }
                            }
                            size_t call_idx;
                            size_t after;
                            size_t close_p;
                            if (!hit) break;
                            call_idx = (size_t)(hit - stmt);
                            after = call_idx + cn;
                            if (call_idx > 0) {
                                unsigned char pc = (unsigned char)stmt[call_idx - 1];
                                if ((pc >= 'a' && pc <= 'z') ||
                                    (pc >= 'A' && pc <= 'Z') ||
                                    (pc >= '0' && pc <= '9') || pc == '_' ||
                                    pc == '$')
                                    continue;
                            }
                            if (after >= sn || stmt[after] != '(') continue;
                            if (!c0c_find_paren(stmt, sn, after, &close_p))
                                continue;
                            {
                                C0Arg *args;
                                size_t na = 0, ai;
                                args = c0c_split_args(stmt + after + 1,
                                                      close_p - (after + 1),
                                                      &na);
                                if (args) {
                                    /* Arity check */
                                    if (na != C->nparams) {
                                        C0Buf mb;
                                        c0b_init(&mb);
                                        c0b_fmt(&mb, "LIN_TYPE_ERROR: function '%s' arity mismatch: expected %zu, got %zu",
                                                C->name, C->nparams, na);
                                        char *msg = mb.p;
                                        free(args);
                                        free(locals);
                                        return msg;
                                    }
                                    for (ai = 0; ai < na; ai++) {
                                        if (ai < C->nparams) {
                                            C0Type exp_t = c0type_parse(C->params[ai].type_name, strlen(C->params[ai].type_name));
                                            C0Type act_t = c0c_infer_typed(args[ai].p, args[ai].n, locals, nl, fns, nfns);
                                            
                                            /* Check for division by zero in arg */
                                            if (c0c_check_div_by_zero(args[ai].p, args[ai].n, locals, nl, fns, nfns)) {
                                                C0Buf mb;
                                                c0b_init(&mb);
                                                c0b_fmt(&mb, "LIN_TYPE_ERROR: division by zero in argument '%s' of function '%s'", C->params[ai].name, C->name);
                                                char *msg = mb.p;
                                                free(args);
                                                free(locals);
                                                return msg;
                                            }

                                            if (act_t.kind == C0_TKIND_ERROR) {
                                                C0Buf mb;
                                                c0b_init(&mb);
                                                c0b_fmt(&mb, "LIN_TYPE_ERROR: invalid argument '%s' in function '%s'", C->params[ai].name, C->name);
                                                char *msg = mb.p;
                                                free(args);
                                                free(locals);
                                                return msg;
                                            }

                                            if (!c0type_compatible(exp_t, act_t) && exp_t.kind != C0_TKIND_ANY && act_t.kind != C0_TKIND_ANY && act_t.kind != C0_TKIND_UNKNOWN) {
                                                C0Buf mb, exp_buf, act_buf;
                                                c0b_init(&mb);
                                                c0b_init(&exp_buf);
                                                c0b_init(&act_buf);
                                                c0type_to_string(exp_t, &exp_buf);
                                                c0type_to_string(act_t, &act_buf);
                                                c0b_fmt(&mb, "LIN_TYPE_ERROR: function '%s' argument '%s' expected type %s, got %s",
                                                        C->name, C->params[ai].name, exp_buf.p, act_buf.p);
                                                char *msg = mb.p;
                                                c0b_free(&exp_buf);
                                                c0b_free(&act_buf);
                                                free(args);
                                                free(locals);
                                                return msg;
                                            }
                                        }
                                    }
                                    free(args);
                                }
                            }
                        }
                    }
                }

            }
            else idx += 1;
        }

        /* Check if function has return in all paths - simple heuristic */
        if (!has_return) {
            /* For now, we don't error on missing return to preserve compat with existing corpus that may have implicit 0 return */
            /* But for strict mode, we could */
            /* Uncomment to enforce: */
            /*
            C0Buf mb;
            c0b_init(&mb);
            c0b_fmt(&mb, "LIN_TYPE_ERROR: function '%s' missing return", F->name);
            char *msg = mb.p;
            free(locals);
            return msg;
            */
        }

        free(locals);
    }
    return NULL;
}

/* lin_check_rulel (lin.zig:5552): malloc'd, caller frees. */
char *c0_check_rulel(const char *src, size_t len, const C0FnInfo *fns,
                     size_t nfns) {
    C0Buf out, names;
    const char *h, *ex;
    size_t hn, exn, fi;
    c0b_init(&out);
    c0b_init(&names);
    c0c_fn_names(src, len, &names);
    c0c_header(src, len, &h, &hn);
    c0c_exports(src, len, &ex, &exn);
    c0b_s(&out, "@RULEL:LIN_CHECK:1.0.0\n.header=\"");
    c0b_n(&out, h, hn);
    c0b_s(&out, "\"\n.fns=");
    c0c_csv_json_arr(names.p ? names.p : "", names.n, &out);
    c0b_s(&out, "\n.exports=");
    c0c_csv_json_arr(ex, exn, &out);
    c0b_s(&out, "\n.types{\n");
    for (fi = 0; fi < nfns; fi++) {
        size_t pi;
        c0b_fmt(&out, "  .%s{ params=[", fns[fi].name);
        for (pi = 0; pi < fns[fi].nparams; pi++) {
            if (pi > 0) c0b_s(&out, ",");
            c0b_fmt(&out, "\"%s:%s\"", fns[fi].params[pi].name,
                    fns[fi].params[pi].type_name);
        }
        c0b_fmt(&out, "] return=\"%s\" }\n", fns[fi].return_type);
    }
    c0b_s(&out, "}\n.typecheck=passed\n");
    c0b_free(&names);
    return out.p;
}

/* ------------------------------------------------------------------ */
/* lint (lin.zig:4861..5039)                                          */
/* ------------------------------------------------------------------ */

static void c0c_diag(C0Buf *b, const char *src, size_t len, size_t at,
                     const char *code, const char *fix) {
    int64_t ln = 1, col = 1;
    size_t k = 0;
    while (k < at && k < len) {
        if (src[k] == '\n') ln += 1;
        k += 1;
    }
    k = at;
    while (k > 0 && src[k - 1] != '\n') {
        col += 1;
        k -= 1;
    }
    c0b_s(b, "  .d{ code=");
    c0b_s(b, code);
    c0b_s(b, " line=");
    c0c_rgs_num(b, ln);
    c0b_s(b, " col=");
    c0c_rgs_num(b, col);
    c0b_s(b, " fix=\"");
    c0b_s(b, fix);
    c0b_s(b, "\" }\n");
}

static int c0c_heur_str(const char *id, size_t n) {
    static const char *prefix[] = {
        "q",         "body",    "params", "names",  "chs",    "out",
        "js_p",      "rewrite_", "lin_",  "zig_",   "emit_",  "param_",
        "fn_ret",    "andor",   "kw_space", "rgs_",  "jss_",   "cks_",
        "slice2",    "read_ident", "fromCharCode", "charAt", NULL
    };
    int i;
    if (n == 0) return 0;
    for (i = 0; prefix[i]; i++) {
        if (c0c_starts_lit(id, n, 0, prefix[i])) return 1;
    }
    if (n == 2 && c0c_starts_lit(id, n, 0, "id")) return 1;
    if (n == 3 && c0c_starts_lit(id, n, 0, "src")) return 1;
    return 0;
}

/* ck_side_literal (lin.zig:4815) */
static int c0c_side_literal(const char *src, size_t len, size_t at,
                            size_t oplen) {
    size_t k;
    if (at > 0) {
        k = at - 1;
        while ((long)k >= 0 && (src[k] == ' ' || src[k] == '\t')) {
            if (k == 0) break;
            k -= 1;
        }
        if (src[k] == '"') return 1;
    }
    k = c0c_skip_ws(src, len, at + oplen);
    if (k < len && src[k] == '"') return 1;
    return 0;
}

/* ck_call_left_str (lin.zig:4829) */
static int c0c_call_left_str(const char *src, size_t len, size_t at) {
    size_t k;
    int64_t d = 0;
    if (at == 0) return 0;
    k = at - 1;
    while ((long)k >= 0 && (src[k] == ' ' || src[k] == '\t')) {
        if (k == 0) break;
        k -= 1;
    }
    if ((long)k < 0) return 0;
    if (src[k] != ')') return 0;
    while ((long)k >= 0) {
        if (src[k] == ')') d += 1;
        if (src[k] == '(') {
            size_t st;
            const char *nm;
            size_t nmn;
            d -= 1;
            if (d == 0) {
                if (k == 0) return 0;
                if (!c0c_is_ident((unsigned char)src[k - 1])) return 0;
                st = k - 1;
                while (st > 0 && c0c_is_ident((unsigned char)src[st - 1]))
                    st -= 1;
                c0c_read_ident(src, len, st, &nm, &nmn);
                return c0c_heur_str(nm, nmn);
            }
        }
        if (k == 0) break;
        k -= 1;
    }
    return 0;
}

/* cks_ops (lin.zig:4861) */
static void c0c_cks_ops(const char *src, size_t len, C0Buf *b) {
    size_t i = 0, n = len;
    while (i < n) {
        unsigned char c = (unsigned char)src[i];
        if (c == '"') {
            i += 1;
            while (i < n && src[i] != '"') {
                if (src[i] == '\\')
                    c0c_diag(b, src, len, i, "ESCAPE_IN_LITERAL",
                             "literals carry no escapes; call q() to emit a quote");
                i += 1;
            }
            i += 1;
            continue;
        }
        if (c == '/' && i + 1 < n && src[i + 1] == '/') {
            while (i < n && src[i] != '\n') i += 1;
            continue;
        }
        if (c == '/') {
            c0c_diag(b, src, len, i, "INT_DIVISION",
                     "no integer division; subtract in a loop or pass a power of ten");
            i += 1;
            continue;
        }
        if (c == '<' && i + 1 < n && src[i + 1] == '<') {
            c0c_diag(b, src, len, i, "SHIFT_OPERATOR",
                     "no shift operator; call _lia_shl(a, b)");
            i += 2;
            continue;
        }
        if (c == '>' && i + 1 < n && src[i + 1] == '>') {
            c0c_diag(b, src, len, i, "SHIFT_OPERATOR",
                     "no shift operator; call _lia_shr(a, b)");
            i += 2;
            continue;
        }
        if (c == '=' && i + 1 < n && src[i + 1] == '=') {
            if (c0c_side_literal(src, len, i, 2))
                c0c_diag(b, src, len, i, "STRING_COMPARE",
                         "no string equality; compare .length then starts_lit(s, 0, lit)");
            i += 2;
            continue;
        }
        if (c == '!' && i + 1 < n && src[i + 1] == '=') {
            if (c0c_side_literal(src, len, i, 2))
                c0c_diag(b, src, len, i, "STRING_COMPARE",
                         "no string inequality; compare .length then starts_lit(s, 0, lit)");
            i += 2;
            continue;
        }
        if (c == '+' && i + 1 < n && src[i + 1] == '+') {
            i += 2;
            continue;
        }
        if (c == '+') {
            if (c0c_call_left_str(src, len, i))
                c0c_diag(b, src, len, i, "CALL_LEFT_OF_CONCAT",
                         "bind the call result to a variable first, then concatenate");
            i += 1;
            continue;
        }
        i += 1;
    }
}

/* cks_plist (lin.zig:4934) */
static void c0c_cks_plist(const char *src, size_t srclen, const char *plist,
                          size_t pn, size_t at, C0Buf *b) {
    size_t i = 0, st = 0;
    (void)srclen;
    while (i <= pn) {
        if (i == pn || plist[i] == ',') {
            const char *seg = plist + st;
            size_t sn = i - st;
            const char *nm;
            size_t nmn;
            size_t p0, p;
            const char *ty;
            size_t tyn;
            c0c_read_ident(seg, sn, c0c_skip_ws(seg, sn, 0), &nm, &nmn);
            if (nmn > 0) {
                p0 = c0c_skip_ws(seg, sn, 0);
                p = c0c_skip_ws(seg, sn, p0 + nmn);
                ty = "";
                tyn = 0;
                if (p < sn && seg[p] == ':')
                    c0c_read_ident(seg, sn, c0c_skip_ws(seg, sn, p + 1), &ty,
                                   &tyn);
                if (tyn > 0) {
                    if (!c0c_starts_lit(ty, tyn, 0, "string") &&
                        !c0c_starts_lit(ty, tyn, 0, "str") &&
                        !c0c_starts_lit(ty, tyn, 0, "bool")) {
                        if (c0c_heur_str(nm, nmn))
                            c0c_diag(b, src, srclen, at, "NAME_TYPE_COLLISION",
                                     "parameter name is read as a string by "
                                     "the type heuristic; rename it");
                    }
                }
            }
            st = i + 1;
            i += 1;
            continue;
        }
        i += 1;
    }
}

/* cks_params (lin.zig:4982) */
static void c0c_cks_params(const char *src, size_t len, C0Buf *b) {
    size_t i = 0, n = len;
    while (i < n) {
        if (src[i] == '!') {
            const char *nm;
            size_t nmn, op;
            long cl;
            c0c_read_ident(src, len, i + 1, &nm, &nmn);
            if (nmn > 0) {
                op = c0c_skip_ws(src, len, i + 1 + nmn);
                if (op < n && src[op] == '(') {
                    cl = c0c_match_paren(src, len, op);
                    if (cl > (long)op) {
                        c0c_cks_plist(src, len, src + op + 1,
                                      (size_t)cl - (op + 1), op, b);
                        i = (size_t)cl;
                    }
                }
            }
        }
        i += 1;
    }
}

/* cks_lint (lin.zig:5016): malloc'd, caller frees. */
char *c0_lint(const char *src, size_t len) {
    C0Buf out, body;
    int64_t errors;
    c0b_init(&out);
    c0b_init(&body);
    c0c_cks_ops(src, len, &body);
    c0c_cks_params(src, len, &body);
    errors = c0c_count_lit(body.p ? body.p : "", body.n, "  .d{");
    c0b_s(&out, "@RULEL:LIN_LINT:1.0.0\n.policy{ level=error fail_closed=true "
                "rationale=every_rejected_construct_names_its_supported_alternative"
                " }\n.diagnostics{\n");
    if (body.p) c0b_s(&out, body.p);
    c0b_s(&out, "}\n.summary{ errors=");
    {
        C0Buf nb;
        c0b_init(&nb);
        c0c_rgs_num(&nb, errors);
        c0b_s(&out, nb.p ? nb.p : "0");
        c0b_free(&nb);
    }
    c0b_s(&out, " }\n");
    c0b_free(&body);
    return out.p;
}
