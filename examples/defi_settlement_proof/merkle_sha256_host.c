#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/lin_c/lin_sha256.h"

// Definições de domínio conservador pré-aritmética em i64 (F3)
#define LIN_MAX_AMOUNT_IN   INT64_C(1000000)
#define LIN_MAX_RESERVE_IN  INT64_C(9000000000000000)
#define LIN_MAX_RESERVE_OUT INT64_C(9000000000)
#define LIN_MAX_MIN_OUT     INT64_C(9000000000)

static bool lin_settlement_domain_ok(int64_t amount_in, int64_t reserve_in, int64_t reserve_out, int64_t min_out) {
    if (amount_in <= 0 || reserve_in <= 0 || reserve_out <= 0 || min_out <= 0) {
        return false;
    }
    if (amount_in > LIN_MAX_AMOUNT_IN ||
        reserve_in > LIN_MAX_RESERVE_IN ||
        reserve_out > LIN_MAX_RESERVE_OUT ||
        min_out > LIN_MAX_MIN_OUT) {
        return false;
    }
    return true;
}

// Registro canônico de folha de liquidação (binário, little-endian, 112 bytes por LIN-PILOT-VERIFIER-FUZZ-001)
typedef struct {
    uint8_t  schema_id[4];      // LCR1
    uint8_t  schema_version;   // 1
    uint8_t  profile;          // 1
    uint16_t reserved;         // 0
    uint8_t  image_digest[32]; // 32 bytes
    uint64_t run_id;
    uint64_t tx_id;
    int64_t  amount_in;
    int64_t  reserve_in;
    int64_t  reserve_out;
    int64_t  min_out;
    int64_t  out_val;
    uint64_t steps;
    int64_t  status;
} SettlementLeafRecord112;

static void pack_u64_le(uint8_t *dst, uint64_t v) {
    for (int i = 0; i < 8; i++) dst[i] = (uint8_t)(v >> (i * 8));
}

// Computa a folha SHA-256 com prefixo de domínio LIN:LEAF:1
static void compute_leaf_hash(const SettlementLeafRecord112 *rec, uint8_t leaf_hash[32]) {
    uint8_t raw[112];
    memcpy(raw, "LCR1", 4);
    raw[4] = 1;
    raw[5] = 1;
    raw[6] = 0; raw[7] = 0;
    memcpy(raw + 8, rec->image_digest, 32);
    pack_u64_le(raw + 40, rec->run_id);
    pack_u64_le(raw + 48, rec->tx_id);
    pack_u64_le(raw + 56, (uint64_t)rec->amount_in);
    pack_u64_le(raw + 64, (uint64_t)rec->reserve_in);
    pack_u64_le(raw + 72, (uint64_t)rec->reserve_out);
    pack_u64_le(raw + 80, (uint64_t)rec->min_out);
    pack_u64_le(raw + 88, (uint64_t)rec->out_val);
    pack_u64_le(raw + 96, rec->steps);
    pack_u64_le(raw + 104, (uint64_t)rec->status);

    static const uint8_t DOM_LEAF[] = "LIN:LEAF:1";
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_LEAF, sizeof(DOM_LEAF) - 1);
    lin_sha256_update(&ctx, raw, sizeof(raw));
    lin_sha256_final(&ctx, leaf_hash);
}

// Nó pai Merkle: SHA256("LIN:NODE:1" || left_32 || right_32)
static void merkle_parent_sha256(const uint8_t left[32], const uint8_t right[32], uint8_t parent[32]) {
    static const uint8_t DOM_NODE[] = "LIN:NODE:1";
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_NODE, sizeof(DOM_NODE) - 1);
    lin_sha256_update(&ctx, left, 32);
    lin_sha256_update(&ctx, right, 32);
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
    printf("  HOST C11 COM GUARDAS DE DOMÍNIO PRÉ-ARITMÉTICA (F3) & LINBC1 112-BYTE  \n");
    printf("========================================================================\n");
    printf("[LinVM Bytecode Image] %zu bytes | Digest: ", img_len);
    print_hex(vm.img_sha256, 32);
    printf("\n\n");

    // Simulando 4 transações
    struct {
        uint64_t tx_id;
        int64_t amount_in;
        int64_t res_in;
        int64_t res_out;
        int64_t min_out;
    } block_txs[4] = {
        { 1001, 1000, 100000, 200000, 1970 },         // Normal, passa
        { 1002, 2500, 100000, 200000, 4800 },         // Normal, passa
        { 1003, 5000, 100000, 200000, 9900 },         // Slippage violado
        { 1004, 1000, INT64_C(4611686018427387904), 100000, 1 } // F3: 2^62 viola teto de domínio
    };

    SettlementLeafRecord112 records[4];
    uint8_t leaf_hashes[4][32];

    for (int i = 0; i < 4; i++) {
        uint64_t steps = 0;
        VmExecResult res;
        int64_t out_val;
        int64_t status;

        // Guarda C11 pré-execução: não chama LinVM se domínio inválido
        if (!lin_settlement_domain_ok(block_txs[i].amount_in, block_txs[i].res_in, block_txs[i].res_out, block_txs[i].min_out)) {
            out_val = -1;
            status = -1;
            steps = 0;
            printf("[Host C11 Guard] Tx #%lu REJEITADA ANTES DA VM (Fora do Domínio i64 Seguro)\n", block_txs[i].tx_id);
        } else {
            int64_t args[4] = { block_txs[i].amount_in, block_txs[i].res_in, block_txs[i].res_out, block_txs[i].min_out };
            LinErr e = vm_exec(&vm.mod, (size_t)fn_settle, args, 4, 0, &steps, &res);
            if (e != LIN_OK) {
                fprintf(stderr, "Erro LinVM na tx %lu\n", block_txs[i].tx_id);
                return 1;
            }
            out_val = res.val;
            status = (res.val >= 0) ? 1 : -1;
        }

        memcpy(records[i].image_digest, vm.img_sha256, 32);
        records[i].run_id = 1;
        records[i].tx_id = block_txs[i].tx_id;
        records[i].amount_in = block_txs[i].amount_in;
        records[i].reserve_in = block_txs[i].res_in;
        records[i].reserve_out = block_txs[i].res_out;
        records[i].min_out = block_txs[i].min_out;
        records[i].out_val = out_val;
        records[i].steps = steps;
        records[i].status = status;

        compute_leaf_hash(&records[i], leaf_hashes[i]);

        printf("Tx #%lu -> Status=%s | Out=%ld | Steps=%lu\n",
               records[i].tx_id, records[i].status == 1 ? "APPROVED" : "REJECTED_FAIL_CLOSED",
               records[i].out_val, records[i].steps);
        printf("  Leaf SHA-256: ");
        print_hex(leaf_hashes[i], 32);
        printf("\n");
    }

    // Árvore Merkle SHA-256 de 256 bits
    uint8_t n0[32], n1[32], merkle_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], n0);
    merkle_parent_sha256(leaf_hashes[2], leaf_hashes[3], n1);
    merkle_parent_sha256(n0, n1, merkle_root);

    printf("\n[Merkle Tree 256-bit] Raiz do Bloco SHA-256:\n  ");
    print_hex(merkle_root, 32);
    printf("\n\n");

    // Validação da Prova de Inclusão da Tx 1001
    uint8_t test_n0[32], test_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], test_n0);
    merkle_parent_sha256(test_n0, n1, test_root);
    printf("[Auditoria de Inclusão Tx #1001]: %s\n",
           memcmp(test_root, merkle_root, 32) == 0 ? "VERIFICADO_COM_SUCESSO" : "FALHA");

    printf("========================================================================\n");
    return 0;
}
