/*
 * lin_vm.h — port of `VmOp`, `VmIns`, `VmFn`, `VmModule` (lin.zig:5583-5640),
 * `AstToVmLowerer` (lin.zig:14525-14630) and `vmExecWithSp` (lin.zig:6420-6590).
 */
#ifndef LIN_C_VM_H
#define LIN_C_VM_H

#include "lin_ast.h"
#include "lin_abi.h"

#define LIN_VM_PROFILE_LINVM1  1u
#define LIN_VM_PROFILE_LINVM_C0 2u

/* Enumeral order mirrors the Zig `VmOp` (push_const=0 ... arr_len=31).
 * Slice-1 lowers only a subset; the full set is ported so slice-2
 * (statements/control flow) can reuse the same interpreter unchanged. */
typedef enum {
    OP_PUSH_CONST = 0,
    OP_LOAD_LOCAL,
    OP_STORE_LOCAL,
    OP_ADD,
    OP_SUB,
    OP_MUL,
    OP_DIV,
    OP_MOD,
    OP_BIT_AND,
    OP_BIT_OR,
    OP_BIT_XOR,
    OP_BIT_NOT,
    OP_NEG,
    OP_SHL,
    OP_SHR,
    OP_USHR,
    OP_CMP_EQ,
    OP_CMP_NE,
    OP_CMP_LT,
    OP_CMP_GT,
    OP_CMP_LE,
    OP_CMP_GE,
    OP_LOG_NOT,
    OP_JUMP,
    OP_JUMP_IF_FALSE,
    OP_JUMP_IF_FALSE_KEEP,
    OP_JUMP_IF_TRUE_KEEP,
    OP_POP,
    OP_CALL,
    OP_RET,
    OP_LOAD_INDEX,
    OP_STORE_INDEX,
    OP_ARR_LEN,

    /* Additive opcode: unavailable in the frozen LINVM-1 profile. */
    OP_ABI_CALL,
} VmOp;

/* Zig `VmIns { op: VmOp, a: i64 = 0 } */
typedef struct {
    VmOp op;
    int64_t a;
} VmIns;

/* Zig `VmFn` (only the fields this pipeline uses, kept in Zig order) */
typedef struct {
    const char *name;
    size_t nparams;
    size_t nlocals;
    const VmIns *code;
    size_t code_len;
    int sig_ok;
    int ok;
    const char *reject;
    const uint16_t *arr_n;
    size_t arr_n_len;
} VmFn;

/* Zig `VmModule { fns: []VmFn } */
typedef struct {
    VmFn *fns;
    size_t fns_len;
} VmModule;

/* Zig `VmExecResult { val: i64, sp_at_ret: usize }` */
typedef struct {
    int64_t val;
    size_t sp_at_ret;
} VmExecResult;

/* Per-frame storage moved off the native C stack to support small stack hosts */
typedef struct {
    int64_t locals[LIN_VM_MAX_LOCALS];
    int64_t stack[LIN_VM_MAX_STACK];
    int64_t pool[LIN_VM_MAX_ARRS][LIN_VM_MAX_ARR_LEN];
    uint16_t pool_len[LIN_VM_MAX_ARRS];
    size_t pool_used;
} VmFrame;

typedef struct {
    VmFrame frames[LIN_VM_MAX_DEPTH + 1];
} VmFrameStore;

VmFrameStore *lin_vm_frames_alloc(void);
void lin_vm_frames_free(VmFrameStore *s);

/* Per-execution state shared by every frame, including OP_CALL children.
 * The module, regions and ABI context are borrowed; the caller owns them.
 * `steps` is shared across the complete call tree and `step_limit` is the
 * limit for this execution, not a process-global constant. */
typedef struct {
    const VmModule *module;
    const LinRegionSet *regions;
    const LinAbiContext *abi;
    uint64_t *steps;
    uint64_t step_limit;
    uint8_t profile;
    uint8_t abi_version;
    VmFrameStore *frames;
} LinVmContext;

/* Zero-allocation substitute for Zig's `ArrayList(VmIns)`. See LIN_LOWER_CAP. */
typedef struct {
    VmIns code[LIN_LOWER_CAP];
    size_t len;
} LoweredCode;

/* Zig `AstToVmLowerer.lower(arena, root, env) ![]VmIns` — post-order
 * emission + one trailing `ret`. */
LinErr lower_arena(const AstArena *a, uint16_t root,
                   const VarBinding *env, size_t env_len, LoweredCode *out);

LinErr vm_exec_ctx(const LinVmContext *ctx, size_t fi,
                   const int64_t *args, size_t args_len,
                   size_t depth, VmExecResult *out);

/* Zig `vmExecWithSp(mod, fi, args, depth, steps) !VmExecResult`.
 * `depth` is the call nesting (top-level = 0). `*steps` is a running
 * step counter shared across recursive calls, exactly like the Zig pointer. */
LinErr vm_exec(const VmModule *mod, size_t fi, const int64_t *args, size_t args_len,
               size_t depth, uint64_t *steps, VmExecResult *out);

const char *vm_op_name(VmOp op);

#endif /* LIN_C_VM_H */
