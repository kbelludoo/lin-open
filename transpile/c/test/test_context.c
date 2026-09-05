/* test_context.c — LinVmContext executor integration tests. */
#include <stdio.h>
#include <stdint.h>

#include "../lin_c/lin_vm.h"

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

static void init_fn(VmFn *fn, const char *name, const VmIns *code, size_t code_len) {
    fn->name = name;
    fn->nparams = 0;
    fn->nlocals = 0;
    fn->code = code;
    fn->code_len = code_len;
    fn->sig_ok = 1;
    fn->ok = 1;
    fn->reject = NULL;
    fn->arr_n = NULL;
    fn->arr_n_len = 0;
}

static void test_context_and_call_propagation(void) {
    static const VmIns parent_code[] = {
        { OP_CALL, 1 },
        { OP_RET, 0 }
    };
    static const VmIns child_code[] = {
        { OP_PUSH_CONST, 7 },
        { OP_RET, 0 }
    };
    VmFn fns[2];
    VmModule module;
    LinVmContext ctx;
    VmExecResult result;
    uint64_t steps = 0;
    LinErr error;

    init_fn(&fns[0], "parent", parent_code, 2);
    init_fn(&fns[1], "child", child_code, 2);
    module.fns = fns;
    module.fns_len = 2;

    ctx.module = &module;
    ctx.regions = NULL;
    ctx.abi = NULL;
    ctx.steps = &steps;
    ctx.step_limit = 100;
    ctx.profile = 2;
    ctx.abi_version = LIN_HOST_ABI_2;

    error = vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result);
    CHECK(error == LIN_OK, "context execution succeeds");
    CHECK(result.val == 7, "child result returns through OP_CALL");
    CHECK(result.sp_at_ret == 1, "parent return stack depth");
    CHECK(steps == 4, "steps shared across parent and child");
}

static void test_custom_step_limit(void) {
    static const VmIns parent_code[] = {
        { OP_CALL, 1 },
        { OP_RET, 0 }
    };
    static const VmIns child_code[] = {
        { OP_PUSH_CONST, 7 },
        { OP_RET, 0 }
    };
    VmFn fns[2];
    VmModule module;
    LinVmContext ctx;
    VmExecResult result;
    uint64_t steps = 0;

    init_fn(&fns[0], "parent", parent_code, 2);
    init_fn(&fns[1], "child", child_code, 2);
    module.fns = fns;
    module.fns_len = 2;

    ctx.module = &module;
    ctx.regions = NULL;
    ctx.abi = NULL;
    ctx.steps = &steps;
    ctx.step_limit = 3;
    ctx.profile = 2;
    ctx.abi_version = LIN_HOST_ABI_2;

    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_ERR_VM_STEP_LIMIT,
          "custom step limit is enforced");
    CHECK(steps == 4, "step counter records the failing instruction");
}

static void test_legacy_wrapper_and_invalid_context(void) {
    static const VmIns code[] = {
        { OP_PUSH_CONST, 42 },
        { OP_RET, 0 }
    };
    VmFn fn;
    VmModule module;
    VmExecResult result;
    uint64_t steps = 0;
    LinVmContext invalid = {0};

    init_fn(&fn, "literal", code, 2);
    module.fns = &fn;
    module.fns_len = 1;

    CHECK(vm_exec(&module, 0, NULL, 0, 0, &steps, &result) == LIN_OK,
          "legacy vm_exec wrapper succeeds");
    CHECK(result.val == 42 && steps == 2,
          "legacy wrapper preserves result and default limit");
    CHECK(vm_exec_ctx(&invalid, 0, NULL, 0, 0, &result) == LIN_ERR_VM_BAD_FN,
          "invalid context fails closed");
}

int main(void) {
    test_context_and_call_propagation();
    test_custom_step_limit();
    test_legacy_wrapper_and_invalid_context();

    printf("context tests: %d passed, %d failed\n", pass_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}
