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
    LinVmContext ctx = {0};
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
    LinVmContext ctx = {0};
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

static void test_abi_call_and_profile_gate(void) {
    static const VmIns byte_zero_code[] = {
        { OP_PUSH_CONST, 0 },
        { OP_PUSH_CONST, 0 },
        { OP_ABI_CALL, LIN_ABI2_REGION_LOAD_BYTE },
        { OP_RET, 0 }
    };
    static const VmIns byte_one_code[] = {
        { OP_PUSH_CONST, 0 },
        { OP_PUSH_CONST, 1 },
        { OP_ABI_CALL, LIN_ABI2_REGION_LOAD_BYTE },
        { OP_RET, 0 }
    };
    static const VmIns underflow_code[] = {
        { OP_ABI_CALL, LIN_ABI2_REGION_LOAD_BYTE },
        { OP_RET, 0 }
    };
    int64_t cells[1];
    uint8_t payload[2] = {0x00, 0xab};
    LinRegionSet regions;
    LinAbiContext abi;
    VmFn fn;
    VmModule module;
    LinVmContext ctx = {0};
    VmExecResult result;
    uint64_t steps;

    lin_region_set_init(&regions);
    CHECK(lin_region_bind(&regions, 0, cells, 1, 0) == LIN_REGION_OK,
          "bind ABI-call region");
    CHECK(lin_region_write_bytes(&regions.regions[0], payload, sizeof(payload)) == LIN_REGION_OK,
          "write ABI-call payload");
    lin_abi2_context_init(&abi, &regions);
    CHECK(lin_abi2_enable(&abi, LIN_ABI2_REGION_LOAD_BYTE) == LIN_REGION_OK,
          "enable byte intrinsic");

    ctx.module = &module;
    ctx.regions = &regions;
    ctx.abi = &abi;
    ctx.step_limit = 100;
    ctx.profile = LIN_VM_PROFILE_LINVM_C0;
    ctx.abi_version = LIN_HOST_ABI_2;

    init_fn(&fn, "byte_zero", byte_zero_code, 4);
    module.fns = &fn;
    module.fns_len = 1;
    steps = 0;
    ctx.steps = &steps;
    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_OK && result.val == 0,
          "ABI_CALL preserves valid zero byte");

    init_fn(&fn, "byte_one", byte_one_code, 4);
    steps = 0;
    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_OK && result.val == 0xab,
          "ABI_CALL returns nonzero byte");

    init_fn(&fn, "underflow", underflow_code, 2);
    steps = 0;
    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_ERR_VM_STACK_UNDERFLOW,
          "ABI_CALL validates arity through dispatcher");

    init_fn(&fn, "legacy_profile", byte_zero_code, 4);
    ctx.profile = LIN_VM_PROFILE_LINVM1;
    steps = 0;
    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_ERR_VM_BAD_FN,
          "LINVM-1 rejects ABI_CALL");

    ctx.profile = LIN_VM_PROFILE_LINVM_C0;
    ctx.abi_version = LIN_HOST_ABI_1;
    steps = 0;
    CHECK(vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result) == LIN_ERR_VM_BAD_FN,
          "ABI-1 rejects ABI_CALL");
}

#include <pthread.h>

static void test_caller_callee_array_isolation(void) {
    /* LRT-03 proof: Callee's array must never overwrite caller's array.
     * Naive shared static pool causes caller to read 999 instead of 111.
     * With per-depth frame storage, caller reads pristine 111. */
    static const uint16_t arr1[1] = { 1 };
    static const VmIns callee_code[] = {
        { OP_PUSH_CONST, 0 },    /* arr index 0 */
        { OP_PUSH_CONST, 999 },  /* arr[0] = 999 */
        { OP_STORE_INDEX, 0 },   /* local 0 is arr */
        { OP_PUSH_CONST, 0 },
        { OP_RET, 0 }
    };
    static const VmIns caller_code[] = {
        { OP_PUSH_CONST, 0 },    /* arr index 0 */
        { OP_PUSH_CONST, 111 },  /* arr[0] = 111 */
        { OP_STORE_INDEX, 0 },   /* local 0 is arr */
        { OP_CALL, 1 },          /* call callee (fn 1) */
        { OP_POP, 0 },           /* discard callee return */
        { OP_PUSH_CONST, 0 },    /* arr index 0 */
        { OP_LOAD_INDEX, 0 },    /* load arr[0] */
        { OP_RET, 0 }
    };
    VmFn fns[2];
    VmModule module;
    LinVmContext ctx = {0};
    VmExecResult result;
    uint64_t steps = 0;

    init_fn(&fns[0], "caller", caller_code, sizeof(caller_code) / sizeof(caller_code[0]));
    fns[0].nlocals = 1;
    fns[0].arr_n = arr1;
    fns[0].arr_n_len = 1;

    init_fn(&fns[1], "callee", callee_code, sizeof(callee_code) / sizeof(callee_code[0]));
    fns[1].nlocals = 1;
    fns[1].arr_n = arr1;
    fns[1].arr_n_len = 1;

    module.fns = fns;
    module.fns_len = 2;

    ctx.module = &module;
    ctx.regions = NULL;
    ctx.abi = NULL;
    ctx.steps = &steps;
    ctx.step_limit = 1000;
    ctx.profile = LIN_VM_PROFILE_LINVM1;
    ctx.abi_version = LIN_HOST_ABI_1;
    ctx.frames = NULL;

    LinErr err = vm_exec_ctx(&ctx, 0, NULL, 0, 0, &result);
    CHECK(err == LIN_OK, "array isolation execution succeeds");
    CHECK(result.val == 111, "caller array pristine (111 != 999, naive shared pool refuted)");
}

typedef struct {
    const VmModule *module;
    LinErr result_err;
    uint64_t steps;
} ThreadTestArgs;

static void *recursion_thread_entry(void *arg) {
    ThreadTestArgs *targs = (ThreadTestArgs *)arg;
    VmExecResult r;
    targs->result_err = vm_exec(targs->module, 0, NULL, 0, 0, &targs->steps, &r);
    return NULL;
}

static void test_small_stack_recursion_128k(void) {
    /* LRT-03 proof: Deep recursion inside a 128 KiB stack thread must fail closed
     * with error.VmDepth without hitting SIGSEGV / stack exhaustion. */
    static const VmIns recursive_code[] = {
        { OP_CALL, 0 }, /* recurse to fn 0 */
        { OP_RET, 0 }
    };
    VmFn fn;
    VmModule module;
    init_fn(&fn, "bomb", recursive_code, sizeof(recursive_code) / sizeof(recursive_code[0]));
    module.fns = &fn;
    module.fns_len = 1;

    pthread_t th;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    int rc = pthread_attr_setstacksize(&attr, 128 * 1024);
    CHECK(rc == 0, "pthread_attr_setstacksize 128 KiB succeeds");

    ThreadTestArgs args;
    args.module = &module;
    args.result_err = LIN_OK;
    args.steps = 0;

    rc = pthread_create(&th, &attr, recursion_thread_entry, &args);
    pthread_attr_destroy(&attr);
    CHECK(rc == 0, "spawn 128 KiB thread succeeds");

    if (rc == 0) {
        pthread_join(th, NULL);
        CHECK(args.result_err == LIN_ERR_VM_DEPTH, "128 KiB thread fails closed with error.VmDepth (zero SIGSEGV)");
    }
}

int main(void) {
    test_context_and_call_propagation();
    test_custom_step_limit();
    test_legacy_wrapper_and_invalid_context();
    test_abi_call_and_profile_gate();
    test_caller_callee_array_isolation();
    test_small_stack_recursion_128k();

    printf("context tests: %d passed, %d failed\n", pass_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}
