#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"

// Helper seguro para chamar uma função LinVM e obter o valor retornado
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

// Simula o processador de pagamentos de uma fintech existente
typedef struct {
    uint64_t id;
    int64_t  amount_cents;
    int64_t  tx_frequency_1h;
    int64_t  device_trust_score; // 0..100
} Transaction;

int main(void) {
    printf("========================================================================\n");
    printf("  FINTECH APP INTEGRADA COM MÓDULO VERIFICÁVEL LIN (LinVM C11 Host)     \n");
    printf("========================================================================\n\n");

    // 1. Carregar a imagem congelada compilada do LIN (.linbc)
    const char *img_path = "examples/integration_demo/risk_engine.linbc";
    FILE *f = fopen(img_path, "rb");
    if (!f) {
        fprintf(stderr, "Erro: não foi possível abrir a imagem LINBC1 '%s'\n", img_path);
        return 1;
    }

    uint8_t img_bytes[64 * 1024];
    size_t img_len = fread(img_bytes, 1, sizeof(img_bytes), f);
    fclose(f);

    printf("[Host] Imagem LINBC1 carregada com sucesso (%zu bytes lidos do disco).\n", img_len);

    // 2. Inicializar a LinVM com verificação estrita (fail-closed, sem malloc)
    LinBc1Vm vm;
    LinBc1Err err = lin_bc1_load(img_bytes, img_len, &vm);
    if (err != LIN_BC1_OK) {
        fprintf(stderr, "[Host] Rejeição LINBC1 estrita: %s\n", lin_bc1_err_name(err));
        return 1;
    }
    printf("[Host] Módulo LIN verificado com sucesso! SHA-256 e integridade: OK.\n\n");

    // 3. Localizar as funções no módulo compilado
    int fn_calc_risk  = lin_bc1_find_fn(&vm, "calc_risk_score");
    int fn_calc_fee   = lin_bc1_find_fn(&vm, "calc_fee_basis_points");
    int fn_is_blocked = lin_bc1_find_fn(&vm, "is_tx_blocked");

    if (fn_calc_risk < 0 || fn_calc_fee < 0 || fn_is_blocked < 0) {
        fprintf(stderr, "[Host] Erro: funções necessárias não encontradas no módulo LIN.\n");
        return 1;
    }

    // 4. Lote de transações do mundo real para avaliar
    Transaction txs[] = {
        { .id = 1001, .amount_cents = 12000, .tx_frequency_1h = 2,  .device_trust_score = 95 }, // Normal
        { .id = 1002, .amount_cents = 75000, .tx_frequency_1h = 4,  .device_trust_score = 60 }, // Valor alto
        { .id = 1003, .amount_cents = 98000, .tx_frequency_1h = 18, .device_trust_score = 25 }  // Suspeita / Fraude
    };
    size_t num_txs = sizeof(txs) / sizeof(txs[0]);

    for (size_t i = 0; i < num_txs; i++) {
        Transaction tx = txs[i];
        printf("--- Processando Transação #%lu (R$ %.2f) ---\n", tx.id, tx.amount_cents / 100.0);

        uint64_t steps_risk = 0, steps_fee = 0, steps_block = 0;

        // Chamar o motor de risco em LIN via LinVM:
        int64_t args_risk[3] = { tx.amount_cents, tx.tx_frequency_1h, tx.device_trust_score };
        int64_t risk_score = call_lin(&vm.mod, (size_t)fn_calc_risk, args_risk, 3, &steps_risk);

        // Chamar cálculo de taxa em LIN:
        int64_t args_fee[1] = { risk_score };
        int64_t fee_bps = call_lin(&vm.mod, (size_t)fn_calc_fee, args_fee, 1, &steps_fee);

        // Chamar verificação de bloqueio em LIN:
        int64_t args_block[1] = { risk_score };
        int64_t blocked = call_lin(&vm.mod, (size_t)fn_is_blocked, args_block, 1, &steps_block);

        printf("  > Score de Risco (LinVM) : %ld / 1000 (resolvido em %lu passos)\n", risk_score, steps_risk);
        printf("  > Taxa Aplicada (BPS)    : %ld bps (%.2f%%, resolvido em %lu passos)\n", fee_bps, fee_bps / 100.0, steps_fee);
        
        if (blocked) {
            printf("  > DECISÃO DE SEGURANÇA   : [BLOQUEADA - ALTO RISCO DE FRAUDE]\n\n");
        } else {
            printf("  > DECISÃO DE SEGURANÇA   : [APROVADA]\n\n");
        }
    }

    printf("========================================================================\n");
    printf("Conclusão:\n");
    printf(" - Zero Heap Allocations: arena fixa de memória, sem malloc, sem memory leaks.\n");
    printf(" - Imune a Buffer Overflow: verificação estrita de limites na LinVM.\n");
    printf(" - Determinismo Absoluto: contagem exata de passos (steps) auditáveis.\n");
    printf("========================================================================\n");
    return 0;
}
