/*
 * lin_c0_front.c — Compiler 0 front-end: LIN source -> VmModule (host C11).
 *
 * Line-by-line port of the Stage0 Zig front-end. Every divergence from
 * compiler/lin.zig is marked "C adaptation" and is required by C, never by
 * choice; the emitted instruction stream, the rejection codes and their
 * ORDER are meant to be identical, because the published goldens
 * (P1_LINVM_SELFHOST.rulel §3, docs/LINVM0_V2_FRONTIER.rulel) pin exact
 * `value` AND `steps`.
 *
 * Zig source map (compiler/lin.zig):
 *   5287  parse_fn_type_infos      -> c0_parse_fn_infos
 *   5663  VmTok / vmTokenize       -> C0Tok / c0_tokenize
 *   5733  VmComp                   -> C0Comp + the c0_* recursive descent
 *   6262  vmArrLenOf               -> c0_arr_len_of
 *   6275  vmSigEligible            -> c0_sig_eligible
 *   6284  vmResolveDeps            -> c0_resolve_deps
 *   6296  vmBuild                  -> c0_build
 */
#include "lin_c0_front.h"
#include "lin_common.h"
#include "lin_linbc1.h"
#include "lin_sha256.h"

#include <stdlib.h>
#include <string.h>

/* =====================================================================
 * Arena
 * ===================================================================== */

typedef struct C0Chunk {
    struct C0Chunk *next;
    size_t cap;
    size_t used;
    char   mem[1];                    /* flexible tail, over-allocated */
} C0Chunk;

/*
 * Chunked bump arena. A single realloc'd block would MOVE previously handed
 * out pointers, and c0_build hands out VmFn/VmIns pointers that stay live
 * while later functions keep allocating — so chunks are never moved.
 */
struct C0Arena {
    C0Chunk *head;
};

#define C0_CHUNK_DEFAULT (1u << 16)

static C0Chunk *c0_chunk_new(size_t payload) {
    size_t cap = payload > C0_CHUNK_DEFAULT ? payload : C0_CHUNK_DEFAULT;
    C0Chunk *c = (C0Chunk *)malloc(sizeof(C0Chunk) - 1 + cap);
    if (!c) return NULL;
    c->next = NULL;
    c->cap = cap;
    c->used = 0;
    return c;
}

C0Arena *c0_arena_new(void) {
    C0Arena *a = (C0Arena *)malloc(sizeof(C0Arena));
    if (!a) return NULL;
    a->head = c0_chunk_new(0);
    if (!a->head) { free(a); return NULL; }
    return a;
}

void c0_arena_free(C0Arena *a) {
    C0Chunk *c;
    if (!a) return;
    c = a->head;
    while (c) {
        C0Chunk *nx = c->next;
        free(c);
        c = nx;
    }
    free(a);
}

void *c0_arena_alloc(C0Arena *a, size_t n) {
    size_t aligned = (n + 7u) & ~(size_t)7u;
    void *p;
    if (n == 0) { n = 1; aligned = 8; }
    if (a->head->used + aligned > a->head->cap) {
        C0Chunk *nc = c0_chunk_new(aligned);
        if (!nc) return NULL;
        nc->next = a->head;
        a->head = nc;
    }
    p = a->head->mem + a->head->used;
    a->head->used += aligned;
    memset(p, 0, aligned);
    return p;
}

char *c0_arena_strdup_n(C0Arena *a, const char *s, size_t n) {
    char *p = (char *)c0_arena_alloc(a, n + 1);
    if (!p) return NULL;
    if (n) memcpy(p, s, n);
    p[n] = '\0';
    return p;
}

/* =====================================================================
 * parse_fn_type_infos (lin.zig:5287)
 * ===================================================================== */

static int c0_is_name_char(uint8_t c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
           (c >= '0' && c <= '9') || c == '_' || c == '$';
}

static int c0_is_space(uint8_t c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

/* std.mem.trim(u8, s, " \t\r\n") over a (ptr,len) view. */
static void c0_trim(const char **p, size_t *n) {
    while (*n > 0 && c0_is_space((uint8_t)(*p)[0])) { (*p)++; (*n)--; }
    while (*n > 0 && c0_is_space((uint8_t)(*p)[*n - 1])) { (*n)--; }
}

/* std.mem.indexOfScalar(u8, s, ch) -> index or SIZE_MAX. */
static size_t c0_index_char(const char *s, size_t n, char ch) {
    for (size_t i = 0; i < n; i++) if (s[i] == ch) return i;
    return SIZE_MAX;
}

/* std.mem.indexOf(u8, hay, needle) -> index or SIZE_MAX. */
static size_t c0_index_str(const char *s, size_t n, const char *needle, size_t nl) {
    if (nl > n) return SIZE_MAX;
    for (size_t i = 0; i + nl <= n; i++)
        if (memcmp(s + i, needle, nl) == 0) return i;
    return SIZE_MAX;
}

const C0FnInfo *c0_parse_fn_infos(C0Arena *a, const char *src, size_t len, size_t *out_n) {
    C0FnInfo *list = NULL;
    size_t n_list = 0, cap_list = 0;
    size_t i = 0;
    size_t current_line = 1;

    *out_n = 0;
    while (i < len) {
        if (src[i] == '\n') current_line += 1;
        if (src[i] == '!' && (i + 1 >= len || src[i + 1] != '=')) {
            size_t fn_line = current_line;
            size_t pos = i + 1;
            const char *fn_name;
            size_t name_len;
            size_t open_p, close_p, hdr_end, brace_open, brace_close, bpos;
            int64_t paren_depth, brace_depth;
            const char *raw_params;
            size_t raw_len;
            C0Param *params = NULL;
            size_t nparams = 0, cap_params = 0;
            const char *hdr_extra;
            size_t hdr_len;
            const char *ret_type = "any";
            int oom = 0;

            while (pos < len && c0_is_space((uint8_t)src[pos])) {
                if (src[pos] == '\n') current_line += 1;
                pos += 1;
            }
            name_len = 0;
            while (pos < len && c0_is_name_char((uint8_t)src[pos])) { pos += 1; name_len += 1; }
            fn_name = src + (pos - name_len);

            if (name_len > 0 && pos < len && src[pos] == '(') {
                open_p = pos;
                paren_depth = 1;
                pos += 1;
                while (pos < len && paren_depth > 0) {
                    if (src[pos] == '\n') current_line += 1;
                    if (src[pos] == '"') {
                        pos += 1;
                        while (pos < len && src[pos] != '"') {
                            if (src[pos] == '\n') current_line += 1;
                            pos += 1;
                        }
                        if (pos < len) pos += 1;
                        continue;
                    }
                    if (src[pos] == '(') paren_depth += 1;
                    else if (src[pos] == ')') paren_depth -= 1;
                    pos += 1;
                }
                close_p = pos - 1;                       /* C: may wrap to SIZE_MAX if pos==0; pos>=1 here */
                raw_params = src + open_p + 1;
                raw_len = (close_p >= open_p + 1) ? (close_p - (open_p + 1)) : 0;

                /* parameters: split raw_params on ',' */
                {
                    size_t p_at = 0;
                    while (p_at <= raw_len) {
                        size_t comma = c0_index_char(raw_params + p_at, raw_len - p_at, ',');
                        size_t piece_len = (comma == SIZE_MAX) ? (raw_len - p_at) : comma;
                        const char *piece = raw_params + p_at;
                        const char *pn;
                        const char *pt;
                        size_t pn_len, pt_len;
                        c0_trim(&piece, &piece_len);
                        if (piece_len > 0) {
                            size_t colon = c0_index_char(piece, piece_len, ':');
                            if (colon != SIZE_MAX) {
                                pn = piece;            pn_len = colon;
                                pt = piece + colon + 1; pt_len = piece_len - colon - 1;
                                c0_trim(&pn, &pn_len);
                                c0_trim(&pt, &pt_len);
                            } else {
                                pn = piece; pn_len = piece_len;
                                pt = "any"; pt_len = 3;
                            }
                            if (nparams == cap_params) {
                                size_t nc = cap_params ? cap_params * 2 : 8;
                                C0Param *np = (C0Param *)realloc(params, nc * sizeof(C0Param));
                                if (!np) { oom = 1; break; }
                                params = np; cap_params = nc;
                            }
                            params[nparams].name = c0_arena_strdup_n(a, pn, pn_len);
                            params[nparams].type_name = c0_arena_strdup_n(a, pt, pt_len);
                            if (!params[nparams].name || !params[nparams].type_name) { oom = 1; break; }
                            nparams += 1;
                        }
                        if (comma == SIZE_MAX) break;
                        p_at += comma + 1;
                    }
                }

                /* return type: everything between ')' and '{' */
                hdr_end = pos;
                while (hdr_end < len && src[hdr_end] != '{') {
                    if (src[hdr_end] == '\n') current_line += 1;
                    hdr_end += 1;
                }
                hdr_extra = src + pos;
                hdr_len = hdr_end - pos;
                {
                    size_t arrow = c0_index_str(hdr_extra, hdr_len, "->", 2);
                    if (arrow != SIZE_MAX) {
                        const char *rt = hdr_extra + arrow + 2;
                        size_t rt_len = hdr_len - arrow - 2;
                        c0_trim(&rt, &rt_len);
                        ret_type = c0_arena_strdup_n(a, rt, rt_len);
                    } else {
                        size_t colon = c0_index_char(hdr_extra, hdr_len, ':');
                        if (colon != SIZE_MAX) {
                            const char *rt = hdr_extra + colon + 1;
                            size_t rt_len = hdr_len - colon - 1;
                            c0_trim(&rt, &rt_len);
                            ret_type = c0_arena_strdup_n(a, rt, rt_len);
                        }
                    }
                }
                if (!ret_type) oom = 1;

                if (!oom && hdr_end < len && src[hdr_end] == '{') {
                    brace_open = hdr_end;
                    brace_depth = 1;
                    bpos = brace_open + 1;
                    while (bpos < len && brace_depth > 0) {
                        if (src[bpos] == '\n') current_line += 1;
                        if (src[bpos] == '"') {
                            bpos += 1;
                            while (bpos < len && src[bpos] != '"') {
                                if (src[bpos] == '\n') current_line += 1;
                                bpos += 1;
                            }
                            if (bpos < len) bpos += 1;
                            continue;
                        }
                        if (src[bpos] == '{') brace_depth += 1;
                        else if (src[bpos] == '}') brace_depth -= 1;
                        bpos += 1;
                    }
                    brace_close = bpos - 1;

                    if (n_list == cap_list) {
                        size_t nc = cap_list ? cap_list * 2 : 16;
                        C0FnInfo *nl = (C0FnInfo *)realloc(list, nc * sizeof(C0FnInfo));
                        if (!nl) { oom = 1; }
                        else { list = nl; cap_list = nc; }
                    }
                    if (!oom) {
                        list[n_list].name = c0_arena_strdup_n(a, fn_name, name_len);
                        list[n_list].params = params;
                        list[n_list].nparams = nparams;
                        list[n_list].return_type = ret_type;
                        list[n_list].body = src + brace_open + 1;
                        list[n_list].body_len = (brace_close >= brace_open + 1)
                                                    ? (brace_close - (brace_open + 1)) : 0;
                        list[n_list].line = fn_line;
                        if (!list[n_list].name) oom = 1;
                        else n_list += 1;
                        params = NULL;      /* ownership moved into the list */
                    }
                    i = bpos;
                    free(params);
                    if (oom) { free(list); return NULL; }
                    continue;
                }
                free(params);
            }
            if (oom) { free(list); return NULL; }
        }
        i += 1;
    }
    *out_n = n_list;
    return list;
}

/* =====================================================================
 * vmTokenize (lin.zig:5678)
 * ===================================================================== */

typedef enum { C0_TK_IDENT, C0_TK_NUMBER, C0_TK_PUNCT, C0_TK_STR, C0_TK_EOF } C0TokKind;

typedef struct {
    C0TokKind kind;
    const char *text;
    size_t len;
} C0Tok;

static int c0_is_ident_start(uint8_t c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c == '$';
}
static int c0_is_ident_part(uint8_t c) {
    return c0_is_ident_start(c) || (c >= '0' && c <= '9');
}

#define C0_OOM ((const char *)1)   /* sentinel: never equals a VM_REJ_* code */

static C0Tok *c0_tokenize(const char *src, size_t len, size_t *out_n) {
    C0Tok *out = NULL;
    size_t n = 0, cap = 0;
    size_t i = 0;

#define TOK_APPEND(k, s, l)                                            \
    do {                                                               \
        if (n == cap) {                                                \
            size_t nc_ = cap ? cap * 2 : 64;                           \
            C0Tok *np_ = (C0Tok *)realloc(out, nc_ * sizeof(C0Tok));    \
            if (!np_) { free(out); return NULL; }                      \
            out = np_; cap = nc_;                                      \
        }                                                              \
        out[n].kind = (k); out[n].text = (s); out[n].len = (l); n += 1; \
    } while (0)

    while (i < len) {
        uint8_t c = (uint8_t)src[i];
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') { i += 1; continue; }
        if (c == '/' && i + 1 < len && src[i + 1] == '/') {
            while (i < len && src[i] != '\n') i += 1;
            continue;
        }
        if (c == '"') {
            size_t start = i;
            i += 1;
            while (i < len && src[i] != '"') {
                if (src[i] == '\\' && i + 1 < len) i += 1;
                i += 1;
            }
            if (i < len) i += 1;
            TOK_APPEND(C0_TK_STR, src + start, i - start);
            continue;
        }
        if (c >= '0' && c <= '9') {
            size_t start = i;
            while (i < len && src[i] >= '0' && src[i] <= '9') i += 1;
            TOK_APPEND(C0_TK_NUMBER, src + start, i - start);
            continue;
        }
        if (c0_is_ident_start(c)) {
            size_t start = i;
            while (i < len && c0_is_ident_part((uint8_t)src[i])) i += 1;
            TOK_APPEND(C0_TK_IDENT, src + start, i - start);
            continue;
        }
        if (i + 1 < len) {
            static const char *const TWO[] = { "==", "!=", "<=", ">=", "&&", "||", "->", "<<", ">>" };
            int is_two = 0;
            for (size_t k = 0; k < sizeof(TWO) / sizeof(TWO[0]); k++)
                if (memcmp(src + i, TWO[k], 2) == 0) { is_two = 1; break; }
            if (is_two) {
                TOK_APPEND(C0_TK_PUNCT, src + i, 2);
                i += 2;
                continue;
            }
        }
        TOK_APPEND(C0_TK_PUNCT, src + i, 1);
        i += 1;
    }
    TOK_APPEND(C0_TK_EOF, "", 0);
#undef TOK_APPEND
    *out_n = n;
    return out;
}

/* =====================================================================
 * VmComp (lin.zig:5733)
 * ===================================================================== */

typedef struct {
    C0Arena *al;
    C0Tok *toks;
    size_t ntoks;
    size_t pos;

    VmIns *code;
    size_t ncode, code_cap;

    const char **locals;
    size_t nlocals, locals_cap;

    uint16_t *arr_n;
    size_t narrn, arrn_cap;

    VmFn *fns;
    size_t nfns;

    const char *reject;   /* NULL = no rejection; C0_OOM = arena exhausted */
    int allow_div;        /* profile full: emit OP_DIV/OP_MOD instead of reject */
    int allow_shift;      /* profile full: emit OP_SHL/OP_SHR/OP_USHR */
} C0Comp;

static int c0_tok_eq(const C0Tok *t, const char *s) {
    size_t n = strlen(s);
    return t->len == n && (n == 0 || memcmp(t->text, s, n) == 0);
}

static C0Tok c0_peek(C0Comp *c) { return c->toks[c->pos]; }

static C0Tok c0_bump(C0Comp *c) {
    C0Tok tk = c->toks[c->pos];
    if (tk.kind != C0_TK_EOF) c->pos += 1;
    return tk;
}

static int c0_at_punct(C0Comp *c, const char *t) {
    const C0Tok *tk = &c->toks[c->pos];
    return tk->kind == C0_TK_PUNCT && c0_tok_eq(tk, t);
}

static int c0_at_ident(C0Comp *c, const char *t) {
    const C0Tok *tk = &c->toks[c->pos];
    return tk->kind == C0_TK_IDENT && c0_tok_eq(tk, t);
}

static int c0_accept_punct(C0Comp *c, const char *t) {
    if (c0_at_punct(c, t)) { (void)c0_bump(c); return 1; }
    return 0;
}

static void c0_fail(C0Comp *c, const char *code) {
    if (c->reject == NULL) c->reject = code;
}

static size_t c0_emit(C0Comp *c, VmOp op, int64_t a) {
    if (c->ncode == c->code_cap) {
        size_t nc = c->code_cap ? c->code_cap * 2 : 256;
        VmIns *np = (VmIns *)realloc(c->code, nc * sizeof(VmIns));
        if (!np) { c0_fail(c, C0_OOM); return 0; }
        c->code = np;
        c->code_cap = nc;
    }
    c->code[c->ncode].op = op;
    c->code[c->ncode].a = a;
    c->ncode += 1;
    return c->ncode - 1;
}

static int64_t c0_here(C0Comp *c) { return (int64_t)c->ncode; }

static void c0_patch(C0Comp *c, size_t at) { c->code[at].a = c0_here(c); }

static int64_t c0_find_local(C0Comp *c, const char *name, size_t nlen) {
    for (size_t i = 0; i < c->nlocals; i++) {
        size_t l = strlen(c->locals[i]);
        if (l == nlen && memcmp(c->locals[i], name, nlen) == 0) return (int64_t)i;
    }
    return -1;
}

static int64_t c0_local_idx(C0Comp *c, const char *name, size_t nlen) {
    int64_t v = c0_find_local(c, name, nlen);
    char *copy;
    if (v >= 0) return v;
    if (c->nlocals >= LIN_VM_MAX_LOCALS) {
        c0_fail(c, "VM_REJ_TOO_MANY_LOCALS");
        return 0;
    }
    if (c->nlocals == c->locals_cap) {
        size_t nc = c->locals_cap ? c->locals_cap * 2 : 16;
        const char **np = (const char **)realloc(c->locals, nc * sizeof(char *));
        if (!np) { c0_fail(c, C0_OOM); return 0; }
        c->locals = np;
        c->locals_cap = nc;
    }
    if (c->narrn == c->arrn_cap) {
        size_t nc = c->arrn_cap ? c->arrn_cap * 2 : 16;
        uint16_t *np = (uint16_t *)realloc(c->arr_n, nc * sizeof(uint16_t));
        if (!np) { c0_fail(c, C0_OOM); return 0; }
        c->arr_n = np;
        c->arrn_cap = nc;
    }
    copy = c0_arena_strdup_n(c->al, name, nlen);
    if (!copy) { c0_fail(c, C0_OOM); return 0; }
    c->locals[c->nlocals] = copy;
    c->arr_n[c->narrn] = 0;
    c->nlocals += 1;
    c->narrn += 1;
    return (int64_t)(c->nlocals - 1);
}

static uint16_t c0_local_arr_n(C0Comp *c, int64_t li) {
    if (li < 0 || (size_t)li >= c->narrn) return 0;
    return c->arr_n[li];
}

static void c0_mark_arr(C0Comp *c, int64_t li, uint16_t n) {
    if (li >= 0 && (size_t)li < c->narrn) c->arr_n[li] = n;
}

static int64_t c0_find_fn(C0Comp *c, const char *name, size_t nlen) {
    for (size_t i = 0; i < c->nfns; i++) {
        size_t l = strlen(c->fns[i].name);
        if (c->fns[i].sig_ok && l == nlen && memcmp(c->fns[i].name, name, nlen) == 0)
            return (int64_t)i;
    }
    return -1;
}

/* ---- recursive descent (lin.zig:5831-6290) ---- */

static void c0_expr(C0Comp *c);
static void c0_e_or(C0Comp *c);
static void c0_e_and(C0Comp *c);
static void c0_e_cmp(C0Comp *c);
static void c0_e_shift(C0Comp *c);
static void c0_e_bor(C0Comp *c);
static void c0_e_bxor(C0Comp *c);
static void c0_e_band(C0Comp *c);
static void c0_e_add(C0Comp *c);
static void c0_e_mul(C0Comp *c);
static void c0_e_unary(C0Comp *c);
static void c0_e_primary(C0Comp *c);
static void c0_emit_arr_lit(C0Comp *c, int64_t li, uint16_t cap);
static void c0_assign(C0Comp *c);
static void c0_block(C0Comp *c);
static void c0_stmt(C0Comp *c);

static void c0_expr(C0Comp *c) { c0_e_or(c); }

static void c0_e_or(C0Comp *c) {
    c0_e_and(c);
    while (c->reject == NULL && c0_at_punct(c, "||")) {
        size_t j;
        (void)c0_bump(c);
        j = c0_emit(c, OP_JUMP_IF_TRUE_KEEP, 0);
        if (c->reject) return;
        (void)c0_emit(c, OP_POP, 0);
        if (c->reject) return;
        c0_e_and(c);
        if (c->reject) return;
        c0_patch(c, j);
    }
}

static void c0_e_and(C0Comp *c) {
    c0_e_cmp(c);
    while (c->reject == NULL && c0_at_punct(c, "&&")) {
        size_t j;
        (void)c0_bump(c);
        j = c0_emit(c, OP_JUMP_IF_FALSE_KEEP, 0);
        if (c->reject) return;
        (void)c0_emit(c, OP_POP, 0);
        if (c->reject) return;
        c0_e_cmp(c);
        if (c->reject) return;
        c0_patch(c, j);
    }
}

static void c0_e_cmp(C0Comp *c) {
    c0_e_shift(c);
    while (c->reject == NULL) {
        VmOp op;
        if (c0_at_punct(c, "==")) op = OP_CMP_EQ;
        else if (c0_at_punct(c, "!=")) op = OP_CMP_NE;
        else if (c0_at_punct(c, "<=")) op = OP_CMP_LE;
        else if (c0_at_punct(c, ">=")) op = OP_CMP_GE;
        else if (c0_at_punct(c, "<"))  op = OP_CMP_LT;
        else if (c0_at_punct(c, ">"))  op = OP_CMP_GT;
        else return;
        (void)c0_bump(c);
        c0_e_shift(c);
        if (c->reject) return;
        (void)c0_emit(c, op, 0);
    }
}

/* Shift precedence sits between the bitwise-or group and comparisons so the
 * profile-full parser can execute the SipHash/xxHash-style scalar kernels.
 * Default profile still rejects shifts via VM_REJ_PARSE (no `<<` tokens). */
static void c0_e_shift(C0Comp *c) {
    c0_e_bor(c);
    while (c->reject == NULL) {
        if (c0_at_punct(c, "<<")) {
            if (!c->allow_shift) { c0_fail(c, "VM_REJ_SHIFT"); return; }
            (void)c0_bump(c);
            c0_e_bor(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_SHL, 0);
        } else if (c0_at_punct(c, ">>")) {
            if (!c->allow_shift) { c0_fail(c, "VM_REJ_SHIFT"); return; }
            (void)c0_bump(c);
            c0_e_bor(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_SHR, 0);
        } else return;
    }
}

static void c0_e_bor(C0Comp *c) {
    c0_e_bxor(c);
    while (c->reject == NULL && c0_at_punct(c, "|")) {
        (void)c0_bump(c);
        c0_e_bxor(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_BIT_OR, 0);
    }
}

static void c0_e_bxor(C0Comp *c) {
    c0_e_band(c);
    while (c->reject == NULL && c0_at_punct(c, "^")) {
        (void)c0_bump(c);
        c0_e_band(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_BIT_XOR, 0);
    }
}

static void c0_e_band(C0Comp *c) {
    c0_e_add(c);
    while (c->reject == NULL && c0_at_punct(c, "&")) {
        (void)c0_bump(c);
        c0_e_add(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_BIT_AND, 0);
    }
}

static void c0_e_add(C0Comp *c) {
    c0_e_mul(c);
    while (c->reject == NULL) {
        if (c0_at_punct(c, "+")) {
            (void)c0_bump(c);
            c0_e_mul(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_ADD, 0);
        } else if (c0_at_punct(c, "-")) {
            (void)c0_bump(c);
            c0_e_mul(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_SUB, 0);
        } else return;
    }
}

static void c0_e_mul(C0Comp *c) {
    c0_e_unary(c);
    while (c->reject == NULL) {
        if (c0_at_punct(c, "*")) {
            (void)c0_bump(c);
            c0_e_unary(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_MUL, 0);
        } else if (c0_at_punct(c, "%")) {
            (void)c0_bump(c);
            c0_e_unary(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_MOD, 0);
        } else if (c0_at_punct(c, "/")) {
            if (!c->allow_div) {
                c0_fail(c, "VM_REJ_INT_DIVISION");
                return;
            }
            (void)c0_bump(c);
            c0_e_unary(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_DIV, 0);
        } else return;
    }
}

static void c0_e_unary(C0Comp *c) {
    if (c0_at_punct(c, "~")) {
        (void)c0_bump(c);
        c0_e_unary(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_BIT_NOT, 0);
        return;
    }
    if (c0_at_punct(c, "-")) {
        (void)c0_bump(c);
        c0_e_unary(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_NEG, 0);
        return;
    }
    if (c0_at_punct(c, "!")) {
        (void)c0_bump(c);
        c0_e_unary(c);
        if (c->reject) return;
        (void)c0_emit(c, OP_LOG_NOT, 0);
        return;
    }
    c0_e_primary(c);
}

/* std.fmt.parseInt(i64, text, 10): optional sign, >=1 digit, no overflow.
 * Zig accepts the full i64 range, so -9223372036854775808 must parse while
 * 9223372036854775808 must not (the Zig golden VM_REJ_LITERAL_RANGE depends
 * on exactly this asymmetry). Magnitudes are accumulated in u64 and only the
 * final negation touches the signed type, so no UB. */
static int c0_parse_i64(const char *t, size_t n, int64_t *out) {
    size_t i = 0;
    int neg = 0, digits = 0;
    uint64_t acc = 0;
    uint64_t max_mag;

    if (n == 0) return 0;
    if (t[0] == '-' || t[0] == '+') { neg = (t[0] == '-'); i = 1; }
    max_mag = neg ? ((uint64_t)INT64_MAX + 1u) : (uint64_t)INT64_MAX;
    for (; i < n; i++) {
        uint64_t d;
        if (t[i] < '0' || t[i] > '9') return 0;
        d = (uint64_t)(t[i] - '0');
        if (acc > (max_mag - d) / 10u) return 0;   /* acc*10+d would overflow */
        acc = acc * 10u + d;
        digits = 1;
    }
    if (!digits) return 0;
    if (neg) *out = (int64_t)(uint64_t)(0ull - acc);   /* 2^63 -> INT64_MIN */
    else     *out = (int64_t)acc;                      /* acc <= INT64_MAX  */
    return 1;
}

/* std.fmt.parseInt(u16, text, 10): digits only, no overflow. */
static int c0_parse_u16(const char *t, size_t n, uint16_t *out) {
    uint32_t acc = 0;
    if (n == 0) return 0;
    for (size_t i = 0; i < n; i++) {
        if (t[i] < '0' || t[i] > '9') return 0;
        acc = acc * 10u + (uint32_t)(t[i] - '0');
        if (acc > 65535u) return 0;
    }
    *out = (uint16_t)acc;
    return 1;
}

static void c0_e_primary(C0Comp *c) {
    C0Tok tk = c0_peek(c);

    if (tk.kind == C0_TK_STR) {
        (void)c0_bump(c);
        c0_fail(c, "VM_REJ_STRING_LITERAL");
        return;
    }
    if (tk.kind == C0_TK_NUMBER) {
        int64_t v;
        (void)c0_bump(c);
        if (!c0_parse_i64(tk.text, tk.len, &v)) {
            c0_fail(c, "VM_REJ_LITERAL_RANGE");
            return;
        }
        (void)c0_emit(c, OP_PUSH_CONST, v);
        return;
    }
    if (c0_accept_punct(c, "(")) {
        c0_expr(c);
        if (c->reject) return;
        if (!c0_accept_punct(c, ")")) c0_fail(c, "VM_REJ_PARSE");
        return;
    }
    if (tk.kind == C0_TK_IDENT) {
        (void)c0_bump(c);
        if (c0_tok_eq(&tk, "true"))  { (void)c0_emit(c, OP_PUSH_CONST, 1); return; }
        if (c0_tok_eq(&tk, "false")) { (void)c0_emit(c, OP_PUSH_CONST, 0); return; }

        if (c0_at_punct(c, "(")) {
            size_t argc = 0;
            (void)c0_bump(c);
            if (!c0_at_punct(c, ")")) {
                while (c->reject == NULL) {
                    c0_expr(c);
                    if (c->reject) return;
                    argc += 1;
                    if (!c0_accept_punct(c, ",")) break;
                }
                if (c->reject) return;
            }
            if (!c0_accept_punct(c, ")")) { c0_fail(c, "VM_REJ_PARSE"); return; }
            if (c0_tok_eq(&tk, "_lia_shl") || c0_tok_eq(&tk, "_lia_shr") ||
                c0_tok_eq(&tk, "_lia_ushr") || c0_tok_eq(&tk, "_lia_mod") ||
                c0_tok_eq(&tk, "@rem")) {
                VmOp op;
                if (argc != 2) { c0_fail(c, "VM_REJ_ARITY"); return; }
                op = c0_tok_eq(&tk, "_lia_shl") ? OP_SHL
                   : c0_tok_eq(&tk, "_lia_shr") ? OP_SHR
                   : c0_tok_eq(&tk, "_lia_ushr") ? OP_USHR : OP_MOD;
                (void)c0_emit(c, op, 0);
                return;
            }
            {
                int64_t fi = c0_find_fn(c, tk.text, tk.len);
                if (fi >= 0) {
                    if (c->fns[fi].nparams != argc) { c0_fail(c, "VM_REJ_ARITY"); return; }
                    (void)c0_emit(c, OP_CALL, fi);
                    return;
                }
            }
            c0_fail(c, "VM_REJ_UNKNOWN_CALL");
            return;
        }
        if (c0_at_punct(c, ".")) {
            C0Tok fld;
            (void)c0_bump(c);
            fld = c0_peek(c);
            if (fld.kind == C0_TK_IDENT && (c0_tok_eq(&fld, "length") || c0_tok_eq(&fld, "len"))) {
                int64_t li;
                (void)c0_bump(c);
                li = c0_find_local(c, tk.text, tk.len);
                if (li >= 0) {
                    if (c0_local_arr_n(c, li) == 0) { c0_fail(c, "VM_REJ_LENGTH_NOT_ARRAY"); return; }
                    (void)c0_emit(c, OP_ARR_LEN, li);
                    return;
                }
                c0_fail(c, "VM_REJ_UNBOUND_IDENT");
                return;
            }
            c0_fail(c, "VM_REJ_MEMBER_ACCESS");
            return;
        }
        if (c0_at_punct(c, "[")) {
            int64_t li = c0_find_local(c, tk.text, tk.len);
            if (li >= 0) {
                if (c0_local_arr_n(c, li) == 0) { c0_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
                (void)c0_bump(c);
                c0_expr(c);
                if (c->reject) return;
                if (!c0_accept_punct(c, "]")) { c0_fail(c, "VM_REJ_PARSE"); return; }
                (void)c0_emit(c, OP_LOAD_INDEX, li);
                return;
            }
            c0_fail(c, "VM_REJ_UNBOUND_IDENT");
            return;
        }
        {
            int64_t li = c0_find_local(c, tk.text, tk.len);
            if (li >= 0) {
                if (c0_local_arr_n(c, li) > 0) { c0_fail(c, "VM_REJ_ARRAY_AS_SCALAR"); return; }
                (void)c0_emit(c, OP_LOAD_LOCAL, li);
                return;
            }
        }
        c0_fail(c, "VM_REJ_UNBOUND_IDENT");
        return;
    }
    c0_fail(c, "VM_REJ_PARSE");
    (void)c0_bump(c);
}

static void c0_emit_arr_lit(C0Comp *c, int64_t li, uint16_t cap) {
    int64_t ei = 0;
    if (!c0_accept_punct(c, "[")) { c0_fail(c, "VM_REJ_PARSE"); return; }
    if (!c0_at_punct(c, "]")) {
        while (c->reject == NULL) {
            if (ei >= (int64_t)cap) { c0_fail(c, "VM_REJ_ARRAY_LIT_LEN"); return; }
            (void)c0_emit(c, OP_PUSH_CONST, ei);
            if (c->reject) return;
            c0_expr(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_STORE_INDEX, li);
            if (c->reject) return;
            ei += 1;
            if (!c0_accept_punct(c, ",")) break;
        }
        if (c->reject) return;
    }
    if (!c0_accept_punct(c, "]")) c0_fail(c, "VM_REJ_PARSE");
}

static void c0_assign(C0Comp *c) {
    C0Tok tk = c0_peek(c);
    if (tk.kind != C0_TK_IDENT) { c0_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
    (void)c0_bump(c);

    if (c0_at_punct(c, "[")) {
        int64_t li = c0_find_local(c, tk.text, tk.len);
        if (li >= 0) {
            if (c0_local_arr_n(c, li) == 0) { c0_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
            (void)c0_bump(c);
            c0_expr(c);
            if (c->reject) return;
            if (!c0_accept_punct(c, "]")) { c0_fail(c, "VM_REJ_PARSE"); return; }
            if (!c0_accept_punct(c, "=")) { c0_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
            c0_expr(c);
            if (c->reject) return;
            (void)c0_emit(c, OP_STORE_INDEX, li);
            return;
        }
        c0_fail(c, "VM_REJ_UNBOUND_IDENT");
        return;
    }
    if (c0_accept_punct(c, ":")) {
        C0Tok ntk;
        uint16_t nval;
        int64_t li;
        if (!c0_accept_punct(c, "[")) { c0_fail(c, "VM_REJ_PARSE"); return; }
        ntk = c0_peek(c);
        if (ntk.kind != C0_TK_NUMBER) { c0_fail(c, "VM_REJ_PARSE"); return; }
        (void)c0_bump(c);
        if (!c0_parse_u16(ntk.text, ntk.len, &nval)) { c0_fail(c, "VM_REJ_ARRAY_TOO_LARGE"); return; }
        if (nval < 1 || nval > LIN_VM_MAX_ARR_LEN) { c0_fail(c, "VM_REJ_ARRAY_TOO_LARGE"); return; }
        if (!c0_accept_punct(c, "]")) { c0_fail(c, "VM_REJ_PARSE"); return; }
        if (!(c0_at_ident(c, "int") || c0_at_ident(c, "i64"))) {
            c0_fail(c, "VM_REJ_ARRAY_ELEM_NOT_INT");
            return;
        }
        (void)c0_bump(c);
        li = c0_local_idx(c, tk.text, tk.len);
        if (c->reject) return;
        c0_mark_arr(c, li, nval);
        if (c0_accept_punct(c, "=")) c0_emit_arr_lit(c, li, nval);
        return;
    }
    if (!c0_accept_punct(c, "=")) { c0_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
    if (c0_at_punct(c, "[")) {
        int64_t li = c0_local_idx(c, tk.text, tk.len);
        uint16_t cap;
        if (c->reject) return;
        cap = c0_local_arr_n(c, li);
        if (cap == 0) { c0_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
        c0_emit_arr_lit(c, li, cap);
        return;
    }
    c0_expr(c);
    if (c->reject) return;
    {
        int64_t li = c0_local_idx(c, tk.text, tk.len);
        if (c->reject) return;
        if (c0_local_arr_n(c, li) > 0) { c0_fail(c, "VM_REJ_ARRAY_AS_SCALAR"); return; }
        (void)c0_emit(c, OP_STORE_LOCAL, li);
    }
}

static void c0_block(C0Comp *c) {
    if (!c0_accept_punct(c, "{")) { c0_fail(c, "VM_REJ_PARSE"); return; }
    while (!c0_at_punct(c, "}")) {
        if (c->reject != NULL) return;
        if (c0_peek(c).kind == C0_TK_EOF) { c0_fail(c, "VM_REJ_PARSE"); return; }
        c0_stmt(c);
    }
    (void)c0_bump(c);
}

static void c0_if_chain(C0Comp *c, size_t **ends, size_t *n_ends, size_t *cap_ends) {
    size_t jf, je;
    if (!c0_accept_punct(c, "(")) { c0_fail(c, "VM_REJ_PARSE"); return; }
    c0_expr(c);
    if (c->reject) return;
    if (!c0_accept_punct(c, ")")) { c0_fail(c, "VM_REJ_PARSE"); return; }
    jf = c0_emit(c, OP_JUMP_IF_FALSE, 0);
    if (c->reject) return;
    c0_block(c);
    if (c->reject != NULL) return;
    je = c0_emit(c, OP_JUMP, 0);
    if (c->reject) return;
    if (*n_ends == *cap_ends) {
        size_t nc = *cap_ends ? *cap_ends * 2 : 16;
        size_t *np = (size_t *)realloc(*ends, nc * sizeof(size_t));
        if (!np) { c0_fail(c, C0_OOM); return; }
        *ends = np;
        *cap_ends = nc;
    }
    (*ends)[*n_ends] = je;
    *n_ends += 1;
    c0_patch(c, jf);
    if (c0_accept_punct(c, ":")) {
        if (c0_at_punct(c, "(")) { c0_if_chain(c, ends, n_ends, cap_ends); return; }
        c0_block(c);
        return;
    }
    if (c0_at_ident(c, "else")) {
        (void)c0_bump(c);
        if (c0_at_ident(c, "if")) {
            (void)c0_bump(c);
            c0_if_chain(c, ends, n_ends, cap_ends);
            return;
        }
        c0_block(c);
        return;
    }
}

/* Find the closing ')' of a for header without compiling its increment yet.
 * Nested calls and parenthesized expressions are balanced independently. */
static size_t c0_for_close(const C0Comp *c, size_t start) {
    size_t depth = 0;
    for (size_t i = start; i < c->ntoks; i++) {
        const C0Tok *tk = &c->toks[i];
        if (tk->kind != C0_TK_PUNCT) continue;
        if (c0_tok_eq(tk, "(")) {
            depth += 1;
        } else if (c0_tok_eq(tk, ")")) {
            if (depth == 0) return i;
            depth -= 1;
        }
    }
    return SIZE_MAX;
}

static void c0_stmt(C0Comp *c) {
    if (c0_accept_punct(c, ";")) return;
    if (c0_at_punct(c, "^")) {
        (void)c0_bump(c);
        c0_expr(c);
        if (c->reject) return;
        (void)c0_accept_punct(c, ";");
        (void)c0_emit(c, OP_RET, 0);
        return;
    }
    if (c0_at_ident(c, "return")) {
        (void)c0_bump(c);
        c0_expr(c);
        if (c->reject) return;
        (void)c0_accept_punct(c, ";");
        (void)c0_emit(c, OP_RET, 0);
        return;
    }
    if (c0_at_punct(c, "?") || c0_at_ident(c, "if")) {
        size_t *ends = NULL;
        size_t n_ends = 0, cap_ends = 0;
        (void)c0_bump(c);
        c0_if_chain(c, &ends, &n_ends, &cap_ends);
        if (c->reject != NULL) { free(ends); return; }
        for (size_t i = 0; i < n_ends; i++) c0_patch(c, ends[i]);
        free(ends);
        (void)c0_accept_punct(c, ";");
        return;
    }
    if (c0_at_ident(c, "while")) {
        int64_t top;
        size_t jf;
        (void)c0_bump(c);
        top = c0_here(c);
        if (!c0_accept_punct(c, "(")) { c0_fail(c, "VM_REJ_PARSE"); return; }
        c0_expr(c);
        if (c->reject) return;
        if (!c0_accept_punct(c, ")")) { c0_fail(c, "VM_REJ_PARSE"); return; }
        jf = c0_emit(c, OP_JUMP_IF_FALSE, 0);
        if (c->reject) return;
        c0_block(c);
        if (c->reject != NULL) return;
        (void)c0_emit(c, OP_JUMP, top);
        if (c->reject) return;
        c0_patch(c, jf);
        (void)c0_accept_punct(c, ";");
        return;
    }
    if (c0_at_ident(c, "for")) {
        size_t step_pos;
        size_t close_pos;
        size_t body_pos;
        size_t cond_pos;
        size_t jf;
        size_t body_end;

        (void)c0_bump(c);
        if (!c0_accept_punct(c, "(")) { c0_fail(c, "VM_REJ_PARSE"); return; }

        /* init: assignment or an empty clause */
        if (!c0_at_punct(c, ";")) c0_assign(c);
        if (c->reject) return;
        if (!c0_accept_punct(c, ";")) { c0_fail(c, "VM_REJ_PARSE"); return; }

        /* condition: an empty condition is the canonical true loop */
        cond_pos = c->ncode;
        if (c0_at_punct(c, ";")) {
            (void)c0_emit(c, OP_PUSH_CONST, 1);
        } else {
            c0_expr(c);
            if (c->reject) return;
        }
        if (!c0_accept_punct(c, ";")) { c0_fail(c, "VM_REJ_PARSE"); return; }

        /* The increment is lexically before the body but executes after it.
         * Save its token position, skip to the body, then compile it after
         * the body has been emitted. */
        step_pos = c->pos;
        close_pos = c0_for_close(c, step_pos);
        if (close_pos == SIZE_MAX) { c0_fail(c, "VM_REJ_PARSE"); return; }
        body_pos = close_pos + 1;
        c->pos = body_pos;

        jf = c0_emit(c, OP_JUMP_IF_FALSE, 0);
        if (c->reject) return;
        c0_block(c);
        if (c->reject) return;
        body_end = c->pos;

        c->pos = step_pos;
        if (c->pos != close_pos) {
            c0_assign(c);
            if (c->reject) return;
            if (c->pos != close_pos) { c0_fail(c, "VM_REJ_PARSE"); return; }
        }
        c->pos = body_end;
        (void)c0_emit(c, OP_JUMP, (int64_t)cond_pos);
        if (c->reject) return;
        c0_patch(c, jf);
        (void)c0_accept_punct(c, ";");
        return;
    }
    if (c0_at_punct(c, "#")) { c0_fail(c, "VM_REJ_FOR_LOOP"); return; }
    c0_assign(c);
    if (c->reject != NULL) return;
    if (!c0_accept_punct(c, ";")) c0_fail(c, "VM_REJ_PARSE");
}

/* =====================================================================
 * vmArrLenOf / vmSigEligible (lin.zig:6262, 6275)
 * ===================================================================== */

static int c0_arr_len_of(const char *ty, uint16_t *out) {
    const char *t = ty;
    size_t n = strlen(ty);
    size_t close, num_at, num_len, rest_at, rest_len;
    uint16_t v;
    c0_trim(&t, &n);
    if (n < 6 || t[0] != '[') return 0;
    close = c0_index_char(t, n, ']');
    if (close == SIZE_MAX) return 0;
    num_at = 1;
    num_len = close - 1;
    {
        const char *p = t + num_at;
        size_t l = num_len;
        while (l > 0 && (p[0] == ' ' || p[0] == '\t')) { p++; l--; }
        while (l > 0 && (p[l - 1] == ' ' || p[l - 1] == '\t')) { l--; }
        num_at = (size_t)(p - t);
        num_len = l;
    }
    if (!c0_parse_u16(t + num_at, num_len, &v)) return 0;
    rest_at = close + 1;
    rest_len = n - rest_at;
    {
        const char *p = t + rest_at;
        size_t l = rest_len;
        while (l > 0 && (p[0] == ' ' || p[0] == '\t')) { p++; l--; }
        while (l > 0 && (p[l - 1] == ' ' || p[l - 1] == '\t')) { l--; }
        rest_len = l;
        if (!((rest_len == 3 && memcmp(p, "int", 3) == 0) ||
              (rest_len == 3 && memcmp(p, "i64", 3) == 0)))
            return 0;
    }
    *out = v;
    return 1;
}

static const char *c0_sig_eligible(const C0FnInfo *info) {
    size_t rl = strlen(info->return_type);
    if (!((rl == 3 && memcmp(info->return_type, "int", 3) == 0) ||
          (rl == 3 && memcmp(info->return_type, "i64", 3) == 0)))
        return "VM_REJ_RETURN_NOT_INT";
    for (size_t i = 0; i < info->nparams; i++) {
        const char *tn = info->params[i].type_name;
        size_t l = strlen(tn);
        uint16_t n;
        if ((l == 3 && memcmp(tn, "int", 3) == 0) || (l == 3 && memcmp(tn, "i64", 3) == 0))
            continue;
        if (c0_arr_len_of(tn, &n)) {
            if (n < 1 || n > LIN_VM_MAX_ARR_LEN) return "VM_REJ_ARRAY_TOO_LARGE";
            continue;
        }
        return "VM_REJ_PARAM_NOT_INT";
    }
    return NULL;
}

/* =====================================================================
 * vmResolveDeps (lin.zig:6284)
 * ===================================================================== */

static void c0_resolve_deps(VmFn *fns, size_t nfns) {
    int changed = 1;
    while (changed) {
        changed = 0;
        for (size_t i = 0; i < nfns; i++) {
            VmFn *f = &fns[i];
            if (!f->ok) continue;
            for (size_t k = 0; k < f->code_len; k++) {
                size_t ti;
                if (f->code[k].op != OP_CALL) continue;
                ti = (size_t)f->code[k].a;
                if (ti >= nfns || !fns[ti].ok) {
                    f->ok = 0;
                    f->reject = "VM_REJ_DEP_REJECTED";
                    changed = 1;
                    break;
                }
            }
        }
    }
}

/* The info list and its param arrays are malloc'd (they are only needed
 * during the build), so they are released here — the sanitizer sweep in
 * test/verify_c0.sh (SAN=1) fails the gate on any leak. */
static void c0_free_fn_infos(const C0FnInfo *infos, size_t n) {
    if (!infos) return;
    for (size_t i = 0; i < n; i++) free((void *)infos[i].params);
    free((void *)infos);
}

/* =====================================================================
 * vmBuild (lin.zig:6296)
 * ===================================================================== */

static VmModule *c0_build_impl(C0Arena *a, const char *src, size_t len,
                               int allow_div, int allow_shift) {
    size_t n_infos = 0;
    const C0FnInfo *infos;
    VmModule *mod;
    VmFn *fns;

    infos = c0_parse_fn_infos(a, src, len, &n_infos);
    if (!infos) return NULL;

    mod = (VmModule *)c0_arena_alloc(a, sizeof(VmModule));
    fns = (VmFn *)c0_arena_alloc(a, (n_infos ? n_infos : 1) * sizeof(VmFn));
    if (!mod || !fns) { c0_free_fn_infos(infos, n_infos); return NULL; }
    mod->fns = fns;
    mod->fns_len = n_infos;

    for (size_t i = 0; i < n_infos; i++) {
        const char *rej;
        fns[i].name = infos[i].name;
        fns[i].nparams = infos[i].nparams;
        fns[i].nlocals = 0;
        fns[i].code = NULL;
        fns[i].code_len = 0;
        fns[i].sig_ok = 0;
        fns[i].ok = 0;
        fns[i].reject = "";
        fns[i].arr_n = NULL;
        fns[i].arr_n_len = 0;
        rej = c0_sig_eligible(&infos[i]);
        if (rej) fns[i].reject = rej;
        else fns[i].sig_ok = 1;
    }

    for (size_t i = 0; i < n_infos; i++) {
        C0Comp comp;
        size_t ntoks = 0;
        VmIns *code_copy;
        uint16_t *arr_copy;
        int broke = 0;

        if (!fns[i].sig_ok) continue;

        memset(&comp, 0, sizeof(comp));
        comp.al = a;
        comp.toks = c0_tokenize(infos[i].body, infos[i].body_len, &ntoks);
        if (!comp.toks) { c0_free_fn_infos(infos, n_infos); return NULL; }
        comp.ntoks = ntoks;
        comp.pos = 0;
        comp.fns = fns;
        comp.nfns = n_infos;
        comp.reject = NULL;
        comp.allow_div = allow_div;
        comp.allow_shift = allow_shift;

        for (size_t p = 0; p < infos[i].nparams; p++) {
            int64_t li = c0_local_idx(&comp, infos[i].params[p].name,
                                      strlen(infos[i].params[p].name));
            uint16_t n;
            if (comp.reject) break;
            if (c0_arr_len_of(infos[i].params[p].type_name, &n)) {
                if (n < 1 || n > LIN_VM_MAX_ARR_LEN) {
                    fns[i].reject = "VM_REJ_ARRAY_TOO_LARGE";
                    fns[i].sig_ok = 0;
                    broke = 1;
                    break;
                }
                c0_mark_arr(&comp, li, n);
            }
        }
        if (broke || !fns[i].sig_ok) {
            free(comp.code); free(comp.locals); free(comp.arr_n); free(comp.toks);
            continue;
        }

        while (c0_peek(&comp).kind != C0_TK_EOF && comp.reject == NULL) c0_stmt(&comp);

        if (comp.reject) {
            fns[i].reject = (comp.reject == C0_OOM) ? "C0_REJ_OUT_OF_MEMORY" : comp.reject;
            free(comp.code); free(comp.locals); free(comp.arr_n); free(comp.toks);
            continue;
        }
        (void)c0_emit(&comp, OP_PUSH_CONST, 0);
        (void)c0_emit(&comp, OP_RET, 0);
        if (comp.reject) {
            fns[i].reject = "C0_REJ_OUT_OF_MEMORY";
            free(comp.code); free(comp.locals); free(comp.arr_n); free(comp.toks);
            continue;
        }

        code_copy = (VmIns *)c0_arena_alloc(a, comp.ncode * sizeof(VmIns));
        arr_copy = (uint16_t *)c0_arena_alloc(a, (comp.narrn ? comp.narrn : 1) * sizeof(uint16_t));
        if (!code_copy || !arr_copy) {
            free(comp.code); free(comp.locals); free(comp.arr_n); free(comp.toks);
            c0_free_fn_infos(infos, n_infos);
            return NULL;
        }
        memcpy(code_copy, comp.code, comp.ncode * sizeof(VmIns));
        if (comp.narrn) memcpy(arr_copy, comp.arr_n, comp.narrn * sizeof(uint16_t));

        fns[i].code = code_copy;
        fns[i].code_len = comp.ncode;
        fns[i].nlocals = comp.nlocals;
        fns[i].arr_n = arr_copy;
        fns[i].arr_n_len = comp.narrn;
        fns[i].ok = 1;

        free(comp.code); free(comp.locals); free(comp.arr_n); free(comp.toks);
    }

    c0_resolve_deps(fns, n_infos);
    c0_free_fn_infos(infos, n_infos);
    return mod;
}

VmModule *c0_build(C0Arena *a, const char *src, size_t len) {
    return c0_build_impl(a, src, len, 1, 0);
}

/* Experimental "profile full": used only by the `vmfull` CLI command. */
VmModule *c0_build_full(C0Arena *a, const char *src, size_t len) {
    return c0_build_impl(a, src, len, 1, 1);
}

/* =====================================================================
 * LINBC1 image encoder (docs/LINBC1_FORMAT.rulel §2/§3, profile 1)
 *
 * Canonical order: string pool = function order; no regions, no ABIs (the
 * C0 host has no host intrinsics yet — V2+). Self-hash domain "linbc1:img:"
 * over everything before the hash, exactly as the loader recomputes it.
 * ===================================================================== */

typedef struct {
    uint8_t *p;
    size_t len, cap;
} C0Out;

static int c0_out_need(C0Out *o, size_t extra) {
    if (o->len + extra <= o->cap) return 1;
    {
        size_t nc = o->cap ? o->cap : 256;
        uint8_t *np;
        while (nc < o->len + extra) nc *= 2;
        np = (uint8_t *)realloc(o->p, nc);
        if (!np) return 0;
        o->p = np;
        o->cap = nc;
    }
    return 1;
}

static int c0_put_u8(C0Out *o, uint8_t v) {
    if (!c0_out_need(o, 1)) return 0;
    o->p[o->len++] = v;
    return 1;
}
static int c0_put_u16(C0Out *o, uint16_t v) {
    if (!c0_out_need(o, 2)) return 0;
    o->p[o->len++] = (uint8_t)(v & 0xff);
    o->p[o->len++] = (uint8_t)((v >> 8) & 0xff);
    return 1;
}
static int c0_put_u32(C0Out *o, uint32_t v) {
    if (!c0_out_need(o, 4)) return 0;
    for (int i = 0; i < 4; i++) o->p[o->len++] = (uint8_t)((v >> (8 * i)) & 0xff);
    return 1;
}
static int c0_put_i64(C0Out *o, int64_t v) {
    uint64_t u = (uint64_t)v;
    if (!c0_out_need(o, 8)) return 0;
    for (int i = 0; i < 8; i++) o->p[o->len++] = (uint8_t)((u >> (8 * i)) & 0xff);
    return 1;
}
static int c0_put_bytes(C0Out *o, const void *b, size_t n) {
    if (!c0_out_need(o, n)) return 0;
    if (n) memcpy(o->p + o->len, b, n);
    o->len += n;
    return 1;
}

uint8_t *c0_image_encode(C0Arena *a, const VmModule *mod, size_t *out_len, const char **err) {
    C0Out o;
    LinSha256 h;
    uint8_t digest[32];
    static const uint8_t DOM[] = "linbc1:img:";

    (void)a;   /* the encoder owns its output buffer; arena kept for symmetry */
    memset(&o, 0, sizeof(o));
    *out_len = 0;
    *err = NULL;

    /* every function must be executable — a partial image is never written */
    for (size_t i = 0; i < mod->fns_len; i++) {
        if (!mod->fns[i].ok) { *err = "C0_REJ_MODULE_NOT_PURE"; return NULL; }
        if (mod->fns[i].code_len == 0) { *err = "C0_REJ_EMPTY_FN"; return NULL; }
        if (mod->fns[i].nparams > 255 || mod->fns[i].nlocals > LIN_VM_MAX_LOCALS) {
            *err = "C0_REJ_FN_LIMITS";
            return NULL;
        }
        if (mod->fns[i].nlocals < mod->fns[i].nparams) { *err = "C0_REJ_FN_LIMITS"; return NULL; }
    }
    if (mod->fns_len > LIN_BC1_MAX_FNS) { *err = "C0_REJ_TOO_MANY_FNS"; return NULL; }

    /* header */
    if (!c0_put_bytes(&o, "LINBC1", 6)) goto oom;
    if (!c0_put_u8(&o, 1)) goto oom;                       /* format_version */
    if (!c0_put_u8(&o, 1)) goto oom;                       /* profile LINVM-1 */
    if (!c0_put_u8(&o, 0)) goto oom;                       /* flags */
    if (!c0_put_u32(&o, (uint32_t)mod->fns_len)) goto oom; /* n_strings */
    if (!c0_put_u32(&o, (uint32_t)mod->fns_len)) goto oom; /* n_fns */
    if (!c0_put_u32(&o, 0)) goto oom;                      /* n_regions */
    if (!c0_put_u32(&o, 0)) goto oom;                      /* n_abis */

    /* string pool: one entry per function name, in section order */
    for (size_t i = 0; i < mod->fns_len; i++) {
        size_t nl = strlen(mod->fns[i].name);
        if (!c0_put_u32(&o, (uint32_t)nl)) goto oom;
        if (!c0_put_bytes(&o, mod->fns[i].name, nl)) goto oom;
    }

    /* functions */
    for (size_t i = 0; i < mod->fns_len; i++) {
        const VmFn *f = &mod->fns[i];
        uint8_t n_arrs = 0;
        for (size_t li = 0; li < f->arr_n_len; li++) if (f->arr_n[li] > 0) n_arrs++;
        if (n_arrs > 8) { *err = "C0_REJ_TOO_MANY_ARRAYS"; free(o.p); return NULL; }

        if (!c0_put_u32(&o, (uint32_t)i)) goto oom;                 /* name_idx */
        if (!c0_put_u8(&o, (uint8_t)f->nparams)) goto oom;
        if (!c0_put_u8(&o, (uint8_t)f->nlocals)) goto oom;
        if (!c0_put_u8(&o, n_arrs)) goto oom;
        if (!c0_put_u32(&o, (uint32_t)f->code_len)) goto oom;
        for (size_t li = 0; li < f->arr_n_len; li++) {
            if (f->arr_n[li] == 0) continue;
            if (li > 255) { *err = "C0_REJ_FN_LIMITS"; free(o.p); return NULL; }
            if (!c0_put_u8(&o, (uint8_t)li)) goto oom;
            if (!c0_put_u16(&o, f->arr_n[li])) goto oom;
        }
        for (size_t pc = 0; pc < f->code_len; pc++) {
            /* encoding XVER imutável: [op u8][operando i64 LE] */
            if (!c0_put_u8(&o, (uint8_t)f->code[pc].op)) goto oom;
            if (!c0_put_i64(&o, f->code[pc].a)) goto oom;
        }
    }

    /* self hash */
    lin_sha256_init(&h);
    lin_sha256_update(&h, DOM, sizeof(DOM) - 1);
    lin_sha256_update(&h, o.p, o.len);
    lin_sha256_final(&h, digest);
    if (!c0_put_bytes(&o, digest, 32)) goto oom;

    *out_len = o.len;
    return o.p;

oom:
    free(o.p);
    *err = "C0_REJ_OUT_OF_MEMORY";
    return NULL;
}
