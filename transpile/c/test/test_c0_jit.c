/*
 * test_c0_jit.c — Unit Test Suite for LinVM C0 In-Memory JIT Compiler
 *
 * Tests the in-memory C11 JIT emitter, compiler, and runner directly.
 */
#define _GNU_SOURCE
#include "../tool/lin_c0_jit.h"
#include "../tool/lin_tcc_dyn.h"
#include "../lin_c0_front.h"
#include "../lin_c/lin_common.h"
#include "../lin_c/lin_vm.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { \
        tests_run++; \
        printf("  [TEST] %-45s ... ", name); \
    } while (0)

#define PASS() \
    do { \
        tests_passed++; \
        printf("PASS\n"); \
    } while (0)

int main(void) {
    printf("========================================================================\n");
    printf("   TEST SUITE: LIN C0 IN-MEMORY JIT COMPILER & EXECUTION ENGINE\n");
    printf("========================================================================\n");

    /* 1. Check runtime availability */
    TEST("libtcc dynamic runtime availability");
    int avail = c0_jit_is_available();
    assert(avail == 1);
    PASS();

    C0Arena *a = c0_arena_new();
    assert(a != NULL);

    /* 2. Simple arithmetic expression */
    TEST("compile and run arithmetic: (x * 2 + 1)");
    const char *src1 =
        "@LIN:L1c:0.2\n"
        "!affine(x: int) -> int { ^x * 2 + 1; }\n";
    VmModule *m1 = c0_build(a, src1, strlen(src1));
    assert(m1 != NULL);
    assert(m1->fns_len == 1);
    assert(m1->fns[0].ok == 1);

    int64_t args1[1] = {21};
    LinJitResult r1;
    int ok1 = c0_jit_exec(m1, "affine", args1, 1, &r1);
    assert(ok1 == 1);
    assert(r1.success == 1);
    assert(r1.val == 43);
    PASS();

    /* 3. Negative numbers and wrapping */
    TEST("signed wrapping math (INT64_MIN - 1)");
    const char *src2 =
        "@LIN:L1c:0.2\n"
        "!sub_wrap(a: int, b: int) -> int { ^a - b; }\n";
    VmModule *m2 = c0_build(a, src2, strlen(src2));
    assert(m2 != NULL);

    int64_t args2[2] = {-9223372036854775807LL - 1, 1};
    LinJitResult r2;
    int ok2 = c0_jit_exec(m2, "sub_wrap", args2, 2, &r2);
    assert(ok2 == 1);
    assert(r2.val == 9223372036854775807LL); // Wraps to INT64_MAX
    PASS();

    /* 4. Control flow and while loops */
    TEST("control flow while loop (sum 1 to 10)");
    const char *src3 =
        "@LIN:L1c:0.2\n"
        "!sum_to(n: int) -> int {\n"
        "  i = 1;\n"
        "  acc = 0;\n"
        "  while (i <= n) {\n"
        "    acc = acc + i;\n"
        "    i = i + 1;\n"
        "  };\n"
        "  ^acc;\n"
        "}\n";
    VmModule *m3 = c0_build(a, src3, strlen(src3));
    assert(m3 != NULL);

    int64_t args3[1] = {10};
    LinJitResult r3;
    int ok3 = c0_jit_exec(m3, "sum_to", args3, 1, &r3);
    assert(ok3 == 1);
    assert(r3.val == 55); // Sum(1..10) = 55
    PASS();

    /* 5. Inter-function calls */
    TEST("function calls (call other function in module)");
    const char *src4 =
        "@LIN:L1c:0.2\n"
        "!square(x: int) -> int { ^x * x; }\n"
        "!sum_of_squares(a: int, b: int) -> int { ^square(a) + square(b); }\n";
    VmModule *m4 = c0_build(a, src4, strlen(src4));
    assert(m4 != NULL);

    int64_t args4[2] = {3, 4};
    LinJitResult r4;
    int ok4 = c0_jit_exec(m4, "sum_of_squares", args4, 2, &r4);
    assert(ok4 == 1);
    assert(r4.val == 25); // 3^2 + 4^2 = 25
    PASS();

    /* 6. Arrays (load/store/len) */
    TEST("array operations (allocation and indexing)");
    const char *src5 =
        "@LIN:L1c:0.2\n"
        "!test_array(x: int) -> int {\n"
        "  arr: [4]int;\n"
        "  arr[0] = x;\n"
        "  arr[1] = x * 2;\n"
        "  arr[2] = x * 3;\n"
        "  arr[3] = arr[0] + arr[1] + arr[2];\n"
        "  ^arr[3];\n"
        "}\n";
    VmModule *m5 = c0_build(a, src5, strlen(src5));
    assert(m5 != NULL);

    int64_t args5[1] = {10};
    LinJitResult r5;
    int ok5 = c0_jit_exec(m5, "test_array", args5, 1, &r5);
    assert(ok5 == 1);
    assert(r5.val == 60); // 10 + 20 + 30 = 60
    PASS();

    /* 7. Strict Roundtrip Consensus */
    TEST("strict roundtrip consensus (LinVM vs JIT)");
    int ok_rt = c0_jit_roundtrip(m3, "sum_to", args3, 1);
    assert(ok_rt == 1);
    PASS();

    c0_arena_free(a);

    printf("------------------------------------------------------------------------\n");
    printf("   ALL %d JIT UNIT TESTS PASSED (0 FAILURES)\n", tests_passed);
    printf("========================================================================\n");
    return 0;
}
