/*
 * test_overflow_edges.c — edge vectors NOT in the original Zig suite.
 *
 * The 29 original vectors never touch the INT64 boundaries, which are
 * exactly where Zig and C diverge:
 *   - Zig integer arithmetic is DEFINED WRAPPING; C signed overflow is UB.
 *   - @divTrunc / @rem are defined for INT64_MIN / -1; C is UB there.
 *
 * Every expected value below is computed from Zig's documented semantics
 * (wrapping arithmetic, truncating division/remainder). If this port were a
 * naive C translation (a+b, a*b, x/y, x%y), most of these would be UB —
 * and on gcc -O2 often silently "wrong" in ways the 29 original vectors
 * would never reveal.
 *
 * This is the "differential/edge" layer of the transpilation methodology:
 * the original suite is the contract, this file is the probe.
 */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <limits.h>

#include "lin_common.h"
#include "lin_token.h"
#include "lin_ast.h"
#include "lin_parse.h"
#include "lin_vm.h"

#define I64MIN (-9223372036854775807LL - 1)
#define I64MAX  9223372036854775807LL

typedef struct {
    const char *input;
    int64_t expected;
    const char *desc;
} EdgeCase;

static const EdgeCase edges[] = {
    /* literal parsing wraps (Zig: num = num*10 + d in i64) */
    { "9223372036854775807",           I64MAX,        "INT64_MAX literal" },
    { "9223372036854775808",           I64MIN,        "one past INT64_MAX wraps to INT64_MIN" },
    { "18446744073709551615",          -1,            "2^64-1 wraps to -1" },
    { "18446744073709551616",          0,             "2^64 wraps to 0" },

    /* wrapping arithmetic */
    { "9223372036854775807 + 1",       I64MIN,        "INT64_MAX + 1 wraps to INT64_MIN" },
    { "9223372036854775807 * 2",       -2,            "INT64_MAX * 2 wraps to -2" },
    { "9223372036854775807 - -1",      I64MIN,        "INT64_MAX - (-1) wraps to INT64_MIN" },
    { "-9223372036854775808 + 1",      -9223372036854775807LL, "INT64_MIN + 1" },
    { "-(-9223372036854775808)",       I64MIN,        "negating INT64_MIN wraps to itself (0 -% x)" },

    /* division / modulo: C99 truncation == @divTrunc/@rem, plus the two UB cases */
    { "-7 / 2",                        -3,            "truncation toward zero (not floor)" },
    { "7 / -2",                        -3,            "truncation toward zero (not floor)" },
    { "-7 % 2",                        -1,            "@rem keeps sign of dividend" },
    { "7 % -2",                        1,             "@rem keeps sign of dividend" },
    { "-9223372036854775808 / -1",     I64MIN,        "@divTrunc(INT64_MIN, -1) wraps (C: UB)" },
    { "-9223372036854775808 % -1",     0,             "@rem(INT64_MIN, -1) == 0 (C: UB)" },

    /* combinations of the above */
    { "-9223372036854775808 * -1",     I64MIN,        "INT64_MIN * -1 wraps to INT64_MIN" },
    { "(-9223372036854775808) / 2",    -4611686018427387904LL, "INT64_MIN / 2" },
};

int main(void) {
    const size_t n = sizeof(edges) / sizeof(edges[0]);
    static const VarBinding env0[] = { { "x", 10 }, { "y", 20 }, { "z", 5 }, { "x1", 15 } };

    size_t pass = 0;
    printf("=== C-PORT OVERFLOW EDGE SUITE (Zig wrapping semantics probes) ===\n\n");

    for (size_t i = 0; i < n; i++) {
        const EdgeCase *tc = &edges[i];
        Parser p;
        parser_init(&p, lin_str_of(tc->input));
        uint16_t root = 0;
        LinErr e = parse_full(&p, &root);
        int64_t aval = 0, vval = 0;

        if (e == LIN_OK) {
            e = ast_arena_eval(&p.arena, root, env0, 4, &aval);
        }
        if (e == LIN_OK) {
            LoweredCode lc;
            e = lower_arena(&p.arena, root, env0, 4, &lc);
            if (e == LIN_OK) {
                VmFn fn = { "test_expr", 4, 4, lc.code, lc.len, 1, 1, "", NULL, 0 };
                VmModule mod = { &fn, 1 };
                int64_t args[4] = { 10, 20, 5, 15 };
                uint64_t steps = 0;
                VmExecResult vr;
                e = vm_exec(&mod, 0, args, 4, 0, &steps, &vr);
                vval = vr.val;
            }
        }
        if (e == LIN_OK && aval == tc->expected && vval == tc->expected) {
            printf("  [%2zu/%zu] PASS: \"%-28s\" => %" PRId64 " | %s\n",
                   i + 1, n, tc->input, aval, tc->desc);
            pass++;
        } else {
            printf("  [%2zu/%zu] FAIL: \"%-28s\" => AST:%" PRId64 " VM:%" PRId64
                   " expected %" PRId64 " (%s) | %s\n",
                   i + 1, n, tc->input, aval, vval, tc->expected,
                   e == LIN_OK ? "value mismatch" : lin_err_name(e), tc->desc);
        }
    }

    printf("\nEDGE SUITE: %zu/%zu PASSED\n", pass, n);
    return (pass == n) ? 0 : 1;
}
