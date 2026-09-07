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
 */
#include "lin_c0_front.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
/* infer_expr_type (lin.zig:5204)                                     */
/* ------------------------------------------------------------------ */

typedef struct {
    const char *name;
    size_t nlen;
    const char *type;
} C0Local;

static const char *c0c_local_get(const C0Local *locals, size_t n,
                                 const char *name, size_t nlen) {
    size_t i;
    for (i = 0; i < n; i++) {
        if (locals[i].nlen == nlen && memcmp(locals[i].name, name, nlen) == 0)
            return locals[i].type;
    }
    return NULL;
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

static const char *c0c_infer(const char *expr, size_t elen,
                             const C0Local *locals, size_t nlocals,
                             const C0FnInfo *fns, size_t nfns);

static const char *c0c_infer(const char *expr, size_t elen,
                             const C0Local *locals, size_t nlocals,
                             const C0FnInfo *fns, size_t nfns) {
    const char *t = expr;
    size_t n = elen;
    size_t k;
    c0c_trim_set(&t, &n, " \t\r\n;");
    if (n == 0) return "any";
    if (n >= 2 && t[0] == '"' && t[n - 1] == '"') return "string";
    if (c0c_eq(t, n, "true") || c0c_eq(t, n, "false")) return "bool";
    if (c0c_is_valid_ident(t, n)) {
        const char *lt = c0c_local_get(locals, nlocals, t, n);
        return lt ? lt : "any";
    }
    if (c0c_is_integer_literal(t, n)) return "int";
    /* call: name(...) with trailing ')' */
    for (k = 0; k < n; k++) {
        if (t[k] == '(') {
            if (t[n - 1] == ')') {
                const char *cn = t;
                size_t cn_n = k, fi;
                c0c_trim_set(&cn, &cn_n, " \t");
                for (fi = 0; fi < nfns; fi++) {
                    if (c0c_eq(cn, cn_n, fns[fi].name)) return fns[fi].return_type;
                }
            }
            break;
        }
    }
    if (c0c_has_top_op(t, n, "==") || c0c_has_top_op(t, n, "!=") ||
        c0c_has_top_op(t, n, "<=") || c0c_has_top_op(t, n, ">=") ||
        c0c_has_top_op(t, n, "<") || c0c_has_top_op(t, n, ">"))
        return "bool";
    if (c0c_has_top_op(t, n, "&&") || c0c_has_top_op(t, n, "||") ||
        c0c_has_top_op(t, n, " and ") || c0c_has_top_op(t, n, " or "))
        return "bool";
    if (c0c_has_top_op(t, n, "+")) {
        const char *L, *R;
        size_t Ln, Rn;
        if (c0c_split_top_op(t, n, '+', &L, &Ln, &R, &Rn)) {
            const char *tl = c0c_infer(L, Ln, locals, nlocals, fns, nfns);
            const char *tr = c0c_infer(R, Rn, locals, nlocals, fns, nfns);
            if (strcmp(tl, "string") == 0 || strcmp(tr, "string") == 0)
                return "string";
            if (strcmp(tl, "int") == 0 && strcmp(tr, "int") == 0) return "int";
        }
        return "int";
    }
    if (c0c_has_top_op(t, n, "-") || c0c_has_top_op(t, n, "*") ||
        c0c_has_top_op(t, n, "/") || c0c_has_top_op(t, n, "%"))
        return "int";
    if (n >= 2 && t[0] == '(' && t[n - 1] == ')')
        return c0c_infer(t + 1, n - 2, locals, nlocals, fns, nfns);
    return "any";
}

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

static void c0c_local_put(C0Local **locals, size_t *n, size_t *cap,
                          const char *name, size_t nlen, const char *type) {
    size_t i;
    for (i = 0; i < *n; i++) {
        if ((*locals)[i].nlen == nlen && memcmp((*locals)[i].name, name, nlen) == 0) {
            (*locals)[i].type = type;
            return;
        }
    }
    if (*n == *cap) {
        size_t nc = *cap ? *cap * 2 : 16;
        C0Local *nl = (C0Local *)realloc(*locals, nc * sizeof(C0Local));
        if (!nl) return;
        *locals = nl;
        *cap = nc;
    }
    (*locals)[*n].name = name;
    (*locals)[*n].nlen = nlen;
    (*locals)[*n].type = type;
    *n += 1;
}

/* lin_type_check (lin.zig:5396): NULL when clean, else malloc'd message. */
char *c0_type_check(const C0FnInfo *fns, size_t nfns) {
    size_t fi;
    for (fi = 0; fi < nfns; fi++) {
        const C0FnInfo *F = &fns[fi];
        C0Local *locals = NULL;
        size_t nl = 0, capl = 0, pi, idx = 0, stmt_start = 0;
        int in_quote = 0;
        int64_t pd = 0, bd = 0;
        for (pi = 0; pi < F->nparams; pi++)
            c0c_local_put(&locals, &nl, &capl, F->params[pi].name,
                          strlen(F->params[pi].name), F->params[pi].type_name);
        while (idx <= F->body_len) {
            int is_end = 0;
            if (idx == F->body_len) is_end = 1;
            else {
                unsigned char ch = (unsigned char)F->body[idx];
                if (ch == '"') in_quote = !in_quote;
                if (!in_quote) {
                    if (ch == '(') pd += 1;
                    else if (ch == ')') pd -= 1;
                    else if (ch == '{') bd += 1;
                    else if (ch == '}') bd -= 1;
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
                /* assignment: FIRST '=' with scalar context checks */
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
                        if (c0c_is_valid_ident(lhs, ln_)) {
                            const char *rt = c0c_infer(rhs, rn_, locals, nl, fns, nfns);
                            c0c_local_put(&locals, &nl, &capl, lhs, ln_, rt);
                        }
                    }
                }
                /* return: ^expr or "return " */
                {
                    const char *rx = NULL;
                    size_t rxn = 0;
                    if (stmt[0] == '^') {
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
                        const char *actual =
                            c0c_infer(rx, rxn, locals, nl, fns, nfns);
                        if (strcmp(F->return_type, "any") != 0 &&
                            strcmp(actual, "any") != 0) {
                            char *msg = NULL;
                            const char *exp = F->return_type;
                            int bad = 0;
                            if (strcmp(exp, "int") == 0 &&
                                (strcmp(actual, "string") == 0 ||
                                 strcmp(actual, "bool") == 0))
                                bad = 1;
                            else if (strcmp(exp, "string") == 0 &&
                                     (strcmp(actual, "int") == 0 ||
                                      strcmp(actual, "bool") == 0))
                                bad = 1;
                            else if (strcmp(exp, "bool") == 0 &&
                                     (strcmp(actual, "string") == 0 ||
                                      strcmp(actual, "int") == 0))
                                bad = 1;
                            if (bad) {
                                C0Buf mb;
                                c0b_init(&mb);
                                c0b_fmt(&mb,
                                        "LIN_TYPE_ERROR: function '%s' return "
                                        "type mismatch: expected %s, got %s",
                                        F->name, exp, actual);
                                msg = mb.p;
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
                                unsigned char pc =
                                    (unsigned char)stmt[call_idx - 1];
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
                                    for (ai = 0; ai < na; ai++) {
                                        if (ai < C->nparams) {
                                            const char *exp =
                                                C->params[ai].type_name;
                                            const char *act = c0c_infer(
                                                args[ai].p, args[ai].n,
                                                locals, nl, fns, nfns);
                                            if (strcmp(exp, "any") != 0 &&
                                                strcmp(act, "any") != 0 &&
                                                strcmp(exp, act) != 0) {
                                                C0Buf mb;
                                                char *msg;
                                                c0b_init(&mb);
                                                c0b_fmt(&mb,
                                                        "LIN_TYPE_ERROR: "
                                                        "function '%s' "
                                                        "argument '%s' "
                                                        "expected type %s, "
                                                        "got %s",
                                                        C->name,
                                                        C->params[ai].name,
                                                        exp, act);
                                                msg = mb.p;
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
