/*
 * lin_common.c — error display names.
 *
 * These are the exact strings Zig prints for each error value with `{any}`
 * (e.g. `error.DivisionByZero`), so the C runner's FAIL lines match the
 * original `lin test` output byte-for-byte.
 */
#include "lin_common.h"

const char *lin_err_name(LinErr e) {
    switch (e) {
    case LIN_OK: return "error.Success";
    case LIN_ERR_ARENA_OOM: return "error.ArenaOutOfMemory";
    case LIN_ERR_MISSING_CLOSE_PAREN: return "error.MissingClosingParen";
    case LIN_ERR_UNEXPECTED_PRIMARY: return "error.UnexpectedTokenInPrimary";
    case LIN_ERR_INVALID_BINARY_OP: return "error.InvalidBinaryOperator";
    case LIN_ERR_TRAILING_TOKENS: return "error.TrailingTokens";
    case LIN_ERR_INVALID_NODE: return "error.InvalidNodeIndex";
    case LIN_ERR_DIV_ZERO: return "error.DivisionByZero";
    case LIN_ERR_UNDEF_VAR: return "error.UndefinedVariable";
    case LIN_ERR_VM_STEP_LIMIT: return "error.VmStepLimit";
    case LIN_ERR_VM_STACK_OVERFLOW: return "error.VmStackOverflow";
    case LIN_ERR_VM_STACK_UNDERFLOW: return "error.VmStackUnderflow";
    case LIN_ERR_VM_BAD_FN: return "error.VmBadFunction";
    case LIN_ERR_VM_DEPTH: return "error.VmDepth";
    case LIN_ERR_VM_ARITY: return "error.VmArity";
    case LIN_ERR_VM_DIV_ZERO: return "error.VmDivisionByZero";
    case LIN_ERR_PARSE_TOO_DEEP: return "error.ParseTooDeep";
    }
    return "error.Unknown";
}
