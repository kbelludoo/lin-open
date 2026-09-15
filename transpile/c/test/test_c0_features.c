/* test_c0_features.c — frontend C0 for-loop and integer-division tests. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "../lin_c0_front.h"

static int pass_count;
static int fail_count;

#define CHECK(condition, label) do { \
    if (condition) { \
        pass_count++; \
    } else { \
        fail_count++; \
        fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, label); \
    } \
} while (0)

static int find_fn(const VmModule *mod, const char *name) {
    for (size_t i = 0; i < mod->fns_len; i++) {
        if (strcmp(mod->fns[i].name, name) == 0) return (int)i;
    }
    return -1;
}

static LinErr run_source(
    const char *source,
    const char *name,
    const int64_t *args,
    size_t args_len,
    int64_t *value
) {
    C0Arena *arena = c0_arena_new();
    VmModule *module;
    VmExecResult result;
    uint64_t steps = 0;
    int fi;
    LinErr error;

    if (!arena) return LIN_ERR_ARENA_OOM;
    module = c0_build(arena, source, strlen(source));
    if (!module) {
        c0_arena_free(arena);
        return LIN_ERR_ARENA_OOM;
    }
    fi = find_fn(module, name);
    if (fi < 0 || !module->fns[fi].ok) {
        c0_arena_free(arena);
        return LIN_ERR_VM_BAD_FN;
    }
    error = vm_exec(module, (size_t)fi, args, args_len, 0, &steps, &result);
    if (error == LIN_OK && value) *value = result.val;
    c0_arena_free(arena);
    return error;
}

static void test_for_and_division(void) {
    static const char source[] =
        "!sum_half(n: int) -> int {"
        "  total = 0;"
        "  for (i = 0; i < n; i = i + 1) {"
        "    total = total + i;"
        "  }"
        "  ^total / 2;"
        "}";
    int64_t arg = 6;
    int64_t value = 0;

    CHECK(run_source(source, "sum_half", &arg, 1, &value) == LIN_OK,
          "for plus division compiles and executes");
    CHECK(value == 7, "sum 0..5 divided by 2 truncates to 7");
}

static void test_empty_for_clauses(void) {
    static const char source[] =
        "!constant_loop() -> int {"
        "  i = 0;"
        "  for (; i < 3; ) {"
        "    i = i + 1;"
        "  }"
        "  ^i;"
        "}";
    int64_t value = 0;

    CHECK(run_source(source, "constant_loop", NULL, 0, &value) == LIN_OK,
          "for accepts empty init and increment clauses");
    CHECK(value == 3, "empty-clause for terminates through body update");
}

static void test_division_by_zero_runtime(void) {
    static const char source[] =
        "!bad(x: int) -> int { ^x / 0; }";
    int64_t arg = 7;
    int64_t value = 0;

    CHECK(run_source(source, "bad", &arg, 1, &value) == LIN_ERR_VM_DIV_ZERO,
          "division by zero remains a runtime VM error");
}

static void test_for_malformed_header(void) {
    static const char source[] =
        "!bad() -> int { for (i = 0; i < 2) { i = i + 1; } ^i; }";
    C0Arena *arena = c0_arena_new();
    VmModule *module;
    int fi;

    CHECK(arena != NULL, "arena for malformed for test");
    if (!arena) return;
    module = c0_build(arena, source, strlen(source));
    fi = module ? find_fn(module, "bad") : -1;
    CHECK(fi >= 0 && !module->fns[fi].ok,
          "malformed for header is rejected");
    c0_arena_free(arena);
}

static void test_if_assign_optional_semi(void) {
    static const char source[] =
        "!pick(v: int) -> int {"
        "  w = 7;"
        "  ?(v < 8){ w = 3 };"
        "  ^w;"
        "}";
    int64_t arg = 2;
    int64_t value = 0;

    CHECK(run_source(source, "pick", &arg, 1, &value) == LIN_OK,
          "if-block assignment without inner semicolon compiles");
    CHECK(value == 3, "?(v < 8){ w = 3 } stores 3 when v=2");
    arg = 9;
    CHECK(run_source(source, "pick", &arg, 1, &value) == LIN_OK,
          "if-block assignment false branch still compiles");
    CHECK(value == 7, "?(v < 8){ w = 3 } keeps 7 when v=9");
}

int main(void) {
    test_for_and_division();
    test_empty_for_clauses();
    test_division_by_zero_runtime();
    test_for_malformed_header();
    test_if_assign_optional_semi();

    printf("C0 feature tests: %d passed, %d failed\n", pass_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}
