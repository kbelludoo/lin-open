/*
 * lin_ast.h — port of `AstTag`, `VarBinding` and `AstArena`
 * (compiler/lin.zig:14165-14260).
 *
 * The arena is the heart of LIN's "0 heap allocations" design: a fixed
 * [256]-node SoA (struct-of-arrays) block. Children are u16 indices into
 * the same arrays — the whole AST is a flat, pointer-free table, which is
 * why it transpiles to C with zero semantic drift.
 */
#ifndef LIN_C_AST_H
#define LIN_C_AST_H

#include "lin_common.h"

/* Enumeral order mirrors the Zig `AstTag` (lit=0 ... call_arg=16). */
typedef enum {
    TAG_LIT = 0,
    TAG_VAR_REF,
    TAG_UNARY_POS,
    TAG_UNARY_NEG,
    TAG_ADD,
    TAG_SUB,
    TAG_MUL,
    TAG_DIV,
    TAG_MOD,
    TAG_EQ,
    TAG_NEQ,
    TAG_LT,
    TAG_LTE,
    TAG_GT,
    TAG_GTE,
    TAG_CALL,
    TAG_CALL_ARG,
} AstTag;

/* Zig `VarBinding { name: []const u8, val: i64 } */
typedef struct {
    const char *name;
    int64_t val;
} VarBinding;

/* Zig `AstArena` */
typedef struct {
    AstTag tags[LIN_ARENA_CAP];
    uint16_t lhs[LIN_ARENA_CAP];
    uint16_t rhs[LIN_ARENA_CAP];
    int64_t vals[LIN_ARENA_CAP];
    LinStr names[LIN_ARENA_CAP];
    size_t len;
} AstArena;

void ast_arena_init(AstArena *a);

/* Zig `addNode(tag, left, right, val, name) !u16` */
LinErr ast_arena_add(AstArena *a, AstTag tag, uint16_t left, uint16_t right,
                     int64_t val, LinStr name, uint16_t *out_idx);

/* Zig `eval(node_idx, env) !i64` — recursive post-order evaluation.
 * Semantics preserved exactly:
 *   - all arithmetic wraps (lin_wadd/lin_wsub/lin_wmul)
 *   - div = @divTrunc (C '/' + INT64_MIN/-1 special case)
 *   - mod = @rem       (C '%' + INT64_MIN/-1 special case)
 *   - comparisons yield 1/0
 *   - call / call_arg => UndefinedVariable (faithful, even though it reads odd)
 */
LinErr ast_arena_eval(const AstArena *a, uint16_t node,
                      const VarBinding *env, size_t env_len, int64_t *out);

const char *ast_tag_name(AstTag t);

#endif /* LIN_C_AST_H */
