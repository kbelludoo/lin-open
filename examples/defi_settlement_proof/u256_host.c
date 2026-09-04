#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/lin_c/lin_sha256.h"

// Resultado da liquidação uint256
typedef struct {
    int64_t  status;          // 1 = APPROVED, -1 = INV_INPUT, -2 = OVERFLOW
    uint8_t  amount_out[32];  // 32 bytes big-endian (padrão EVM)
    uint64_t words_out[4];    // 4 palavras de 64 bits little-endian
    uint64_t steps_total;     // Passos acumulados da LinVM
} LinU256SettlementResult;

// Converte bytes big-endian de 32 bytes para 4 palavras de 64 bits little-endian (representação LIN)
static void u256_bytes_be_to_words_le(const uint8_t be[32], int64_t words[4]) {
    for (int i = 0; i < 4; i++) {
        uint64_t w = 0;
        int base = 32 - 8 * (i + 1);
        for (int b = 0; b < 8; b++) {
            w = (w << 8) | (uint64_t)be[base + b];
        }
        words[i] = (int64_t)w;
    }
}

// Converte 4 palavras de 64 bits little-endian para bytes big-endian de 32 bytes (padrão EVM)
static void u256_words_le_to_bytes_be(const uint64_t words[4], uint8_t be[32]) {
    for (int i = 0; i < 4; i++) {
        uint64_t w = words[i];
        int base = 32 - 8 * (i + 1);
        for (int b = 7; b >= 0; b--) {
            be[base + b] = (uint8_t)(w & 0xFF);
            w >>= 8;
        }
    }
}

// Execução de liquidação uint256 em um único ponto de entrada do Host C11
int lin_settle_u256_single_shot(
    const LinBc1Vm *vm,
    int fn_idx,
    const uint8_t amount_in_be[32],
    const uint8_t reserve_in_be[32],
    const uint8_t reserve_out_be[32],
    LinU256SettlementResult *res_out
) {
    if (!vm || !res_out || fn_idx < 0) return -1;
    memset(res_out, 0, sizeof(*res_out));

    int64_t ain[4], rin[4], rout[4];
    u256_bytes_be_to_words_le(amount_in_be, ain);
    u256_bytes_be_to_words_le(reserve_in_be, rin);
    u256_bytes_be_to_words_le(reserve_out_be, rout);

    int64_t args[13];
    for (int i = 0; i < 4; i++) {
        args[i]     = ain[i];
        args[4 + i] = rin[i];
        args[8 + i] = rout[i];
    }

    uint64_t total_steps = 0;

    // Primeiro checa status com out_word_idx = -1
    args[12] = -1;
    VmExecResult r_status;
    uint64_t step_count = 0;
    LinErr err = vm_exec(&vm->mod, (size_t)fn_idx, args, 13, 0, &step_count, &r_status);
    if (err != LIN_OK) {
        res_out->status = -1;
        return (int)err;
    }
    total_steps += step_count;
    if (r_status.val < 0) {
        res_out->status = r_status.val;
        res_out->steps_total = total_steps;
        return 0;
    }

    // Se status == 1, recupera as 4 palavras
    for (int w = 0; w < 4; w++) {
        args[12] = (int64_t)w;
        step_count = 0;
        VmExecResult r;
        err = vm_exec(&vm->mod, (size_t)fn_idx, args, 13, 0, &step_count, &r);
        if (err != LIN_OK) {
            res_out->status = -1;
            return (int)err;
        }
        total_steps += step_count;
        res_out->words_out[w] = (uint64_t)r.val;
    }

    res_out->status = 1; // Aprovado
    res_out->steps_total = total_steps;
    u256_words_le_to_bytes_be(res_out->words_out, res_out->amount_out);
    return 0;
}

static void print_hex(const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; i++) printf("%02x", data[i]);
}

int main(void) {
    const char *img_path = "examples/defi_settlement_proof/u256_settlement_engine.linbc";
    FILE *f = fopen(img_path, "rb");
    if (!f) {
        fprintf(stderr, "Erro ao abrir imagem LINBC1 '%s'\n", img_path);
        return 1;
    }
    uint8_t img_bytes[64 * 1024];
    size_t img_len = fread(img_bytes, 1, sizeof(img_bytes), f);
    fclose(f);

    LinBc1Vm vm;
    LinBc1Err err = lin_bc1_load(img_bytes, img_len, &vm);
    if (err != LIN_BC1_OK) {
        fprintf(stderr, "Rejeição LINBC1: %s\n", lin_bc1_err_name(err));
        return 1;
    }

    int fn_settle = lin_bc1_find_fn(&vm, "settle_u256_word");
    if (fn_settle < 0) {
        fprintf(stderr, "Função settle_u256_word ausente\n");
        return 1;
    }

    printf("========================================================================\n");
    printf("     LIN HOST C11: LIQUIDAÇÃO DETERMINÍSTICA UINT256 (PILOTO PROD)      \n");
    printf("========================================================================\n");
    printf("[LinVM Bytecode Image] %zu bytes | Digest: ", img_len);
    print_hex(vm.img_sha256, 32);
    printf("\n\n");

    uint8_t ain[32] = {0}, rin[32] = {0}, rout[32] = {0};
    uint64_t v_ain = 1000000000000000000ULL;
    uint64_t v_rin = 5000000000000000000ULL;
    uint64_t v_rout = 10000000000000000000ULL;
    for (int i = 0; i < 8; i++) {
        ain[31 - i] = (uint8_t)(v_ain >> (i * 8));
        rin[31 - i] = (uint8_t)(v_rin >> (i * 8));
        rout[31 - i] = (uint8_t)(v_rout >> (i * 8));
    }

    LinU256SettlementResult res;
    int rc = lin_settle_u256_single_shot(&vm, fn_settle, ain, rin, rout, &res);
    if (rc != 0) {
        fprintf(stderr, "Erro ao executar lin_settle_u256_single_shot: rc=%d\n", rc);
        return 1;
    }

    printf("Input 96 Bytes (Big-Endian Hex):\n");
    printf("  amount_in:   "); print_hex(ain, 32); printf("\n");
    printf("  reserve_in:  "); print_hex(rin, 32); printf("\n");
    printf("  reserve_out: "); print_hex(rout, 32); printf("\n\n");

    printf("Output Settlement (Single Execution Interface):\n");
    printf("  Status:      %ld (%s)\n", res.status, res.status == 1 ? "APPROVED" : "REJECTED");
    printf("  Steps VM:    %lu\n", res.steps_total);
    printf("  amount_out:  "); print_hex(res.amount_out, 32); printf("\n");

    uint64_t expected_out = 1662497915624478906ULL;
    uint8_t expected_be[32] = {0};
    for (int i = 0; i < 8; i++) {
        expected_be[31 - i] = (uint8_t)(expected_out >> (i * 8));
    }

    if (memcmp(res.amount_out, expected_be, 32) == 0) {
        printf("\n[PARIDADE SOLIDITY/EVM]: PASS (Bit-Exact: 1662497915624478906)\n");
    } else {
        printf("\n[PARIDADE SOLIDITY/EVM]: FAIL (Divergência detectada)\n");
        return 1;
    }

    printf("========================================================================\n");
    return 0;
}
