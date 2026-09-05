/*
 * lin_vm.c — bytecode lowerer + LinVM interpreter.
 *
 * The interpreter is ported opcode-for-opcode from `vmExecWithSp`
 * (lin.zig:6420). The only deliberate C adaptations:
 *   - Zig's `+%`/`-%`/`*%`/`@divTrunc`/`@rem` -> lin_w* (bit-identical wrap)
 *   - `@intCast(ins.a)` on a non-negative value -> (size_t) cast
 *   - `@bitCast(ua << shift)` -> (int64_t)((uint64_t)a << shift)
 *   - `a >> shift` (i64, arithmetic) -> a >> shift (gcc x86-64: arithmetic;
 *     C leaves it implementation-defined — see README)
 */
#include "lin_vm.h"

/* =====================================================================
 * LOWERER — AstToVmLowerer (lin.zig:14525-14630)
 * ===================================================================== */

static LinErr lower_emit(const AstArena *a, uint16_t node,
                         const VarBinding *env, size_t env_len, LoweredCode *out) {
    if (node >= a->len) return LIN_ERR_INVALID_NODE;
    AstTag tag = a->tags[node];
    LinErr e;

    switch (tag) {
    case TAG_LIT:
        if (out->len >= LIN_LOWER_CAP) return LIN_ERR_ARENA_OOM;
        out->code[out->len].op = OP_PUSH_CONST;
        out->code[out->len].a = a->vals[node];
        out->len += 1;
        return LIN_OK;

    case TAG_VAR_REF: {
        size_t found = SIZE_MAX;
        for (size_t i = 0; i < env_len; i++) {
            if (lin_str_eq_cstr(a->names[node], env[i].name)) {
                found = i;
                break;
            }
        }
        if (found == SIZE_MAX) return LIN_ERR_UNDEF_VAR;
        if (out->len >= LIN_LOWER_CAP) return LIN_ERR_ARENA_OOM;
        out->code[out->len].op = OP_LOAD_LOCAL;
        out->code[out->len].a = (int64_t)found;
        out->len += 1;
        return LIN_OK;
    }

    case TAG_UNARY_POS:
        /* Faithful: emits nothing beyond the operand. `+x` compiles to `x`. */
        return lower_emit(a, a->lhs[node], env, env_len, out);

    case TAG_UNARY_NEG:
        e = lower_emit(a, a->lhs[node], env, env_len, out);
        if (e) return e;
        if (out->len >= LIN_LOWER_CAP) return LIN_ERR_ARENA_OOM;
        out->code[out->len].op = OP_NEG;
        out->code[out->len].a = 0;
        out->len += 1;
        return LIN_OK;

    case TAG_ADD:
    case TAG_SUB:
    case TAG_MUL:
    case TAG_DIV:
    case TAG_MOD:
    case TAG_EQ:
    case TAG_NEQ:
    case TAG_LT:
    case TAG_LTE:
    case TAG_GT:
    case TAG_GTE: {
        VmOp op;
        switch (tag) {
        case TAG_ADD:   op = OP_ADD;     break;
        case TAG_SUB:   op = OP_SUB;     break;
        case TAG_MUL:   op = OP_MUL;     break;
        case TAG_DIV:   op = OP_DIV;     break;
        case TAG_MOD:   op = OP_MOD;     break;
        case TAG_EQ:    op = OP_CMP_EQ;  break;
        case TAG_NEQ:   op = OP_CMP_NE;  break;
        case TAG_LT:    op = OP_CMP_LT;  break;
        case TAG_LTE:   op = OP_CMP_LE;  break;
        case TAG_GT:    op = OP_CMP_GT;  break;
        case TAG_GTE:   op = OP_CMP_GE;  break;
        default:        return LIN_ERR_INVALID_NODE;
        }
        e = lower_emit(a, a->lhs[node], env, env_len, out);
        if (e) return e;
        e = lower_emit(a, a->rhs[node], env, env_len, out);
        if (e) return e;
        if (out->len >= LIN_LOWER_CAP) return LIN_ERR_ARENA_OOM;
        out->code[out->len].op = op;
        out->code[out->len].a = 0;
        out->len += 1;
        return LIN_OK;
    }

    case TAG_CALL:
    case TAG_CALL_ARG:
        /* Faithful to the Zig switch: expression-mode lowering rejects calls. */
        return LIN_ERR_UNDEF_VAR;
    }

    return LIN_ERR_INVALID_NODE;
}

LinErr lower_arena(const AstArena *a, uint16_t root,
                   const VarBinding *env, size_t env_len, LoweredCode *out) {
    out->len = 0;
    LinErr e = lower_emit(a, root, env, env_len, out);
    if (e) return e;
    if (out->len >= LIN_LOWER_CAP) return LIN_ERR_ARENA_OOM;
    out->code[out->len].op = OP_RET;
    out->code[out->len].a = 0;
    out->len += 1;
    return LIN_OK;
}

/* =====================================================================
 * LINVM — vmExecWithSp (lin.zig:6420-6590)
 * ===================================================================== */

/* Zig vmShift: b out of [0,64) -> 0; shl = bitcast shift; shr = arithmetic. */
static int64_t vm_shift(int64_t a, int64_t b, int left) {
    if (b < 0 || b >= 64) return 0;
    if (left) return (int64_t)((uint64_t)a << (unsigned)b);
    return a >> (unsigned)b;
}

/* Zig vmShiftU: logical right shift via u64 bitcast. */
static int64_t vm_ushr(int64_t a, int64_t b) {
    if (b < 0 || b >= 64) return 0;
    return (int64_t)((uint64_t)a >> (unsigned)b);
}

static LinErr vm_validate_abi_call_context(
    const LinVmContext *ctx,
    uint8_t abi_id
) {
    if (ctx == NULL || ctx->abi == NULL || ctx->regions == NULL) {
        return LIN_ERR_VM_BAD_FN;
    }
    if (ctx->profile != LIN_VM_PROFILE_LINVM_C0) {
        return LIN_ERR_VM_BAD_FN;
    }
    if (ctx->abi_version != LIN_HOST_ABI_2 ||
        ctx->abi->abi_version != LIN_HOST_ABI_2) {
        return LIN_ERR_VM_BAD_FN;
    }
    if (ctx->abi->regions != ctx->regions) {
        return LIN_ERR_VM_BAD_FN;
    }
    if (!lin_abi2_is_enabled(ctx->abi, abi_id)) {
        return LIN_ERR_VM_BAD_FN;
    }
    return LIN_OK;
}

LinErr vm_exec_ctx(const LinVmContext *ctx, size_t fi,
                   const int64_t *args, size_t args_len,
                   size_t depth, VmExecResult *out) {
    if (ctx == NULL || ctx->module == NULL || ctx->steps == NULL || out == NULL) {
        return LIN_ERR_VM_BAD_FN;
    }
    const VmModule *mod = ctx->module;
    if (depth > LIN_VM_MAX_DEPTH) return LIN_ERR_VM_DEPTH;
    if (fi >= mod->fns_len) return LIN_ERR_VM_BAD_FN;
    const VmFn *f = &mod->fns[fi];
    if (!f->ok) return LIN_ERR_VM_BAD_FN;
    if (args_len != f->nparams) return LIN_ERR_VM_ARITY;

    int64_t locals[LIN_VM_MAX_LOCALS];
    for (size_t i = 0; i < LIN_VM_MAX_LOCALS; i++) locals[i] = 0;

    /* array pool (used by slice-2; always empty in this slice) */
    int64_t pool[LIN_VM_MAX_ARRS][LIN_VM_MAX_ARR_LEN];
    uint16_t pool_len[LIN_VM_MAX_ARRS];
    for (size_t i = 0; i < LIN_VM_MAX_ARRS; i++) pool_len[i] = 0;
    size_t pool_used = 0;

    for (size_t li = 0; li < f->arr_n_len; li++) {
        uint16_t an = f->arr_n[li];
        if (an == 0) continue;
        if (pool_used >= LIN_VM_MAX_ARRS) return LIN_ERR_VM_BAD_FN;
        size_t slot = pool_used;
        pool_used += 1;
        pool_len[slot] = an;
        for (size_t z = 0; z < an; z++) pool[slot][z] = 0;
        locals[li] = (int64_t)slot;
    }

    for (size_t idx = 0; idx < args_len; idx++) {
        if (idx < f->arr_n_len && f->arr_n[idx] > 0) continue;
        locals[idx] = args[idx];
    }

    int64_t stack[LIN_VM_MAX_STACK];
    size_t sp = 0;
    size_t pc = 0;

    while (pc < f->code_len) {
        (*ctx->steps) += 1;
        if (*ctx->steps > ctx->step_limit) return LIN_ERR_VM_STEP_LIMIT;
        VmIns ins = f->code[pc];
        pc += 1;

        switch (ins.op) {
        case OP_PUSH_CONST:
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp] = ins.a;
            sp += 1;
            break;

        case OP_LOAD_LOCAL:
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp] = locals[(size_t)ins.a];
            sp += 1;
            break;

        case OP_STORE_LOCAL:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 1;
            locals[(size_t)ins.a] = stack[sp];
            break;

        case OP_POP:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 1;
            break;

        case OP_BIT_NOT:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            stack[sp - 1] = ~stack[sp - 1];
            break;

        case OP_NEG:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            stack[sp - 1] = lin_wsub(0, stack[sp - 1]); /* Zig: 0 -% x */
            break;

        case OP_LOG_NOT:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            stack[sp - 1] = (stack[sp - 1] == 0) ? 1 : 0;
            break;

        case OP_JUMP:
            pc = (size_t)ins.a;
            break;

        case OP_JUMP_IF_FALSE:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 1;
            if (stack[sp] == 0) pc = (size_t)ins.a;
            break;

        case OP_JUMP_IF_FALSE_KEEP:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            if (stack[sp - 1] == 0) pc = (size_t)ins.a;
            break;

        case OP_JUMP_IF_TRUE_KEEP:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            if (stack[sp - 1] != 0) pc = (size_t)ins.a;
            break;

        case OP_RET:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            out->val = stack[sp - 1];
            out->sp_at_ret = sp;
            return LIN_OK;

        case OP_LOAD_INDEX: {
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 1;
            int64_t ix = stack[sp];
            size_t li = (size_t)ins.a;
            size_t slot = (size_t)locals[li];
            int64_t v = 0;
            if (slot < LIN_VM_MAX_ARRS) {
                uint16_t n = pool_len[slot];
                if (ix >= 0 && ix < (int64_t)n) {
                    v = pool[slot][(size_t)ix];
                }
            }
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp] = v;
            sp += 1;
            break;
        }

        case OP_STORE_INDEX: {
            if (sp < 2) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 2;
            int64_t ix = stack[sp];
            int64_t val = stack[sp + 1];
            size_t li = (size_t)ins.a;
            size_t slot = (size_t)locals[li];
            if (slot < LIN_VM_MAX_ARRS) {
                uint16_t n = pool_len[slot];
                if (ix >= 0 && ix < (int64_t)n) {
                    pool[slot][(size_t)ix] = val;
                }
            }
            break;
        }

        case OP_ARR_LEN: {
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            size_t slot = (size_t)locals[(size_t)ins.a];
            int64_t n = 0;
            if (slot < LIN_VM_MAX_ARRS) n = pool_len[slot];
            stack[sp] = n;
            sp += 1;
            break;
        }

        case OP_CALL: {
            size_t ti = (size_t)ins.a;
            if (ti >= mod->fns_len) return LIN_ERR_VM_BAD_FN;
            size_t n = mod->fns[ti].nparams;
            if (sp < n) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= n;
            VmExecResult r;
            LinErr e = vm_exec_ctx(ctx, ti, stack + sp, n, depth + 1, &r);
            if (e) return e;
            stack[sp] = r.val;
            sp += 1;
            break;
        }

        case OP_ABI_CALL: {
            if (ins.a < 0 || ins.a > UINT8_MAX) {
                return LIN_ERR_VM_BAD_FN;
            }

            uint8_t abi_id = (uint8_t)ins.a;
            LinErr context_error = vm_validate_abi_call_context(ctx, abi_id);
            if (context_error != LIN_OK) return context_error;

            size_t old_sp = sp;
            LinAbiResult result = lin_abi2_dispatch(
                ctx->abi,
                abi_id,
                stack,
                &sp
            );

            if (result.vm_error != LIN_OK) return result.vm_error;

            /* region_check_range is status-producing: a valid call consumes
             * its arguments and pushes TRUNCATED/BOUNDS/etc. as a value.
             * Fatal dispatch failures leave sp unchanged and abort. */
            if (result.region_error != LIN_REGION_OK && sp == old_sp) {
                return LIN_ERR_VM_BAD_FN;
            }
            if (sp >= LIN_VM_MAX_STACK) {
                return LIN_ERR_VM_STACK_OVERFLOW;
            }

            stack[sp] = result.value;
            sp += 1;
            break;
        }

        default: {
            /* binary ops: add sub mul div mod bit_and bit_or bit_xor
             * shl shr ushr cmp_eq cmp_ne cmp_lt cmp_gt cmp_le cmp_ge */
            if (sp < 2) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 2;
            int64_t x = stack[sp];
            int64_t y = stack[sp + 1];
            int64_t r = 0;
            switch (ins.op) {
            case OP_ADD:     r = lin_wadd(x, y); break;
            case OP_SUB:     r = lin_wsub(x, y); break;
            case OP_MUL:     r = lin_wmul(x, y); break;
            case OP_DIV:
                if (y == 0) return LIN_ERR_VM_DIV_ZERO;
                r = lin_wdiv(x, y);
                break;
            case OP_MOD:
                if (y == 0) return LIN_ERR_VM_DIV_ZERO;
                r = lin_wrem(x, y);
                break;
            case OP_BIT_AND: r = x & y; break;
            case OP_BIT_OR:  r = x | y; break;
            case OP_BIT_XOR: r = x ^ y; break;
            case OP_SHL:     r = vm_shift(x, y, 1); break;
            case OP_SHR:     r = vm_shift(x, y, 0); break;
            case OP_USHR:    r = vm_ushr(x, y); break;
            case OP_CMP_EQ:  r = (x == y) ? 1 : 0; break;
            case OP_CMP_NE:  r = (x != y) ? 1 : 0; break;
            case OP_CMP_LT:  r = (x < y) ? 1 : 0; break;
            case OP_CMP_GT:  r = (x > y) ? 1 : 0; break;
            case OP_CMP_LE:  r = (x <= y) ? 1 : 0; break;
            case OP_CMP_GE:  r = (x >= y) ? 1 : 0; break;
            default:         return LIN_ERR_VM_BAD_FN;
            }
            stack[sp] = r;
            sp += 1;
            break;
        }
        }
    }

    /* Zig fallthrough (code ended without `ret`): val=0, sp_at_ret=sp */
    out->val = 0;
    out->sp_at_ret = sp;
    return LIN_OK;
}

LinErr vm_exec(const VmModule *mod, size_t fi, const int64_t *args, size_t args_len,
               size_t depth, uint64_t *steps, VmExecResult *out) {
    LinVmContext ctx;
    ctx.module = mod;
    ctx.regions = NULL;
    ctx.abi = NULL;
    ctx.steps = steps;
    ctx.step_limit = LIN_VM_STEP_LIMIT;
    ctx.profile = LIN_VM_PROFILE_LINVM1;
    ctx.abi_version = LIN_HOST_ABI_1;
    return vm_exec_ctx(&ctx, fi, args, args_len, depth, out);
}

const char *vm_op_name(VmOp op) {
    switch (op) {
    case OP_PUSH_CONST: return "push_const";
    case OP_LOAD_LOCAL: return "load_local";
    case OP_STORE_LOCAL: return "store_local";
    case OP_ADD: return "add";
    case OP_SUB: return "sub";
    case OP_MUL: return "mul";
    case OP_DIV: return "div";
    case OP_MOD: return "mod";
    case OP_BIT_AND: return "bit_and";
    case OP_BIT_OR: return "bit_or";
    case OP_BIT_XOR: return "bit_xor";
    case OP_BIT_NOT: return "bit_not";
    case OP_NEG: return "neg";
    case OP_SHL: return "shl";
    case OP_SHR: return "shr";
    case OP_USHR: return "ushr";
    case OP_CMP_EQ: return "cmp_eq";
    case OP_CMP_NE: return "cmp_ne";
    case OP_CMP_LT: return "cmp_lt";
    case OP_CMP_GT: return "cmp_gt";
    case OP_CMP_LE: return "cmp_le";
    case OP_CMP_GE: return "cmp_ge";
    case OP_LOG_NOT: return "log_not";
    case OP_JUMP: return "jump";
    case OP_JUMP_IF_FALSE: return "jump_if_false";
    case OP_JUMP_IF_FALSE_KEEP: return "jump_if_false_keep";
    case OP_JUMP_IF_TRUE_KEEP: return "jump_if_true_keep";
    case OP_POP: return "pop";
    case OP_CALL: return "call";
    case OP_RET: return "ret";
    case OP_LOAD_INDEX: return "load_index";
    case OP_STORE_INDEX: return "store_index";
    case OP_ARR_LEN: return "arr_len";
    case OP_ABI_CALL: return "abi_call";
    }
    return "?";
}
