/*
 * test_c_expr.c — C port of the "REAL STAGE-0 C EXPRESSION PARSER & FLAT AST
 * ARENA TEST SUITE" (compiler/lin.zig:14632-14782).
 *
 * The 29 vectors, the environment {x=10, y=20, z=5, x1=15}, the VM args
 * {10, 20, 5, 15} and the output format are copied verbatim from the Zig
 * source, so this binary's stdout is directly diff-able against the
 * corresponding block of `lin test` (see baseline_diff.sh).
 *
 * The machine-readable summary goes to STDERR on purpose: stdout must stay
 * byte-identical to the original suite.
 */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>

#include "lin_common.h"
#include "lin_token.h"
#include "lin_ast.h"
#include "lin_parse.h"
#include "lin_vm.h"

typedef struct {
    const char *input;
    int64_t expected;
    int has_expected; /* Zig ?i64 */
    int should_fail;
    const char *desc;
} TestCase;

/* Verbatim copy of `test_suite` (lin.zig:14646-14674).
 * Note: the original banner says "(28 VECTORS)" although the suite holds 29
 * entries — reproduced faithfully (the README claims 29/29). */
static const TestCase test_suite[] = {
    { "42", 42, 1, 0, "Single integer literal" },
    { "-5", -5, 1, 0, "Unary negative literal" },
    { "+12", 12, 1, 0, "Unary positive literal" },
    { "1 + -2", -1, 1, 0, "Addition with unary negative" },
    { "1 - -2", 3, 1, 0, "Binary minus with unary negative (1 - (-2) = 3)" },
    { "1 - +2", -1, 1, 0, "Binary minus with unary positive (1 - (+2) = -1)" },
    { "-(1 + 2) * 3", -9, 1, 0, "Unary negative on parenthesized expr" },
    { "10 % 3", 1, 1, 0, "Modulo remainder operation" },
    { "1 + 2 * 3", 7, 1, 0, "Operator precedence (* over +)" },
    { "(1 + 2) * 3", 9, 1, 0, "Parenthesized expression" },
    { "100 - 20 - 10", 70, 1, 0, "Left associativity (100-20-10 = 70)" },
    { "2 * 3 + 4 * 5", 26, 1, 0, "Compound precedence (6 + 20)" },
    { "1 < 2", 1, 1, 0, "Comparison less-than true" },
    { "1 < 2 < 3", 1, 1, 0, "Chained C comparison: (1<2)<3 => 1<3 => 1" },
    { "3 == 3", 1, 1, 0, "Comparison equality true" },
    { "5 != 5", 0, 1, 0, "Comparison inequality false" },
    { "10 >= 10", 1, 1, 0, "Comparison greater-equal true" },
    { "1 + 2 == 3", 1, 1, 0, "Precedence arithmetic before comparison" },
    { "x + 1", 11, 1, 0, "Variable lookup (x=10)" },
    { "x1 + 2", 17, 1, 0, "Alphanumeric identifier (x1=15)" },
    { "x * y + z", 205, 1, 0, "Multi-variable expression (10*20 + 5)" },
    { "(x + y) / z", 6, 1, 0, "Variables in parentheses (30 / 5)" },
    { "50 + 20 * (30 - 10) / 4", 150, 1, 0, "Complex mixed expression" },
    { "1 + * 2", 0, 0, 1, "Syntax error (consecutive binary ops)" },
    { "( 2 + 3", 0, 0, 1, "Unclosed parenthesis" },
    { "5 / 0", 0, 0, 1, "Division by zero" },
    { "5 % 0", 0, 0, 1, "Modulo by zero" },
    { "1x + 2", 0, 0, 1, "Invalid identifier starting with digit" },
    { "unknown_var + 1", 0, 0, 1, "Undefined variable reference" },
};

/* Verbatim copy of `global_env` (lin.zig:14641-14644). */
static const VarBinding global_env[] = {
    { "x", 10 },
    { "y", 20 },
    { "z", 5 },
    { "x1", 15 },
};

static const int ENV_LEN = (int)(sizeof(global_env) / sizeof(global_env[0]));

/* Result of pushing one vector through parse -> eval -> lower -> VM,
 * with per-stage errors so the rejection point is reported exactly like
 * the Zig harness (parse / AST eval / lower / LinVM). */
typedef struct {
    LinErr parse_err;
    LinErr eval_err;
    LinErr lower_err;
    LinErr vm_err;
    int64_t ast_val;
    VmExecResult vm_res;
    size_t insts;
} PipelineResult;

static PipelineResult run_pipeline(const TestCase *tc) {
    PipelineResult r;
    r.parse_err = LIN_OK;
    r.eval_err = LIN_OK;
    r.lower_err = LIN_OK;
    r.vm_err = LIN_OK;
    r.ast_val = 0;
    r.vm_res.val = 0;
    r.vm_res.sp_at_ret = 0;
    r.insts = 0;

    Parser p;
    parser_init(&p, lin_str_of(tc->input));
    uint16_t root = 0;
    r.parse_err = parse_full(&p, &root);
    if (r.parse_err != LIN_OK) return r;

    r.eval_err = ast_arena_eval(&p.arena, root, global_env, (size_t)ENV_LEN, &r.ast_val);
    if (r.eval_err != LIN_OK) return r;

    LoweredCode lc;
    r.lower_err = lower_arena(&p.arena, root, global_env, (size_t)ENV_LEN, &lc);
    if (r.lower_err != LIN_OK) return r;

    /* Mock fn/module exactly like the Zig harness:
     * VmFn{ .name="test_expr", .nparams=4, .nlocals=4, .code=bytecode, ok, sig_ok } */
    VmFn fn;
    fn.name = "test_expr";
    fn.nparams = (size_t)ENV_LEN;
    fn.nlocals = (size_t)ENV_LEN;
    fn.code = lc.code;
    fn.code_len = lc.len;
    fn.sig_ok = 1;
    fn.ok = 1;
    fn.reject = "";
    fn.arr_n = NULL;
    fn.arr_n_len = 0;
    VmModule mod;
    mod.fns = &fn;
    mod.fns_len = 1;

    int64_t vm_args[4] = { 10, 20, 5, 15 };
    uint64_t steps = 0;
    r.vm_err = vm_exec(&mod, 0, vm_args, 4, 0, &steps, &r.vm_res);
    r.insts = lc.len;
    return r;
}

int main(void) {
    const size_t n = sizeof(test_suite) / sizeof(test_suite[0]);
    const char bar[] =
        "================================================================================";

    /* Verbatim banner (lin.zig:14677-14682) */
    printf("\n%s\n", bar);
    printf("=== REAL STAGE-0 C EXPRESSION PARSER & FLAT AST ARENA TEST SUITE (28 VECTORS) ===\n");
    printf("%s\n\n", bar);

    size_t pass = 0;

    for (size_t i = 0; i < n; i++) {
        const TestCase *tc = &test_suite[i];
        PipelineResult r = run_pipeline(tc);

        if (tc->should_fail) {
            if (r.parse_err != LIN_OK) {
                printf("  [%2zu/%zu] PASS: \"%s\" properly rejected at parse (%s)\n",
                       i + 1, n, tc->input, tc->desc);
                pass++;
            } else if (r.eval_err != LIN_OK) {
                printf("  [%2zu/%zu] PASS: \"%s\" properly rejected in AST eval (%s)\n",
                       i + 1, n, tc->input, tc->desc);
                pass++;
            } else if (r.lower_err != LIN_OK) {
                printf("  [%2zu/%zu] PASS: \"%s\" properly rejected at lower (%s)\n",
                       i + 1, n, tc->input, tc->desc);
                pass++;
            } else if (r.vm_err != LIN_OK) {
                printf("  [%2zu/%zu] PASS: \"%s\" properly rejected in LinVM (%s)\n",
                       i + 1, n, tc->input, tc->desc);
                pass++;
            } else {
                printf("  [%2zu/%zu] FAIL: \"%s\" expected error, but succeeded in AST and VM\n",
                       i + 1, n, tc->input);
            }
            continue;
        }

        /* success path — mirrors lin.zig:14729-14773 */
        if (r.parse_err != LIN_OK) {
            printf("  [%2zu/%zu] FAIL: \"%s\" parse error: %s\n",
                   i + 1, n, tc->input, lin_err_name(r.parse_err));
            continue;
        }
        if (r.eval_err != LIN_OK) {
            printf("  [%2zu/%zu] FAIL: \"%s\" evaluation error: %s\n",
                   i + 1, n, tc->input, lin_err_name(r.eval_err));
            continue;
        }
        if (r.lower_err != LIN_OK) {
            printf("  [%2zu/%zu] FAIL: \"%s\" lowering error: %s\n",
                   i + 1, n, tc->input, lin_err_name(r.lower_err));
            continue;
        }
        if (r.vm_err != LIN_OK) {
            printf("  [%2zu/%zu] FAIL: \"%s\" LinVM execution error: %s\n",
                   i + 1, n, tc->input, lin_err_name(r.vm_err));
            continue;
        }

        if (r.ast_val == tc->expected && r.vm_res.val == tc->expected) {
            printf("  [%2zu/%zu] PASS: \"%-24s\" => AST:%4" PRId64
                   " == VM:%4" PRId64 " (Insts: %2zu) | %s\n",
                   i + 1, n, tc->input, r.ast_val, r.vm_res.val, r.insts, tc->desc);
            pass++;
        } else {
            printf("  [%2zu/%zu] FAIL: \"%s\" => AST:%" PRId64 ", VM:%" PRId64
                   ", expected %" PRId64 "\n",
                   i + 1, n, tc->input, r.ast_val, r.vm_res.val, tc->expected);
        }
    }

    /* stdout above must match `lin test` byte-for-byte; the machine-readable
     * verdict goes to stderr so a `diff` of stdout stays clean. */
    fprintf(stderr, "C-PORT STAGE-0 C-EXPRESSION SUITE: %zu/%zu PASSED\n", pass, n);
    return (pass == n) ? 0 : 1;
}
