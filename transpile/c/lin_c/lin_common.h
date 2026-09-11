/*
 * lin_common.h — shared types for the Zig -> C transpilation of LIN's
 * Stage-0 C-expression pipeline (tokenizer -> Pratt parser -> flat AST arena
 * -> AST eval -> bytecode lowerer -> LinVM).
 *
 * Source of truth: compiler/lin.zig (kbelludoo/lin).
 * Every Zig-to-C semantic decision is documented in README.md.
 */
#ifndef LIN_C_COMMON_H
#define LIN_C_COMMON_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <limits.h>

/* ---- Zig []const u8 (slice) --------------------------------------------
 * Zig slices are (pointer, length) pairs that alias the source buffer.
 * We keep that aliasing: arena node `name` points into the input string,
 * exactly like Zig's `names: [256][]const u8`.
 */
typedef struct {
    const uint8_t *p;
    size_t len;
} LinStr;

static inline LinStr lin_str_of(const char *s) {
    LinStr x;
    x.p = (const uint8_t *)s;
    x.len = strlen(s);
    return x;
}

static inline LinStr lin_str_empty(void) {
    LinStr x;
    x.p = (const uint8_t *)"";
    x.len = 0;
    return x;
}

static inline int lin_str_eq_cstr(LinStr a, const char *b) {
    size_t n = strlen(b);
    return a.len == n && (n == 0 || memcmp(a.p, b, n) == 0);
}

/* ---- Error model ---------------------------------------------------------
 * Zig uses error unions (`ParseError!u16`, `VmError!i64`). C has no such
 * type; the mapping used throughout this port:
 *
 *   Zig:  fn f(...) ParseError!u16          C:  LinErr f(..., uint16_t *out)
 *   Zig:  return error.DivisionByZero       C:  return LIN_ERR_DIV_ZERO
 *   Zig:  try x / return x                  C:  LinErr e = x(); if (e) return e;
 *
 * The names below are the *display* names of the Zig errors, so the C test
 * runner can reproduce the `error.X` text of `lin test` byte-for-byte.
 */
typedef enum {
    LIN_OK = 0,
    /* arena */
    LIN_ERR_ARENA_OOM,
    /* parser */
    LIN_ERR_MISSING_CLOSE_PAREN,
    LIN_ERR_UNEXPECTED_PRIMARY,
    LIN_ERR_INVALID_BINARY_OP,
    LIN_ERR_TRAILING_TOKENS,
    /* eval / lower */
    LIN_ERR_INVALID_NODE,
    LIN_ERR_DIV_ZERO,
    LIN_ERR_UNDEF_VAR,
    /* VM */
    LIN_ERR_VM_STEP_LIMIT,
    LIN_ERR_VM_STACK_OVERFLOW,
    LIN_ERR_VM_STACK_UNDERFLOW,
    LIN_ERR_VM_BAD_FN,
    LIN_ERR_VM_DEPTH,
    LIN_ERR_VM_ARITY,
    LIN_ERR_VM_DIV_ZERO,
    /* LRT-02: parser depth limit */
    LIN_ERR_PARSE_TOO_DEEP,
} LinErr;

const char *lin_err_name(LinErr e);

/* ---- Wrapping integer arithmetic (the core of the port) -------------------
 * Zig's default integer arithmetic is *defined wrapping* (`+%`, `-%`, `*%`).
 * C's signed overflow is undefined behavior. The trick: do the math in
 * uint64_t, where C guarantees modular (2^64) arithmetic, then bit-cast
 * back to int64_t. This is bit-identical to Zig for every input.
 */
static inline int64_t lin_wadd(int64_t a, int64_t b) { return (int64_t)((uint64_t)a + (uint64_t)b); }
static inline int64_t lin_wsub(int64_t a, int64_t b) { return (int64_t)((uint64_t)a - (uint64_t)b); }
static inline int64_t lin_wmul(int64_t a, int64_t b) { return (int64_t)((uint64_t)a * (uint64_t)b); }

/* @divTrunc: C's '/' (C99) already truncates toward zero — identical to Zig
 * for every case EXCEPT INT64_MIN / -1: Zig wraps to INT64_MIN, C is UB. */
static inline int64_t lin_wdiv(int64_t x, int64_t y) {
    if (x == INT64_MIN && y == -1) return INT64_MIN; /* Zig: wrapping */
    return x / y;
}

/* @rem: C's '%' already truncates toward zero — identical EXCEPT
 * INT64_MIN % -1: Zig yields 0, C is UB. */
static inline int64_t lin_wrem(int64_t x, int64_t y) {
    if (x == INT64_MIN && y == -1) return 0; /* Zig: @rem */
    return x % y;
}

/* ---- Constants (mirrored from lin.zig) ------------------------------------ */
#define LIN_ARENA_CAP      256            /* tags: [256]AstTag — "0 heap allocations" */
#define LIN_PARSER_MAX_DEPTH 64           /* LRT-02: maximum recursion depth in Pratt parser */
#define LIN_MAX_ARGS       16             /* arg_nodes: [16]u16 in parsePrimary */
#define LIN_VM_MAX_LOCALS  64
#define LIN_VM_MAX_STACK   256
#define LIN_VM_MAX_DEPTH   192
#define LIN_VM_STEP_LIMIT  200000000ULL
#define LIN_VM_MAX_ARRS    8
#define LIN_VM_MAX_ARR_LEN 256

/* Zig's ArrayList(VmIns) grows on the heap. The C port is zero-allocation:
 * in this slice each AST node emits at most one instruction and the arena
 * holds at most 256 nodes, so 512 instructions cannot be exhausted
 * (256 nodes + 1 final `ret`). Documented bound, checked anyway. */
#define LIN_LOWER_CAP      512

#endif /* LIN_C_COMMON_H */
