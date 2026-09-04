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

    size_t capture_local = LIN_VM_CAPTURE_NONE;
    for (size_t li = 0; li < fn->arr_n_len; li++) {
        if (fn->arr_n[li] != 0) {
            capture_local = li;
            break;
        }
    }
    if (capture_local == LIN_VM_CAPTURE_NONE ||
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
    LinErr exec_err = vm_exec_capture_array(
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
