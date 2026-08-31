/*
 * lin_ast.c — flat AST arena + recursive evaluator.
 */
#include "lin_ast.h"

void ast_arena_init(AstArena *a) {
    /* Zig: arrays zero-init, names start as "" */
    for (size_t i = 0; i < LIN_ARENA_CAP; i++) {
        a->tags[i] = TAG_LIT;
        a->lhs[i] = 0;
        a->rhs[i] = 0;
        a->vals[i] = 0;
        a->names[i] = lin_str_empty();
    }
    a->len = 0;
}

LinErr ast_arena_add(AstArena *a, AstTag tag, uint16_t left, uint16_t right,
                     int64_t val, LinStr name, uint16_t *out_idx) {
    if (a->len >= LIN_ARENA_CAP) return LIN_ERR_ARENA_OOM;
    uint16_t idx = (uint16_t)a->len;
    a->tags[idx] = tag;
    a->lhs[idx] = left;
    a->rhs[idx] = right;
    a->vals[idx] = val;
    a->names[idx] = name;
    a->len += 1;
    *out_idx = idx;
    return LIN_OK;
}

LinErr ast_arena_eval(const AstArena *a, uint16_t node,
                      const VarBinding *env, size_t env_len, int64_t *out) {
    if (node >= a->len) return LIN_ERR_INVALID_NODE;
    AstTag tag = a->tags[node];

    int64_t l = 0, r = 0;
    LinErr e;

    switch (tag) {
    case TAG_LIT:
        *out = a->vals[node];
        return LIN_OK;

    case TAG_VAR_REF: {
        LinStr target = a->names[node];
        for (size_t i = 0; i < env_len; i++) {
            if (lin_str_eq_cstr(target, env[i].name)) {
                *out = env[i].val;
                return LIN_OK;
            }
        }
        return LIN_ERR_UNDEF_VAR;
    }

    case TAG_UNARY_POS:
        return ast_arena_eval(a, a->lhs[node], env, env_len, out);

    case TAG_UNARY_NEG:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, out);
        if (e) return e;
        *out = lin_wsub(0, *out); /* Zig: 0 -% v */
        return LIN_OK;

    case TAG_ADD:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = lin_wadd(l, r);
        return LIN_OK;

    case TAG_SUB:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = lin_wsub(l, r);
        return LIN_OK;

    case TAG_MUL:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = lin_wmul(l, r);
        return LIN_OK;

    case TAG_DIV:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        if (r == 0) return LIN_ERR_DIV_ZERO;
        *out = lin_wdiv(l, r);
        return LIN_OK;

    case TAG_MOD:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        if (r == 0) return LIN_ERR_DIV_ZERO;
        *out = lin_wrem(l, r);
        return LIN_OK;

    case TAG_EQ:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l == r) ? 1 : 0;
        return LIN_OK;

    case TAG_NEQ:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l != r) ? 1 : 0;
        return LIN_OK;

    case TAG_LT:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l < r) ? 1 : 0;
        return LIN_OK;

    case TAG_LTE:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l <= r) ? 1 : 0;
        return LIN_OK;

    case TAG_GT:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l > r) ? 1 : 0;
        return LIN_OK;

    case TAG_GTE:
        e = ast_arena_eval(a, a->lhs[node], env, env_len, &l); if (e) return e;
        e = ast_arena_eval(a, a->rhs[node], env, env_len, &r); if (e) return e;
        *out = (l >= r) ? 1 : 0;
        return LIN_OK;

    case TAG_CALL:
    case TAG_CALL_ARG:
        /* Faithful to the Zig switch: these arms return UndefinedVariable. */
        return LIN_ERR_UNDEF_VAR;
    }

    /* unreachable */
    return LIN_ERR_INVALID_NODE;
}

const char *ast_tag_name(AstTag t) {
    switch (t) {
    case TAG_LIT: return "lit";
    case TAG_VAR_REF: return "var_ref";
    case TAG_UNARY_POS: return "unary_pos";
    case TAG_UNARY_NEG: return "unary_neg";
    case TAG_ADD: return "add";
    case TAG_SUB: return "sub";
    case TAG_MUL: return "mul";
    case TAG_DIV: return "div";
    case TAG_MOD: return "mod";
    case TAG_EQ: return "eq";
    case TAG_NEQ: return "neq";
    case TAG_LT: return "lt";
    case TAG_LTE: return "lte";
    case TAG_GT: return "gt";
    case TAG_GTE: return "gte";
    case TAG_CALL: return "call";
    case TAG_CALL_ARG: return "call_arg";
    }
    return "?";
}
