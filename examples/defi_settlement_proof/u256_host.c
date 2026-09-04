/*
 * u256_host.c — single-execution C11 ABI for the U256 settlement engine.
 *
 * ABI:
 *   u256_host IMAGE AMOUNT_IN RESERVE_IN RESERVE_OUT
 *
 * Each value is one 32-byte hexadecimal uint256.  The wrapper converts the
 * canonical big-endian bytes into four raw little-endian u64 words, executes
 * settle_u256 once, captures its first local array (16 uint16 limbs), and
 * converts the result back to canonical bytes.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/lin_c/lin_sha256.h"

static const char RECEIPT_DOMAIN[] = "lin:settlement:v1:";

static int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_bytes32(const char *text, uint8_t out[32]) {
    size_t at = 0;
    if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) at = 2;
    if (strlen(text + at) != 64) return 0;
    for (size_t i = 0; i < 32; i++) {
        int hi = hex_value(text[at + 2 * i]);
        int lo = hex_value(text[at + 2 * i + 1]);
        if (hi < 0 || lo < 0) return 0;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 1;
}

/* bytes32 is printed big-endian; LIN receives raw little-endian u64 words. */
static void bytes32_to_words(const uint8_t bytes[32], int64_t words[4]) {
    for (size_t w = 0; w < 4; w++) {
        uint64_t raw = 0;
        size_t offset = 32 - (w + 1) * 8;
        for (size_t j = 0; j < 8; j++) {
            raw = (raw << 8) | (uint64_t)bytes[offset + j];
        }
        words[w] = (int64_t)raw;
    }
}

/* LIN stores limb 0 as the least-significant 16 bits. */
static int limbs_to_bytes32(const int64_t limbs[16], uint8_t bytes[32]) {
    memset(bytes, 0, 32);
    for (size_t i = 0; i < 16; i++) {
        if (limbs[i] < 0 || limbs[i] > 65535) return 0;
        uint16_t limb = (uint16_t)limbs[i];
        size_t offset = 30 - 2 * i;
        bytes[offset] = (uint8_t)(limb >> 8);
        bytes[offset + 1] = (uint8_t)limb;
    }
    return 1;
}

static int read_file(const char *path, uint8_t **data_out, size_t *len_out) {
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return 0;
    }
    long end = ftell(file);
    if (end <= 0) {
        fclose(file);
        return 0;
    }
    if (fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return 0;
    }

    size_t len = (size_t)end;
    uint8_t *data = (uint8_t *)malloc(len);
    if (!data) {
        fclose(file);
        return 0;
    }
    size_t got = fread(data, 1, len, file);
    fclose(file);
    if (got != len) {
        free(data);
        return 0;
    }
    *data_out = data;
    *len_out = len;
    return 1;
}

static void print_hex32(const uint8_t bytes[32]) {
    for (size_t i = 0; i < 32; i++) printf("%02x", (unsigned)bytes[i]);
}

static void write_u64_le(uint8_t out[8], uint64_t value) {
    for (size_t i = 0; i < 8; i++) out[i] = (uint8_t)(value >> (8 * i));
}

/* The public vm_exec API intentionally returns one scalar and keeps arrays
 * frame-local.  This example host therefore has a bounded, image-specific
 * capture loop.  It mirrors the LINVM opcode semantics needed by this frozen
 * image, while the protected generic interpreter remains unchanged. */
static int64_t u256_shift(int64_t value, int64_t amount, int left) {
    if (amount < 0 || amount >= 64) return 0;
    if (left) return (int64_t)((uint64_t)value << (unsigned)amount);
    return value >> (unsigned)amount;
}

static int64_t u256_ushr(int64_t value, int64_t amount) {
    if (amount < 0 || amount >= 64) return 0;
    return (int64_t)((uint64_t)value >> (unsigned)amount);
}

static LinErr u256_exec_capture(const VmModule *mod, size_t fi,
                                const int64_t *args, size_t args_len,
                                size_t depth, uint64_t *steps,
                                VmExecResult *out, size_t capture_local,
                                int64_t *capture, size_t capture_cap,
                                size_t *capture_len) {
    if (depth > LIN_VM_MAX_DEPTH) return LIN_ERR_VM_DEPTH;
    if (fi >= mod->fns_len) return LIN_ERR_VM_BAD_FN;
    const VmFn *fn = &mod->fns[fi];
    if (!fn->ok) return LIN_ERR_VM_BAD_FN;
    if (args_len != fn->nparams) return LIN_ERR_VM_ARITY;
    if (capture == NULL || capture_len == NULL ||
        capture_local >= fn->arr_n_len || fn->arr_n[capture_local] == 0 ||
        (size_t)fn->arr_n[capture_local] > capture_cap) {
        return LIN_ERR_VM_BAD_FN;
    }
    *capture_len = 0;

    int64_t locals[LIN_VM_MAX_LOCALS];
    for (size_t i = 0; i < LIN_VM_MAX_LOCALS; i++) locals[i] = 0;

    int64_t pool[LIN_VM_MAX_ARRS][LIN_VM_MAX_ARR_LEN];
    uint16_t pool_len[LIN_VM_MAX_ARRS];
    for (size_t i = 0; i < LIN_VM_MAX_ARRS; i++) pool_len[i] = 0;
    size_t pool_used = 0;
    for (size_t li = 0; li < fn->arr_n_len; li++) {
        uint16_t array_len = fn->arr_n[li];
        if (array_len == 0) continue;
        if (pool_used >= LIN_VM_MAX_ARRS) return LIN_ERR_VM_BAD_FN;
        size_t slot = pool_used++;
        pool_len[slot] = array_len;
        for (size_t z = 0; z < array_len; z++) pool[slot][z] = 0;
        locals[li] = (int64_t)slot;
    }
    for (size_t i = 0; i < args_len; i++) {
        if (i < fn->arr_n_len && fn->arr_n[i] > 0) continue;
        locals[i] = args[i];
    }

    int64_t stack[LIN_VM_MAX_STACK];
    size_t sp = 0;
    size_t pc = 0;
    while (pc < fn->code_len) {
        *steps += 1;
        if (*steps > LIN_VM_STEP_LIMIT) return LIN_ERR_VM_STEP_LIMIT;
        VmIns ins = fn->code[pc++];
        switch (ins.op) {
        case OP_PUSH_CONST:
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp++] = ins.a;
            break;
        case OP_LOAD_LOCAL:
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp++] = locals[(size_t)ins.a];
            break;
        case OP_STORE_LOCAL:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            locals[(size_t)ins.a] = stack[--sp];
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
            stack[sp - 1] = lin_wsub(0, stack[sp - 1]);
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
            if (stack[--sp] == 0) pc = (size_t)ins.a;
            break;
        case OP_JUMP_IF_FALSE_KEEP:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            if (stack[sp - 1] == 0) pc = (size_t)ins.a;
            break;
        case OP_JUMP_IF_TRUE_KEEP:
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            if (stack[sp - 1] != 0) pc = (size_t)ins.a;
            break;
        case OP_RET: {
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            size_t slot = (size_t)locals[capture_local];
            uint16_t array_len = fn->arr_n[capture_local];
            if (slot >= LIN_VM_MAX_ARRS || pool_len[slot] != array_len) {
                return LIN_ERR_VM_BAD_FN;
            }
            for (size_t z = 0; z < array_len; z++) capture[z] = pool[slot][z];
            *capture_len = array_len;
            out->val = stack[sp - 1];
            out->sp_at_ret = sp;
            return LIN_OK;
        }
        case OP_LOAD_INDEX: {
            if (sp == 0) return LIN_ERR_VM_STACK_UNDERFLOW;
            int64_t index = stack[--sp];
            size_t slot = (size_t)locals[(size_t)ins.a];
            int64_t value = 0;
            if (slot < LIN_VM_MAX_ARRS) {
                uint16_t array_len = pool_len[slot];
                if (index >= 0 && index < (int64_t)array_len) {
                    value = pool[slot][(size_t)index];
                }
            }
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            stack[sp++] = value;
            break;
        }
        case OP_STORE_INDEX: {
            if (sp < 2) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 2;
            int64_t index = stack[sp];
            int64_t value = stack[sp + 1];
            size_t slot = (size_t)locals[(size_t)ins.a];
            if (slot < LIN_VM_MAX_ARRS) {
                uint16_t array_len = pool_len[slot];
                if (index >= 0 && index < (int64_t)array_len) {
                    pool[slot][(size_t)index] = value;
                }
            }
            break;
        }
        case OP_ARR_LEN: {
            if (sp >= LIN_VM_MAX_STACK) return LIN_ERR_VM_STACK_OVERFLOW;
            size_t slot = (size_t)locals[(size_t)ins.a];
            stack[sp++] = slot < LIN_VM_MAX_ARRS ? pool_len[slot] : 0;
            break;
        }
        case OP_CALL:
            /* settle_u256 is intentionally a leaf function. */
            return LIN_ERR_VM_BAD_FN;
        default: {
            if (sp < 2) return LIN_ERR_VM_STACK_UNDERFLOW;
            sp -= 2;
            int64_t x = stack[sp];
            int64_t y = stack[sp + 1];
            int64_t value = 0;
            switch (ins.op) {
            case OP_ADD: value = lin_wadd(x, y); break;
            case OP_SUB: value = lin_wsub(x, y); break;
            case OP_MUL: value = lin_wmul(x, y); break;
            case OP_DIV:
                if (y == 0) return LIN_ERR_VM_DIV_ZERO;
                value = lin_wdiv(x, y);
                break;
            case OP_MOD:
                if (y == 0) return LIN_ERR_VM_DIV_ZERO;
                value = lin_wrem(x, y);
                break;
            case OP_BIT_AND: value = x & y; break;
            case OP_BIT_OR: value = x | y; break;
            case OP_BIT_XOR: value = x ^ y; break;
            case OP_SHL: value = u256_shift(x, y, 1); break;
            case OP_SHR: value = u256_shift(x, y, 0); break;
            case OP_USHR: value = u256_ushr(x, y); break;
            case OP_CMP_EQ: value = (x == y) ? 1 : 0; break;
            case OP_CMP_NE: value = (x != y) ? 1 : 0; break;
            case OP_CMP_LT: value = (x < y) ? 1 : 0; break;
            case OP_CMP_GT: value = (x > y) ? 1 : 0; break;
            case OP_CMP_LE: value = (x <= y) ? 1 : 0; break;
            case OP_CMP_GE: value = (x >= y) ? 1 : 0; break;
            default: return LIN_ERR_VM_BAD_FN;
            }
            stack[sp++] = value;
            break;
        }
        }
    }

    size_t slot = (size_t)locals[capture_local];
    uint16_t array_len = fn->arr_n[capture_local];
    if (slot >= LIN_VM_MAX_ARRS || pool_len[slot] != array_len) {
        return LIN_ERR_VM_BAD_FN;
    }
    for (size_t z = 0; z < array_len; z++) capture[z] = pool[slot][z];
    *capture_len = array_len;
    out->val = 0;
    out->sp_at_ret = sp;
    return LIN_OK;
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: %s IMAGE AMOUNT_IN RESERVE_IN RESERVE_OUT\n", argv[0]);
        return 2;
    }

    uint8_t input_bytes[3][32];
    for (size_t i = 0; i < 3; i++) {
        if (!parse_bytes32(argv[i + 2], input_bytes[i])) {
            fprintf(stderr, "input %zu is not exactly 32-byte hexadecimal\n", i + 1);
            return 2;
        }
    }

    uint8_t input_concat[96];
    memcpy(input_concat, input_bytes, sizeof(input_concat));
    uint8_t input_sha256[32];
    lin_sha256(input_concat, sizeof(input_concat), input_sha256);

    uint8_t *image = NULL;
    size_t image_len = 0;
    if (!read_file(argv[1], &image, &image_len)) {
        fprintf(stderr, "cannot read LINBC1 image: %s\n", argv[1]);
        return 1;
    }

    LinBc1Vm vm;
    LinBc1Err load_err = lin_bc1_load(image, image_len, &vm);
    if (load_err != LIN_BC1_OK) {
        fprintf(stderr, "LINBC1 rejected image: %s\n", lin_bc1_err_name(load_err));
        free(image);
        return 1;
    }

    int fn_index = lin_bc1_find_fn(&vm, "settle_u256");
    if (fn_index < 0) {
        fprintf(stderr, "LINBC1 image has no settle_u256 function\n");
        free(image);
        return 1;
    }
    const VmFn *fn = &vm.fns[fn_index];
    if (fn->nparams != 12) {
        fprintf(stderr, "settle_u256 ABI has %zu parameters; expected 12\n", fn->nparams);
        free(image);
        return 1;
    }

    size_t capture_local = (size_t)-1;
    for (size_t li = 0; li < fn->arr_n_len; li++) {
        if (fn->arr_n[li] != 0) {
            capture_local = li;
            break;
        }
    }
    if (capture_local == (size_t)-1 ||
        fn->arr_n[capture_local] != 16) {
        fprintf(stderr, "settle_u256 has no 16-limb output array\n");
        free(image);
        return 1;
    }

    int64_t args[12];
    for (size_t input = 0; input < 3; input++) {
        bytes32_to_words(input_bytes[input], &args[input * 4]);
    }

    int64_t limbs[16];
    memset(limbs, 0, sizeof(limbs));
    size_t capture_len = 0;
    uint64_t steps = 0;
    VmExecResult exec_result;
    LinErr exec_err = u256_exec_capture(
        &vm.mod, (size_t)fn_index, args, 12, 0, &steps, &exec_result,
        capture_local, limbs, 16, &capture_len);
    if (exec_err != LIN_OK) {
        fprintf(stderr, "LinVM execution failed: %s\n", lin_err_name(exec_err));
        free(image);
        return 1;
    }

    int64_t status = exec_result.val;
    uint8_t amount_out[32];
    memset(amount_out, 0, sizeof(amount_out));
    if (status == 0) {
        if (capture_len != 16 || !limbs_to_bytes32(limbs, amount_out)) {
            fprintf(stderr, "invalid captured uint256 output\n");
            free(image);
            return 1;
        }
    } else if (status != -1 && status != -2) {
        fprintf(stderr, "unexpected settlement status: %" PRId64 "\n", status);
        free(image);
        return 1;
    }

    /* Fixed-width receipt: domain || program || input || status || output ||
     * steps.  The raw image digest identifies the exact bytes supplied to the
     * fail-closed loader; its LINBC1 loader digest is emitted separately. */
    uint8_t program_sha256[32];
    lin_sha256(image, image_len, program_sha256);
    uint8_t status_le[8], steps_le[8], receipt_sha256[32];
    write_u64_le(status_le, (uint64_t)status);
    write_u64_le(steps_le, steps);
    LinSha256 receipt;
    lin_sha256_init(&receipt);
    lin_sha256_update(&receipt, RECEIPT_DOMAIN, sizeof(RECEIPT_DOMAIN) - 1);
    lin_sha256_update(&receipt, program_sha256, sizeof(program_sha256));
    lin_sha256_update(&receipt, input_sha256, sizeof(input_sha256));
    lin_sha256_update(&receipt, status_le, sizeof(status_le));
    lin_sha256_update(&receipt, amount_out, sizeof(amount_out));
    lin_sha256_update(&receipt, steps_le, sizeof(steps_le));
    lin_sha256_final(&receipt, receipt_sha256);

    printf("@RULEL:LIN_U256_SETTLEMENT:1.0.0\n");
    printf(".result{ status=%" PRId64 " amount_out=0x", status);
    print_hex32(amount_out);
    printf(" steps=%" PRIu64 " program_sha256=sha256:", steps);
    print_hex32(program_sha256);
    printf(" loader_digest=sha256:");
    print_hex32(vm.img_sha256);
    printf(" input_sha256=sha256:");
    print_hex32(input_sha256);
    printf(" receipt_sha256=sha256:");
    print_hex32(receipt_sha256);
    printf(" execution=single_vm_call }\n");

    free(image);
    return 0;
}
