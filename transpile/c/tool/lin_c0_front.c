/*
 * lin_c0_front.c — fonte `.lin` -> bytecode LinVM canônico, em C11 puro.
 *
 * Port fiel de `vmTokenize` + `parse_fn_type_infos` + `VmComp` + `vmBuild` +
 * `vmResolveDeps` (compiler/lin.zig). Nenhuma decisão semântica é nova: onde o
 * Zig rejeita, rejeita-se com o MESMO código (`VM_REJ_*`); onde o Zig emite,
 * emite-se a MESMA instrução. É isso que faz de `lin_c0` um substituto de
 * `lin vm` e não um segundo dialeto.
 *
 * Zero alocação (arenas do chamador), zero dependência de Zig, fail-closed em
 * todo limite (`C0_LIMIT_*`).
 */
#include "lin_c0_front.h"
#include "../lin_c/lin_sha256.h"
#include "../lin_c/lin_linbc1.h"
#include <string.h>

/* ===================== primitivas de texto ================================= */

static int c0_is_ws(uint8_t c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
static int c0_is_ident_start(uint8_t c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c == '$';
}
static int c0_is_ident_part(uint8_t c) { return c0_is_ident_start(c) || (c >= '0' && c <= '9'); }

static LinStr c0_span(const uint8_t *p, size_t len) { LinStr s; s.p = p; s.len = len; return s; }
static int c0_eq(LinStr a, const char *b) { return lin_str_eq_cstr(a, b); }
static int c0_eq_str(LinStr a, LinStr b) { return a.len == b.len && (a.len == 0 || memcmp(a.p, b.p, a.len) == 0); }

/* trim " \t\r\n" — o mesmo conjunto de `std.mem.trim(u8, _, " \t\r\n")`. */
static LinStr c0_trim(LinStr a) {
    while (a.len && c0_is_ws(*a.p)) { a.p++; a.len--; }
    while (a.len && c0_is_ws(a.p[a.len - 1])) a.len--;
    return a;
}
static long c0_index_of(LinStr a, uint8_t c) {
    size_t i;
    for (i = 0; i < a.len; i++) if (a.p[i] == c) return (long)i;
    return -1;
}
static long c0_index_of_str(LinStr a, const char *n) {
    size_t nl = strlen(n), i;
    if (nl == 0 || a.len < nl) return -1;
    for (i = 0; i + nl <= a.len; i++) if (memcmp(a.p + i, n, nl) == 0) return (long)i;
    return -1;
}

/* parseInt(i64, decimal): apenas dígitos; estouro = falha. O Stage0 responde
 * com VM_REJ_LITERAL_RANGE nesse caso — não há wrap no caminho do VM. */
static int c0_parse_i64(LinStr t, int64_t *out) {
    uint64_t v = 0;
    size_t i;
    if (t.len == 0) return 0;
    for (i = 0; i < t.len; i++) {
        uint8_t c = t.p[i];
        if (c < '0' || c > '9') return 0;
        v = v * 10ull + (uint64_t)(c - '0');
        if (v > (uint64_t)INT64_MAX) return 0;
    }
    *out = (int64_t)v;
    return 1;
}
/* parseInt(u16, decimal) — mesmo contrato, faixa u16. */
static int c0_parse_u16(LinStr t, uint16_t *out) {
    uint32_t v = 0;
    size_t i;
    if (t.len == 0) return 0;
    for (i = 0; i < t.len; i++) {
        uint8_t c = t.p[i];
        if (c < '0' || c > '9') return 0;
        v = v * 10u + (uint32_t)(c - '0');
        if (v > 0xFFFFu) return 0;
    }
    *out = (uint16_t)v;
    return 1;
}

/* ===================== tokenizador (port de vmTokenize) =================== */

size_t c0_tokenize(const uint8_t *src, size_t len, C0Tok *out, size_t cap) {
    size_t i = 0, n = 0;
#define C0_PUSH(k, p, l) do {                                        \
        if (n >= cap) return (size_t)-1;                             \
        out[n].kind = (k); out[n].text = c0_span((p), (l)); n++;     \
    } while (0)
    while (i < len) {
        uint8_t c = src[i];
        if (c0_is_ws(c)) { i++; continue; }
        if (c == '/' && i + 1 < len && src[i + 1] == '/') {
            while (i < len && src[i] != '\n') i++;
            continue;
        }
        if (c == '"') {
            size_t st = i;
            i++;
            while (i < len && src[i] != '"') {
                if (src[i] == '\\' && i + 1 < len) i++;
                i++;
            }
            if (i < len) i++;
            C0_PUSH(C0_T_STR, src + st, i - st);
            continue;
        }
        if (c >= '0' && c <= '9') {
            size_t st = i;
            while (i < len && src[i] >= '0' && src[i] <= '9') i++;
            C0_PUSH(C0_T_NUMBER, src + st, i - st);
            continue;
        }
        if (c0_is_ident_start(c)) {
            size_t st = i;
            while (i < len && c0_is_ident_part(src[i])) i++;
            C0_PUSH(C0_T_IDENT, src + st, i - st);
            continue;
        }
        if (i + 1 < len) {
            uint8_t a = src[i], b = src[i + 1];
            if ((a == '=' && b == '=') || (a == '!' && b == '=') || (a == '<' && b == '=') ||
                (a == '>' && b == '=') || (a == '&' && b == '&') || (a == '|' && b == '|') ||
                (a == '-' && b == '>')) {
                C0_PUSH(C0_T_PUNCT, src + i, 2);
                i += 2;
                continue;
            }
        }
        C0_PUSH(C0_T_PUNCT, src + i, 1);
        i++;
    }
    C0_PUSH(C0_T_EOF, src + len, 0);
    return n;
#undef C0_PUSH
}

/* ================ varredura de assinaturas (parse_fn_type_infos) ========== */

/* `pos` aponta para a aspas de abertura. Sem tratamento de barra invertida:
 * fiel a parse_fn_type_infos, que deliberadamente difere do tokenizador. */
static size_t c0_skip_quoted(const uint8_t *s, size_t len, size_t pos) {
    pos++;
    while (pos < len && s[pos] != '"') pos++;
    if (pos < len) pos++;
    return pos;
}
static size_t c0_scan_ident(const uint8_t *s, size_t len, size_t pos) {
    while (pos < len && ((s[pos] >= 'a' && s[pos] <= 'z') || (s[pos] >= 'A' && s[pos] <= 'Z') ||
                         (s[pos] >= '0' && s[pos] <= '9') || s[pos] == '_' || s[pos] == '$')) pos++;
    return pos;
}

void c0_scan_fns(const uint8_t *src, size_t len, C0SigList *out) {
    size_t i = 0;
    out->n_fns = 0;
    out->truncated = 0;
    while (i < len) {
        size_t pos, name_start, open_p, close_p, hdr_end;
        LinStr raw, hdr_extra, ret;
        C0FnSig *sig;
        long depth;
        if (!(src[i] == '!' && (i + 1 >= len || src[i + 1] != '='))) { i++; continue; }
        pos = i + 1;
        while (pos < len && c0_is_ws(src[pos])) pos++;
        name_start = pos;
        pos = c0_scan_ident(src, len, pos);
        if (pos - name_start == 0 || pos >= len || src[pos] != '(') { i++; continue; }
        if (out->n_fns >= C0_MAX_FNS) { out->truncated = 1; return; }
        sig = &out->fns[out->n_fns];
        memset(sig, 0, sizeof(*sig));
        sig->name = c0_span(src + name_start, pos - name_start);

        /* parênteses balanceados (com skip de strings) => raw_params */
        open_p = pos;
        depth = 1;
        pos++;
        while (pos < len && depth > 0) {
            if (src[pos] == '"') { pos = c0_skip_quoted(src, len, pos); continue; }
            if (src[pos] == '(') depth++;
            else if (src[pos] == ')') depth--;
            pos++;
        }
        close_p = pos - 1;
        raw = (close_p > open_p + 1) ? c0_span(src + open_p + 1, close_p - (open_p + 1))
                                     : c0_span(src + open_p + 1, 0);
        {
            size_t at = 0;
            while (at <= raw.len) {
                long comma = -1;
                LinStr piece, trimmed;
                size_t j;
                for (j = at; j < raw.len; j++) if (raw.p[j] == ',') { comma = (long)j; break; }
                if (comma < 0) { piece = c0_span(raw.p + at, raw.len - at); at = raw.len + 1; }
                else { piece = c0_span(raw.p + at, (size_t)comma - at); at = (size_t)comma + 1; }
                trimmed = c0_trim(piece);
                if (trimmed.len == 0) continue;
                if (sig->nparams >= C0_MAX_PARAMS) { out->truncated = 1; return; }
                {
                    long colon = c0_index_of(trimmed, ':');
                    size_t slot = sig->nparams;
                    if (colon >= 0) {
                        sig->p_name[slot] = c0_trim(c0_span(trimmed.p, (size_t)colon));
                        sig->p_type[slot] = c0_trim(c0_span(trimmed.p + colon + 1,
                                                            trimmed.len - (size_t)colon - 1));
                    } else {
                        sig->p_name[slot] = trimmed;
                        sig->p_type[slot] = c0_span((const uint8_t *)"any", 3);
                    }
                    sig->nparams = slot + 1;
                }
            }
        }

        /* até '{' fica o extra do cabeçalho, de onde sai o tipo de retorno */
        hdr_end = pos;
        while (hdr_end < len && src[hdr_end] != '{') hdr_end++;
        hdr_extra = c0_span(src + pos, hdr_end - pos);
        ret = c0_span((const uint8_t *)"any", 3);
        {
            long arrow = c0_index_of_str(hdr_extra, "->");
            long colon = c0_index_of(hdr_extra, ':');
            if (arrow >= 0) ret = c0_trim(c0_span(hdr_extra.p + arrow + 2,
                                                  hdr_extra.len - (size_t)arrow - 2));
            else if (colon >= 0) ret = c0_trim(c0_span(hdr_extra.p + colon + 1,
                                                        hdr_extra.len - (size_t)colon - 1));
        }
        sig->ret = ret;
        if (!(hdr_end < len && src[hdr_end] == '{')) { i++; continue; }
        {
            size_t brace_open = hdr_end, bpos = brace_open + 1;
            long bdepth = 1;
            while (bpos < len && bdepth > 0) {
                if (src[bpos] == '"') { bpos = c0_skip_quoted(src, len, bpos); continue; }
                if (src[bpos] == '{') bdepth++;
                else if (src[bpos] == '}') bdepth--;
                bpos++;
            }
            sig->body = c0_span(src + brace_open + 1, (bpos - 1) - (brace_open + 1));
            out->n_fns++;
            i = bpos;
        }
    }
}

/* ===================== elegibilidade de assinatura ========================= */

int c0_arr_len_of(LinStr ty, uint16_t *n_out) {
    LinStr t = c0_trim(ty), num, rest;
    long close;
    uint16_t n = 0;
    if (t.len < 6 || t.p[0] != '[') return 0;
    close = c0_index_of(t, ']');
    if (close < 0) return 0;
    num = c0_trim(c0_span(t.p + 1, (size_t)close - 1));
    if (!c0_parse_u16(num, &n)) return 0;
    rest = c0_trim(c0_span(t.p + close + 1, t.len - (size_t)close - 1));
    if (!(c0_eq(rest, "int") || c0_eq(rest, "i64"))) return 0;
    *n_out = n;
    return 1;
}

const char *c0_sig_eligible(const C0FnSig *sig) {
    size_t i;
    if (!(c0_eq(sig->ret, "int") || c0_eq(sig->ret, "i64"))) return "VM_REJ_RETURN_NOT_INT";
    for (i = 0; i < sig->nparams; i++) {
        uint16_t n = 0;
        if (c0_eq(sig->p_type[i], "int") || c0_eq(sig->p_type[i], "i64")) continue;
        if (c0_arr_len_of(sig->p_type[i], &n)) {
            if (n < 1 || n > LIN_VM_MAX_ARR_LEN) return "VM_REJ_ARRAY_TOO_LARGE";
            continue;
        }
        return "VM_REJ_PARAM_NOT_INT";
    }
    return 0;
}

/* ===================== VmComp: corpo -> bytecode ========================== */

typedef struct {
    C0Module *m;
    const C0Tok *toks;
    size_t ntoks, pos;
    size_t fidx, istart, ilen, icap;
    LinStr locals[LIN_VM_MAX_LOCALS];
    size_t nlocals;
    const char *reject;
    int aborted;                    /* limite global de instruções           */
    int too_many_locals;            /* VM_REJ_TOO_MANY_LOCALS já sinalizado  */
} Comp;

static void c_expr(Comp *c);
static void c_block(Comp *c);
static void c_stmt(Comp *c);
static void c_e_bor(Comp *c);
static void c_e_primary(Comp *c);
static void c_e_unary(Comp *c);
static void c_e_mul(Comp *c);
static void c_e_add(Comp *c);
static void c_e_band(Comp *c);
static void c_e_bxor(Comp *c);
static void c_e_cmp(Comp *c);
static void c_e_and(Comp *c);
static void c_e_or(Comp *c);

static C0Tok c_peek(Comp *c) { return c->toks[c->pos]; }
static C0Tok c_bump(Comp *c) { C0Tok t = c->toks[c->pos]; if (t.kind != C0_T_EOF) c->pos++; return t; }
static int c_at_punct(Comp *c, const char *t) {
    C0Tok k = c_peek(c);
    return k.kind == C0_T_PUNCT && c0_eq(k.text, t);
}
static int c_at_ident(Comp *c, const char *t) {
    C0Tok k = c_peek(c);
    return k.kind == C0_T_IDENT && c0_eq(k.text, t);
}
static int c_accept_punct(Comp *c, const char *t) { if (c_at_punct(c, t)) { (void)c_bump(c); return 1; } return 0; }
static void c_fail(Comp *c, const char *code) { if (c->reject == 0) c->reject = code; }
static size_t c_here(Comp *c) { return c->ilen; }
static VmIns *c_code(Comp *c) { return c->m->ins + c->istart; }

static void c_emit(Comp *c, VmOp op, int64_t a) {
    if (c->ilen >= c->icap) {
        c->m->fatal = C0_LIMIT_INS;
        c->aborted = 1;
        c_fail(c, C0_LIMIT_INS);
        return;
    }
    c_code(c)[c->ilen].op = op;
    c_code(c)[c->ilen].a = a;
    c->ilen++;
}
static void c_patch(Comp *c, size_t at) { c_code(c)[at].a = (int64_t)c_here(c); }

static int c_find_local(Comp *c, LinStr name, int64_t *out) {
    size_t i;
    for (i = 0; i < c->nlocals; i++)
        if (c0_eq_str(c->locals[i], name)) { *out = (int64_t)i; return 1; }
    return 0;
}
static int64_t c_local_idx(Comp *c, LinStr name) {
    int64_t v = 0;
    if (c_find_local(c, name, &v)) return v;
    if (c->nlocals >= LIN_VM_MAX_LOCALS) { c_fail(c, "VM_REJ_TOO_MANY_LOCALS"); c->too_many_locals = 1; return 0; }
    c->locals[c->nlocals] = name;
    c->m->arrn[c->fidx][c->nlocals] = 0;
    c->nlocals++;
    return (int64_t)(c->nlocals - 1);
}
static uint16_t c_local_arr_n(Comp *c, int64_t li) {
    if (li < 0 || (size_t)li >= c->nlocals) return 0;
    return c->m->arrn[c->fidx][li];
}
static void c_mark_arr(Comp *c, int64_t li, uint16_t n) {
    if (li >= 0 && (size_t)li < c->nlocals) c->m->arrn[c->fidx][li] = n;
}
/* findFn do Zig: percorre todas as assinaturas, aceitando só as sig_ok. */
static int c_find_fn(Comp *c, LinStr name) {
    size_t i;
    for (i = 0; i < c->m->total_fns; i++)
        if (c->m->fns[i].sig_ok && c0_eq_str(c0_span((const uint8_t *)c->m->names[i],
                                                      strlen(c->m->names[i])), name))
            return (int)i;
    return -1;
}

static void c_e_or(Comp *c) {
    c_e_and(c);
    while (c_at_punct(c, "||")) {
        size_t j;
        (void)c_bump(c);
        j = c_here(c);
        c_emit(c, OP_JUMP_IF_TRUE_KEEP, 0);
        c_emit(c, OP_POP, 0);
        c_e_and(c);
        c_patch(c, j);
        if (c->aborted) return;
    }
}
static void c_e_and(Comp *c) {
    c_e_cmp(c);
    while (c_at_punct(c, "&&")) {
        size_t j;
        (void)c_bump(c);
        j = c_here(c);
        c_emit(c, OP_JUMP_IF_FALSE_KEEP, 0);
        c_emit(c, OP_POP, 0);
        c_e_cmp(c);
        c_patch(c, j);
        if (c->aborted) return;
    }
}
static void c_e_cmp(Comp *c) {
    c_e_bor(c);
    for (;;) {
        VmOp op;
        if (c_at_punct(c, "==")) op = OP_CMP_EQ;
        else if (c_at_punct(c, "!=")) op = OP_CMP_NE;
        else if (c_at_punct(c, "<=")) op = OP_CMP_LE;
        else if (c_at_punct(c, ">=")) op = OP_CMP_GE;
        else if (c_at_punct(c, "<")) op = OP_CMP_LT;
        else if (c_at_punct(c, ">")) op = OP_CMP_GT;
        else return;
        (void)c_bump(c);
        c_e_bor(c);
        c_emit(c, op, 0);
        if (c->aborted) return;
    }
}
static void c_e_bor(Comp *c) {
    c_e_bxor(c);
    while (c_at_punct(c, "|")) {
        (void)c_bump(c);
        c_e_bxor(c);
        c_emit(c, OP_BIT_OR, 0);
        if (c->aborted) return;
    }
}
static void c_e_bxor(Comp *c) {
    c_e_band(c);
    while (c_at_punct(c, "^")) {
        /* `^` binário é bit_xor; o sigil de retorno `^expr` só existe em
         * posição de statement — como no Zig. */
        (void)c_bump(c);
        c_e_band(c);
        c_emit(c, OP_BIT_XOR, 0);
        if (c->aborted) return;
    }
}
static void c_e_band(Comp *c) {
    c_e_add(c);
    while (c_at_punct(c, "&")) {
        (void)c_bump(c);
        c_e_add(c);
        c_emit(c, OP_BIT_AND, 0);
        if (c->aborted) return;
    }
}
static void c_e_add(Comp *c) {
    c_e_mul(c);
    for (;;) {
        if (c_at_punct(c, "+")) { (void)c_bump(c); c_e_mul(c); c_emit(c, OP_ADD, 0); }
        else if (c_at_punct(c, "-")) { (void)c_bump(c); c_e_mul(c); c_emit(c, OP_SUB, 0); }
        else return;
        if (c->aborted) return;
    }
}
static void c_e_mul(Comp *c) {
    c_e_unary(c);
    for (;;) {
        if (c_at_punct(c, "*")) { (void)c_bump(c); c_e_unary(c); c_emit(c, OP_MUL, 0); }
        else if (c_at_punct(c, "%")) { (void)c_bump(c); c_e_unary(c); c_emit(c, OP_MOD, 0); }
        else if (c_at_punct(c, "/")) { c_fail(c, "VM_REJ_INT_DIVISION"); return; }
        else return;
        if (c->aborted) return;
    }
}
static void c_e_unary(Comp *c) {
    if (c_at_punct(c, "~")) { (void)c_bump(c); c_e_unary(c); c_emit(c, OP_BIT_NOT, 0); return; }
    if (c_at_punct(c, "-")) { (void)c_bump(c); c_e_unary(c); c_emit(c, OP_NEG, 0); return; }
    if (c_at_punct(c, "!")) { (void)c_bump(c); c_e_unary(c); c_emit(c, OP_LOG_NOT, 0); return; }
    c_e_primary(c);
}

static void c_e_primary(Comp *c) {
    C0Tok tk = c_peek(c);
    if (tk.kind == C0_T_STR) { (void)c_bump(c); c_fail(c, "VM_REJ_STRING_LITERAL"); return; }
    if (tk.kind == C0_T_NUMBER) {
        int64_t v = 0;
        (void)c_bump(c);
        if (!c0_parse_i64(tk.text, &v)) { c_fail(c, "VM_REJ_LITERAL_RANGE"); return; }
        c_emit(c, OP_PUSH_CONST, v);
        return;
    }
    if (c_accept_punct(c, "(")) {
        c_expr(c);
        if (!c_accept_punct(c, ")")) c_fail(c, "VM_REJ_PARSE");
        return;
    }
    if (tk.kind == C0_T_IDENT) {
        (void)c_bump(c);
        if (c0_eq(tk.text, "true"))  { c_emit(c, OP_PUSH_CONST, 1); return; }
        if (c0_eq(tk.text, "false")) { c_emit(c, OP_PUSH_CONST, 0); return; }
        if (c_at_punct(c, "(")) {
            size_t argc = 0;
            int fi;
            (void)c_bump(c);
            if (!c_at_punct(c, ")")) {
                for (;;) {
                    c_expr(c);
                    argc++;
                    if (c->aborted || c->reject) return;
                    if (!c_accept_punct(c, ",")) break;
                }
            }
            if (!c_accept_punct(c, ")")) { c_fail(c, "VM_REJ_PARSE"); return; }
            if (c0_eq(tk.text, "_lia_shl") || c0_eq(tk.text, "_lia_shr") ||
                c0_eq(tk.text, "_lia_ushr") || c0_eq(tk.text, "_lia_mod") ||
                c0_eq(tk.text, "@rem")) {
                VmOp op = OP_MOD;
                if (argc != 2) { c_fail(c, "VM_REJ_ARITY"); return; }
                if (c0_eq(tk.text, "_lia_shl")) op = OP_SHL;
                else if (c0_eq(tk.text, "_lia_shr")) op = OP_SHR;
                else if (c0_eq(tk.text, "_lia_ushr")) op = OP_USHR;
                c_emit(c, op, 0);
                return;
            }
            fi = c_find_fn(c, tk.text);
            if (fi >= 0) {
                if (c->m->fns[fi].nparams != argc) { c_fail(c, "VM_REJ_ARITY"); return; }
                c_emit(c, OP_CALL, (int64_t)fi);
                return;
            }
            c_fail(c, "VM_REJ_UNKNOWN_CALL");
            return;
        }
        if (c_at_punct(c, ".")) {
            C0Tok fld;
            int64_t li;
            (void)c_bump(c);
            fld = c_peek(c);
            if (fld.kind == C0_T_IDENT && (c0_eq(fld.text, "length") || c0_eq(fld.text, "len"))) {
                (void)c_bump(c);
                if (c_find_local(c, tk.text, &li)) {
                    if (c_local_arr_n(c, li) == 0) { c_fail(c, "VM_REJ_LENGTH_NOT_ARRAY"); return; }
                    c_emit(c, OP_ARR_LEN, li);
                    return;
                }
                c_fail(c, "VM_REJ_UNBOUND_IDENT");
                return;
            }
            c_fail(c, "VM_REJ_MEMBER_ACCESS");
            return;
        }
        if (c_at_punct(c, "[")) {
            int64_t li;
            if (c_find_local(c, tk.text, &li)) {
                if (c_local_arr_n(c, li) == 0) { c_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
                (void)c_bump(c);
                c_expr(c);
                if (!c_accept_punct(c, "]")) { c_fail(c, "VM_REJ_PARSE"); return; }
                c_emit(c, OP_LOAD_INDEX, li);
                return;
            }
            c_fail(c, "VM_REJ_UNBOUND_IDENT");
            return;
        }
        {
            int64_t li;
            if (c_find_local(c, tk.text, &li)) {
                if (c_local_arr_n(c, li) > 0) { c_fail(c, "VM_REJ_ARRAY_AS_SCALAR"); return; }
                c_emit(c, OP_LOAD_LOCAL, li);
                return;
            }
            c_fail(c, "VM_REJ_UNBOUND_IDENT");
            return;
        }
    }
    c_fail(c, "VM_REJ_PARSE");
    (void)c_bump(c);
}
static void c_expr(Comp *c) { c_e_or(c); }

static void c_emit_arr_lit(Comp *c, int64_t li, uint16_t cap_n) {
    int64_t ei = 0;
    if (!c_accept_punct(c, "[")) { c_fail(c, "VM_REJ_PARSE"); return; }
    if (!c_at_punct(c, "]")) {
        for (;;) {
            if (ei >= (int64_t)cap_n) { c_fail(c, "VM_REJ_ARRAY_LIT_LEN"); return; }
            c_emit(c, OP_PUSH_CONST, ei);
            c_expr(c);
            if (c->aborted) return;
            c_emit(c, OP_STORE_INDEX, li);
            ei++;
            if (!c_accept_punct(c, ",")) break;
        }
    }
    if (!c_accept_punct(c, "]")) c_fail(c, "VM_REJ_PARSE");
}

static void c_assign(Comp *c) {
    C0Tok tk = c_peek(c);
    int64_t li = 0;
    if (tk.kind != C0_T_IDENT) { c_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
    (void)c_bump(c);
    if (c_at_punct(c, "[")) {
        if (c_find_local(c, tk.text, &li)) {
            if (c_local_arr_n(c, li) == 0) { c_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
            (void)c_bump(c);
            c_expr(c);
            if (c->aborted) return;
            if (!c_accept_punct(c, "]")) { c_fail(c, "VM_REJ_PARSE"); return; }
            if (!c_accept_punct(c, "=")) { c_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
            c_expr(c);
            if (c->aborted) return;
            c_emit(c, OP_STORE_INDEX, li);
            return;
        }
        c_fail(c, "VM_REJ_UNBOUND_IDENT");
        return;
    }
    if (c_accept_punct(c, ":")) {
        C0Tok ntk;
        uint16_t nval = 0;
        if (!c_accept_punct(c, "[")) { c_fail(c, "VM_REJ_PARSE"); return; }
        ntk = c_peek(c);
        if (ntk.kind != C0_T_NUMBER) { c_fail(c, "VM_REJ_PARSE"); return; }
        (void)c_bump(c);
        if (!c0_parse_u16(ntk.text, &nval)) { c_fail(c, "VM_REJ_ARRAY_TOO_LARGE"); return; }
        if (nval < 1 || nval > LIN_VM_MAX_ARR_LEN) { c_fail(c, "VM_REJ_ARRAY_TOO_LARGE"); return; }
        if (!c_accept_punct(c, "]")) { c_fail(c, "VM_REJ_PARSE"); return; }
        if (!(c_at_ident(c, "int") || c_at_ident(c, "i64"))) { c_fail(c, "VM_REJ_ARRAY_ELEM_NOT_INT"); return; }
        (void)c_bump(c);
        li = c_local_idx(c, tk.text);
        c_mark_arr(c, li, nval);
        if (c->too_many_locals) return;
        if (c_accept_punct(c, "=")) c_emit_arr_lit(c, li, nval);
        return;
    }
    if (!c_accept_punct(c, "=")) { c_fail(c, "VM_REJ_UNSUPPORTED_STMT"); return; }
    if (c_at_punct(c, "[")) {
        uint16_t cap_n;
        li = c_local_idx(c, tk.text);
        if (c->too_many_locals) return;
        cap_n = c_local_arr_n(c, li);
        if (cap_n == 0) { c_fail(c, "VM_REJ_INDEX_NOT_ARRAY"); return; }
        c_emit_arr_lit(c, li, cap_n);
        return;
    }
    c_expr(c);
    if (c->aborted) return;
    li = c_local_idx(c, tk.text);
    if (c->too_many_locals) return;
    if (c_local_arr_n(c, li) > 0) { c_fail(c, "VM_REJ_ARRAY_AS_SCALAR"); return; }
    c_emit(c, OP_STORE_LOCAL, li);
}

static void c_block(Comp *c) {
    if (!c_accept_punct(c, "{")) { c_fail(c, "VM_REJ_PARSE"); return; }
    while (!c_at_punct(c, "}")) {
        if (c->reject) return;
        if (c_peek(c).kind == C0_T_EOF) { c_fail(c, "VM_REJ_PARSE"); return; }
        c_stmt(c);
    }
    (void)c_bump(c);
}

#define C0_MAX_ENDS 128
static void c_if_chain(Comp *c, size_t *ends, size_t *n_ends) {
    size_t jf, je;
    if (!c_accept_punct(c, "(")) { c_fail(c, "VM_REJ_PARSE"); return; }
    c_expr(c);
    if (c->aborted || c->reject) return;
    if (!c_accept_punct(c, ")")) { c_fail(c, "VM_REJ_PARSE"); return; }
    jf = c_here(c);
    c_emit(c, OP_JUMP_IF_FALSE, 0);
    if (c->aborted) return;
    c_block(c);
    if (c->reject) return;
    je = c_here(c);
    c_emit(c, OP_JUMP, 0);
    if (c->aborted) return;
    if (*n_ends < C0_MAX_ENDS) ends[(*n_ends)++] = je;
    c_patch(c, jf);
    if (c_accept_punct(c, ":")) {
        if (c_at_punct(c, "(")) { c_if_chain(c, ends, n_ends); return; }
        c_block(c);
        return;
    }
    if (c_at_ident(c, "else")) {
        (void)c_bump(c);
        if (c_at_ident(c, "if")) { (void)c_bump(c); c_if_chain(c, ends, n_ends); return; }
        c_block(c);
        return;
    }
}

static void c_stmt(Comp *c) {
    if (c_accept_punct(c, ";")) return;
    if (c_at_punct(c, "^")) {
        (void)c_bump(c);
        c_expr(c);
        if (c->aborted) return;
        (void)c_accept_punct(c, ";");
        c_emit(c, OP_RET, 0);
        return;
    }
    if (c_at_ident(c, "return")) {
        (void)c_bump(c);
        c_expr(c);
        if (c->aborted) return;
        (void)c_accept_punct(c, ";");
        c_emit(c, OP_RET, 0);
        return;
    }
    if (c_at_punct(c, "?") || c_at_ident(c, "if")) {
        size_t ends[C0_MAX_ENDS], n_ends = 0, i;
        (void)c_bump(c);
        c_if_chain(c, ends, &n_ends);
        if (c->reject) return;
        for (i = 0; i < n_ends; i++) c_patch(c, ends[i]);
        (void)c_accept_punct(c, ";");
        return;
    }
    if (c_at_ident(c, "while")) {
        size_t top, jf;
        (void)c_bump(c);
        top = c_here(c);
        if (!c_accept_punct(c, "(")) { c_fail(c, "VM_REJ_PARSE"); return; }
        c_expr(c);
        if (c->aborted || c->reject) return;
        if (!c_accept_punct(c, ")")) { c_fail(c, "VM_REJ_PARSE"); return; }
        jf = c_here(c);
        c_emit(c, OP_JUMP_IF_FALSE, 0);
        if (c->aborted) return;
        c_block(c);
        if (c->reject) return;
        c_emit(c, OP_JUMP, (int64_t)top);
        c_patch(c, jf);
        (void)c_accept_punct(c, ";");
        return;
    }
    if (c_at_punct(c, "#")) { c_fail(c, "VM_REJ_FOR_LOOP"); return; }
    c_assign(c);
    if (c->reject) return;
    if (!c_accept_punct(c, ";")) c_fail(c, "VM_REJ_PARSE");
}

/* ===================== vmBuild + vmResolveDeps ============================ */

static void c_resolve_deps(C0Module *m) {
    int changed = 1;
    while (changed) {
        size_t fi, pc;
        changed = 0;
        for (fi = 0; fi < m->mod.fns_len; fi++) {
            VmFn *f = &m->fns[fi];
            if (!f->ok) continue;
            for (pc = 0; pc < f->code_len; pc++) {
                VmIns *in = &m->ins[m->ins_start[fi] + pc];
                size_t ti = (size_t)in->a;
                if (in->op != OP_CALL) continue;
                if (ti >= m->mod.fns_len || !m->fns[ti].ok) {
                    f->ok = 0;
                    f->reject = "VM_REJ_DEP_REJECTED";
                    changed = 1;
                    break;
                }
            }
        }
    }
}

static int c_copy_name(char *dst, size_t cap, LinStr s) {
    if (s.len + 1 > cap) return 0;
    memcpy(dst, s.p, s.len);
    dst[s.len] = 0;
    return 1;
}

void c0_build(const uint8_t *src, size_t len, C0Module *m) {
    static C0Tok toks[C0_MAX_TOKS];
    C0SigList sigs;
    size_t i;

    memset(m, 0, sizeof(*m));
    c0_scan_fns(src, len, &sigs);
    if (sigs.truncated) { m->fatal = C0_LIMIT_FNS; return; }

    m->total_fns = sigs.n_fns;
    m->mod.fns = m->fns;
    m->mod.fns_len = sigs.n_fns;

    /* 1º laço: nomes, aridades e elegibilidade de assinatura (ordem da fonte) */
    for (i = 0; i < sigs.n_fns; i++) {
        VmFn *f = &m->fns[i];
        const char *rej = c0_sig_eligible(&sigs.fns[i]);
        if (!c_copy_name(m->names[i], C0_MAX_NAME, sigs.fns[i].name)) {
            m->fatal = C0_LIMIT_NAME;
            return;
        }
        f->name = m->names[i];
        f->nparams = sigs.fns[i].nparams;
        f->arr_n = m->arrn[i];
        f->arr_n_len = 0;
        f->reject = rej ? rej : "";
        f->sig_ok = rej ? 0 : 1;
    }
    m->ins_used = 0;

    /* 2º laço: corpo -> bytecode (só assinaturas aptas) */
    for (i = 0; i < sigs.n_fns; i++) {
        Comp c;
        size_t slot, nt;
        VmFn *f = &m->fns[i];
        if (!f->sig_ok) continue;

        memset(&c, 0, sizeof(c));
        c.m = m;
        c.fidx = i;
        c.istart = m->ins_used;
        c.icap = C0_MAX_INS_TOTAL - c.istart;
        memset(m->arrn[i], 0, sizeof(m->arrn[i]));

        nt = c0_tokenize(sigs.fns[i].body.p, sigs.fns[i].body.len, toks, C0_MAX_TOKS);
        if (nt == (size_t)-1) { m->fatal = C0_LIMIT_TOKS; return; }
        c.toks = toks;
        c.ntoks = nt;

        for (slot = 0; slot < sigs.fns[i].nparams; slot++) {
            uint16_t n = 0;
            int64_t li = c_local_idx(&c, sigs.fns[i].p_name[slot]);
            if (c.too_many_locals) break;
            if (c0_arr_len_of(sigs.fns[i].p_type[slot], &n)) {
                if (n < 1 || n > LIN_VM_MAX_ARR_LEN) {
                    f->reject = "VM_REJ_ARRAY_TOO_LARGE";
                    f->sig_ok = 0;
                    slot = sigs.fns[i].nparams;      /* sai do laço, descarta código */
                    break;
                }
                c_mark_arr(&c, li, n);
            }
        }
        if (c.too_many_locals) {
            f->reject = "VM_REJ_TOO_MANY_LOCALS";
            f->sig_ok = 0;
        }
        if (!f->sig_ok) { m->ins_used = c.istart; continue; }

        while (c_peek(&c).kind != C0_T_EOF && c.reject == 0) c_stmt(&c);
        if (c.aborted) { m->fatal = C0_LIMIT_INS; return; }
        if (c.reject) {
            f->reject = c.reject;
            m->ins_used = c.istart;                 /* código descartado, como no Zig */
            continue;
        }
        c_emit(&c, OP_PUSH_CONST, 0);
        c_emit(&c, OP_RET, 0);
        if (c.aborted) { m->fatal = C0_LIMIT_INS; return; }
        m->ins_start[i] = c.istart;
        f->code = m->ins + c.istart;
        f->code_len = c.ilen;
        f->nlocals = c.nlocals;
        f->arr_n_len = c.nlocals;
        f->ok = 1;
        f->reject = "";
        m->ins_used = c.istart + c.ilen;
    }

    c_resolve_deps(m);

    m->eligible_fns = 0;
    for (i = 0; i < m->total_fns; i++) if (m->fns[i].ok) m->eligible_fns++;
}

int c0_find_fn(const C0Module *m, const char *name) {
    size_t i, want = strlen(name);
    for (i = 0; i < m->total_fns; i++)
        if (strlen(m->names[i]) == want && memcmp(m->names[i], name, want) == 0) return (int)i;
    return -1;
}

/* ===================== emissor LINBC1 ==================================== */

typedef struct { C0Image *img; size_t at; } WR;

static void w_u8(WR *w, uint32_t v) { if (w->at < w->img->cap) w->img->out[w->at] = (uint8_t)v; w->at++; }
static void w_u16(WR *w, uint32_t v) { w_u8(w, v & 0xFFu); w_u8(w, (v >> 8) & 0xFFu); }
static void w_u32(WR *w, uint32_t v) {
    w_u8(w, v); w_u8(w, v >> 8); w_u8(w, v >> 16); w_u8(w, v >> 24);
}
static void w_i64(WR *w, int64_t v) {
    uint64_t u = (uint64_t)v;
    int k;
    for (k = 0; k < 8; k++) w_u8(w, (uint32_t)(u >> (8 * k)));
}
static void w_bytes(WR *w, const uint8_t *p, size_t n) {
    size_t i;
    for (i = 0; i < n; i++) w_u8(w, p[i]);
}

void c0_emit_linbc1(const C0Module *m, C0Image *img) {
    WR w;
    size_t i, str_bytes = 0, fns = m->total_fns;
    uint32_t code_total = 0;
    static const char DOM[] = "linbc1:img:";

    img->len = 0;
    img->ok = 0;
    img->err = 0;
    if (m->fatal) { img->err = m->fatal; return; }
    if (fns == 0) { img->err = "C0_EMPTY_MODULE"; return; }
    /* O formato não expressa função rejeitada: módulo não coberto => nada sai. */
    if (fns != m->eligible_fns) { img->err = "C0_REJ_MODULE_NOT_PURE"; return; }

    for (i = 0; i < fns; i++) {
        size_t nl = strlen(m->names[i]);
        if (nl == 0 || nl > C0_MAX_STR_BYTES - str_bytes) { img->err = C0_LIMIT_NAME; return; }
        str_bytes += nl;
        code_total += (uint32_t)m->fns[i].code_len;
    }
    if (code_total > C0_MAX_INS_TOTAL) { img->err = C0_LIMIT_INS; return; }
    if (fns > LIN_BC1_MAX_FNS) { img->err = C0_LIMIT_FNS; return; }

    w.img = img;
    w.at = 0;
    w_bytes(&w, (const uint8_t *)"LINBC1", 6);
    w_u8(&w, 1);                    /* format_version */
    w_u8(&w, 1);                    /* profile = LINVM-1 */
    w_u8(&w, 0);                    /* flags reservados */
    w_u32(&w, (uint32_t)fns);       /* n_strings */
    w_u32(&w, (uint32_t)fns);       /* n_fns     */
    w_u32(&w, 0);                   /* n_regions */
    w_u32(&w, 0);                   /* n_abis    */
    for (i = 0; i < fns; i++) {
        size_t nl = strlen(m->names[i]);
        w_u32(&w, (uint32_t)nl);
        w_bytes(&w, (const uint8_t *)m->names[i], nl);
    }
    for (i = 0; i < fns; i++) {
        const VmFn *f = &m->fns[i];
        size_t pc, li, na = 0;
        for (li = 0; li < f->arr_n_len; li++) if (f->arr_n[li]) na++;
        w_u32(&w, (uint32_t)i);                  /* name_idx = ordem da seção */
        w_u8(&w, (uint32_t)f->nparams);
        w_u8(&w, (uint32_t)f->nlocals);
        w_u8(&w, (uint32_t)na);
        w_u32(&w, (uint32_t)f->code_len);
        for (li = 0; li < f->arr_n_len; li++) {
            if (!f->arr_n[li]) continue;
            w_u8(&w, (uint32_t)li);
            w_u16(&w, (uint32_t)f->arr_n[li]);
        }
        for (pc = 0; pc < f->code_len; pc++) {
            const VmIns *in = &m->ins[m->ins_start[i] + pc];
            w_u8(&w, (uint32_t)in->op);
            w_i64(&w, in->a);
        }
    }
    if (w.at + 32 > img->cap) { img->err = "C0_LIMIT_IMAGE"; return; }
    {
        LinSha256 h;
        lin_sha256_init(&h);
        lin_sha256_update(&h, (const uint8_t *)DOM, sizeof(DOM) - 1);
        lin_sha256_update(&h, img->out, w.at);
        lin_sha256_final(&h, img->out + w.at);
    }
    img->len = w.at + 32;
    img->ok = 1;
}
