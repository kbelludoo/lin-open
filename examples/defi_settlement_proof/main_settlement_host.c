#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"

// Helper para executar função no LinVM C11
static int64_t call_lin(const VmModule *mod, size_t fn_idx, const int64_t *args, size_t n_args, uint64_t *steps_out) {
    uint64_t steps = 0;
    VmExecResult res;
    LinErr err = vm_exec(mod, fn_idx, args, n_args, 0, &steps, &res);
    if (err != LIN_OK) {
        fprintf(stderr, "Erro de execução na LinVM (code=%d)\n", err);
        return -1;
    }
    if (steps_out) *steps_out = steps;
    return res.val;
}

int main(int argc, char **argv) {
    const char *img_path = "examples/defi_settlement_proof/settlement_engine.linbc";
    if (argc > 1) {
        img_path = argv[1];
    }

    FILE *f = fopen(img_path, "rb");
    if (!f) {
        fprintf(stderr, "Erro: imagem nao encontrada: %s\n", img_path);
        return 1;
    }

    uint8_t img_bytes[64 * 1024];
    size_t img_len = fread(img_bytes, 1, sizeof(img_bytes), f);
    fclose(f);

    LinBc1Vm vm;
    LinBc1Err err = lin_bc1_load(img_bytes, img_len, &vm);
    if (err != LIN_BC1_OK) {
        fprintf(stderr, "[Host C11] Rejeicao LINBC1: %s\n", lin_bc1_err_name(err));
        return 1;
    }

    int fn_settle = lin_bc1_find_fn(&vm, "settle_swap");
    int fn_verify_merkle = lin_bc1_find_fn(&vm, "verify_merkle_branch_2");
    if (fn_settle < 0 || fn_verify_merkle < 0) {
        fprintf(stderr, "Erro: funcoes necessarias ausentes na imagem bytecode LINBC1\n");
        return 1;
    }

    printf("========================================================================\n");
    printf("  DEFI SETTLEMENT ENGINE C11 HOST - EXECUTANDO BYTECODE LINBC1          \n");
    printf("========================================================================\n");
    printf("[Bytecode] Imagem carregada: %s (%zu bytes)\n", img_path, img_len);
    printf("[Bytecode] Hash SHA-256 verificado pelo loader: ");
    for (int i = 0; i < 32; i++) printf("%02x", vm.img_sha256[i]);
    printf("\n\n");

    // Cenário 1: Swap Aceito
    uint64_t steps = 0;
    int64_t args_pass[4] = { 1000, 100000, 200000, 1970 };
    int64_t out_pass = call_lin(&vm.mod, (size_t)fn_settle, args_pass, 4, &steps);
    printf("[Cenario 1 - Swap Regular]\n");
    printf("  Entrada: 1000 tokens | ReservaIn: 100000 | ReservaOut: 200000 | MinOut: 1970\n");
    printf("  Resultado da LinVM: %ld tokens (passos: %lu)\n", out_pass, steps);
    printf("  Status: %s\n\n", out_pass >= 1970 ? "APROVADO & LIQUIDADO" : "FALHA");

    // Cenário 2: Swap Rejeitado por Slippage (Fail-Closed)
    int64_t args_fail[4] = { 1000, 100000, 200000, 1980 };
    int64_t out_fail = call_lin(&vm.mod, (size_t)fn_settle, args_fail, 4, &steps);
    printf("[Cenario 2 - Protecao Slippage / Front-Running / MEV]\n");
    printf("  Entrada: 1000 tokens | ReservaIn: 100000 | ReservaOut: 200000 | MinOut: 1980\n");
    printf("  Resultado da LinVM: %ld tokens (passos: %lu)\n", out_fail, steps);
    printf("  Status: %s\n\n", out_fail == -1 ? "REJEITADO COM SUCESSO (FAIL-CLOSED)" : "ERRO");

    printf("========================================================================\n");
    printf("Execucao 100%% concluida a partir de imagem compilada LINBC1.\n");
    printf("========================================================================\n");
    return 0;
}
