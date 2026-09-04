#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/lin_c/lin_sha256.h"

// Registro canônico de folha de liquidação (binário, little-endian, 72 bytes)
// Cobre:
//  0..31: image_sha256 (32 bytes do bytecode executado)
// 32..39: tx_id (u64 LE)
// 40..47: amount_in (u64 LE)
// 48..55: out_val (i64 LE)
// 56..63: steps (u64 LE)
// 64..71: status_code (i64 LE, ex: 1 = aprovado, -1 = slippage_reject)
typedef struct {
    uint8_t image_sha256[32];
    uint64_t tx_id;
    uint64_t amount_in;
    int64_t  out_val;
    uint64_t steps;
    int64_t  status;
} SettlementLeafRecord;

static void pack_u64_le(uint8_t *dst, uint64_t v) {
    for (int i = 0; i < 8; i++) {
        dst[i] = (uint8_t)(v >> (i * 8));
    }
}

// Computa a folha SHA-256 canônica (FIPS 180-4) sobre o registro
static void compute_leaf_hash(const SettlementLeafRecord *rec, uint8_t leaf_hash[32]) {
    uint8_t raw[72];
    memcpy(raw, rec->image_sha256, 32);
    pack_u64_le(raw + 32, rec->tx_id);
    pack_u64_le(raw + 40, rec->amount_in);
    pack_u64_le(raw + 48, (uint64_t)rec->out_val);
    pack_u64_le(raw + 56, rec->steps);
    pack_u64_le(raw + 64, (uint64_t)rec->status);

    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, raw, sizeof(raw));
    lin_sha256_final(&ctx, leaf_hash);
}

// Nó pai Merkle padrão: SHA256(left_32 || right_32)
static void merkle_parent_sha256(const uint8_t left[32], const uint8_t right[32], uint8_t parent[32]) {
    uint8_t combined[64];
    memcpy(combined, left, 32);
    memcpy(combined + 32, right, 32);

    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, combined, sizeof(combined));
    lin_sha256_final(&ctx, parent);
}

static void print_hex(const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; i++) printf("%02x", data[i]);
}

int main(void) {
    const char *img_path = "examples/defi_settlement_proof/settlement_engine.linbc";
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

    int fn_settle = lin_bc1_find_fn(&vm, "settle_swap");
    if (fn_settle < 0) {
        fprintf(stderr, "Função settle_swap ausente\n");
        return 1;
    }

    printf("========================================================================\n");
    printf("  CAMINHO 1: LIQUIDAÇÃO LINBC1 + ÁRVORE MERKLE SHA-256 REAL (FIPS 180-4)\n");
    printf("========================================================================\n");
    printf("[LinVM Bytecode Image] %zu bytes | Digest: ", img_len);
    print_hex(vm.img_sha256, 32);
    printf("\n\n");

    // Simulando um bloco de 4 transações liquidadas na LinVM
    struct {
        uint64_t tx_id;
        int64_t amount_in;
        int64_t res_in;
        int64_t res_out;
        int64_t min_out;
    } block_txs[4] = {
        { 1001, 1000, 100000, 200000, 1970 }, // Passa
        { 1002, 2500, 100000, 200000, 4800 }, // Passa
        { 1003, 5000, 100000, 200000, 9900 }, // Slippage violado (rejeição)
        { 1004, 1200, 150000, 300000, 2300 }  // Passa
    };

    SettlementLeafRecord records[4];
    uint8_t leaf_hashes[4][32];

    for (int i = 0; i < 4; i++) {
        uint64_t steps = 0;
        VmExecResult res;
        int64_t args[4] = { block_txs[i].amount_in, block_txs[i].res_in, block_txs[i].res_out, block_txs[i].min_out };
        LinErr e = vm_exec(&vm.mod, (size_t)fn_settle, args, 4, 0, &steps, &res);
        if (e != LIN_OK) {
            fprintf(stderr, "Erro LinVM na tx %lu\n", block_txs[i].tx_id);
            return 1;
        }

        memcpy(records[i].image_sha256, vm.img_sha256, 32);
        records[i].tx_id = block_txs[i].tx_id;
        records[i].amount_in = block_txs[i].amount_in;
        records[i].out_val = res.val;
        records[i].steps = steps;
        records[i].status = (res.val >= 0) ? 1 : -1;

        compute_leaf_hash(&records[i], leaf_hashes[i]);

        printf("Tx #%lu -> Status=%s | Out=%ld | Steps=%lu\n",
               records[i].tx_id, records[i].status == 1 ? "APPROVED" : "REJECTED_SLIPPAGE",
               records[i].out_val, records[i].steps);
        printf("  Leaf SHA-256: ");
        print_hex(leaf_hashes[i], 32);
        printf("\n");
    }

    // Construção da Árvore Merkle SHA-256 de 256 bits real:
    //      Root (256-bit)
    /*     /              \ */
    //   N0 (256-bit)    N1 (256-bit)
    /*   /        \       /        \ */
    // Leaf0    Leaf1   Leaf2     Leaf3
    uint8_t n0[32], n1[32], merkle_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], n0);
    merkle_parent_sha256(leaf_hashes[2], leaf_hashes[3], n1);
    merkle_parent_sha256(n0, n1, merkle_root);

    printf("\n------------------------------------------------------------------------\n");
    printf("[Merkle Tree 256-bit] Raiz do Bloco SHA-256:\n  ");
    print_hex(merkle_root, 32);
    printf("\n------------------------------------------------------------------------\n\n");

    // Validação de Prova de Inclusão da Tx #1001 (Leaf0)
    // Caminho: sibling0 = Leaf1, sibling1 = N1
    printf("[Auditoria de Inclusão Independente (Tx #1001)]\n");
    uint8_t test_n0[32], test_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], test_n0);
    merkle_parent_sha256(test_n0, n1, test_root);
    printf("  Raiz Recalculada pela Prova: ");
    print_hex(test_root, 32);
    printf("\n  Status da Prova de Inclusão: %s\n\n",
           memcmp(test_root, merkle_root, 32) == 0 ? "VERIFICADO_COM_SUCESSO" : "FALHA");

    // Teste de Adulteração: atacante tenta mudar 1 unidade no valor de saída da Tx #1001
    printf("[Simulação de Ataque de Adulteração (1 unidade fraudada na Tx #1001)]\n");
    SettlementLeafRecord fraud_rec = records[0];
    fraud_rec.out_val -= 1; // Fraude
    uint8_t fraud_leaf[32], fraud_n0[32], fraud_root[32];
    compute_leaf_hash(&fraud_rec, fraud_leaf);
    merkle_parent_sha256(fraud_leaf, leaf_hashes[1], fraud_n0);
    merkle_parent_sha256(fraud_n0, n1, fraud_root);

    printf("  Raiz Gerada com Adulteração: ");
    print_hex(fraud_root, 32);
    printf("\n  Detecção de Fraude: %s (Raiz divergente rejeitada)\n",
           memcmp(fraud_root, merkle_root, 32) != 0 ? "FRAUDE_DETECTADA_E_BARRADA (100%)" : "FALHA_NA_DETECCAO");

    printf("========================================================================\n");
    return 0;
}
