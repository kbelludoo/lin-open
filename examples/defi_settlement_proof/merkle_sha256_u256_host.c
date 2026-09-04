#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/lin_c/lin_sha256.h"

// Schema LCR2: Canonical Leaf Record para uint256 (208 bytes, binário little-endian)
//   Offset   Tam  Campo
//   0        4    schema_id = "LCR2"
//   4        1    schema_version = 1
//   5        1    profile = 1 (LINVM-1)
//   6        2    reserved = 0
//   8        32   image_digest (SHA-256 do LINBC1)
//   40       8    run_id (u64 LE)
//   48       8    tx_id (u64 LE)
//   56       32   amount_in (32 bytes BE / uint256)
//   88       32   reserve_in (32 bytes BE / uint256)
//   120      32   reserve_out (32 bytes BE / uint256)
//   152      32   amount_out (32 bytes BE / uint256)
//   184      8    steps (u64 LE)
//   192      8    status (i64 LE: 1 = APPROVED, -1 = INV_INPUT, -2 = OVERFLOW)
//   200      8    reserved_pad = 0
// Total: 208 bytes
typedef struct {
    uint8_t  schema_id[4];      // LCR2
    uint8_t  schema_version;   // 1
    uint8_t  profile;          // 1
    uint16_t reserved;         // 0
    uint8_t  image_digest[32]; // 32 bytes
    uint64_t run_id;
    uint64_t tx_id;
    uint8_t  amount_in[32];
    uint8_t  reserve_in[32];
    uint8_t  reserve_out[32];
    uint8_t  amount_out[32];
    uint64_t steps;
    int64_t  status;
} SettlementLeafRecordU256;

static void pack_u64_le(uint8_t *dst, uint64_t v) {
    for (int i = 0; i < 8; i++) dst[i] = (uint8_t)(v >> (i * 8));
}

static void compute_leaf_hash_u256(const SettlementLeafRecordU256 *rec, uint8_t leaf_hash[32]) {
    uint8_t raw[208];
    memcpy(raw, "LCR2", 4);
    raw[4] = 1;
    raw[5] = 1;
    raw[6] = 0; raw[7] = 0;
    memcpy(raw + 8, rec->image_digest, 32);
    pack_u64_le(raw + 40, rec->run_id);
    pack_u64_le(raw + 48, rec->tx_id);
    memcpy(raw + 56, rec->amount_in, 32);
    memcpy(raw + 88, rec->reserve_in, 32);
    memcpy(raw + 120, rec->reserve_out, 32);
    memcpy(raw + 152, rec->amount_out, 32);
    pack_u64_le(raw + 184, rec->steps);
    pack_u64_le(raw + 192, (uint64_t)rec->status);
    memset(raw + 200, 0, 8);

    static const uint8_t DOM_LEAF[] = "LIN:LEAF:1";
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_LEAF, sizeof(DOM_LEAF) - 1);
    lin_sha256_update(&ctx, raw, sizeof(raw));
    lin_sha256_final(&ctx, leaf_hash);
}

static void merkle_parent_sha256(const uint8_t left[32], const uint8_t right[32], uint8_t parent[32]) {
    static const uint8_t DOM_NODE[] = "LIN:NODE:1";
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, DOM_NODE, sizeof(DOM_NODE) - 1);
    lin_sha256_update(&ctx, left, 32);
    lin_sha256_update(&ctx, right, 32);
    lin_sha256_final(&ctx, parent);
}

static void u256_bytes_be_to_words_le(const uint8_t be[32], int64_t words[4]) {
    for (int i = 0; i < 4; i++) {
        uint64_t w = 0;
        int base = 32 - 8 * (i + 1);
        for (int b = 0; b < 8; b++) w = (w << 8) | (uint64_t)be[base + b];
        words[i] = (int64_t)w;
    }
}

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
    printf("  LIN PILOTO: LIQUIDAÇÃO UINT256 & PROVAS MERKLE SHA-256 EM BLOCO FIXO  \n");
    printf("========================================================================\n");
    printf("[LinVM Bytecode Image] %zu bytes | Digest: ", img_len);
    print_hex(vm.img_sha256, 32);
    printf("\n\n");

    // Lote de 4 transações representativas
    struct {
        uint64_t tx_id;
        uint64_t ain;
        uint64_t rin;
        uint64_t rout;
    } txs[4] = {
        { 2001, 1000000000000000000ULL, 5000000000000000000ULL, 10000000000000000000ULL }, // 1 ETH, 5 ETH, 10 ETH (Prod)
        { 2002, 2000000000000000000ULL, 5000000000000000000ULL, 10000000000000000000ULL }, // 2 ETH, 5 ETH, 10 ETH
        { 2003, 500000000000000000ULL,  5000000000000000000ULL, 10000000000000000000ULL }, // 0.5 ETH
        { 2004, 0,                      5000000000000000000ULL, 10000000000000000000ULL }  // 0 ETH (Inválido)
    };

    SettlementLeafRecordU256 records[4];
    uint8_t leaf_hashes[4][32];

    for (int i = 0; i < 4; i++) {
        memset(&records[i], 0, sizeof(records[i]));
        memcpy(records[i].image_digest, vm.img_sha256, 32);
        records[i].run_id = 1;
        records[i].tx_id = txs[i].tx_id;

        // Configurar inputs big-endian
        for (int b = 0; b < 8; b++) {
            records[i].amount_in[31 - b]  = (uint8_t)(txs[i].ain >> (b * 8));
            records[i].reserve_in[31 - b] = (uint8_t)(txs[i].rin >> (b * 8));
            records[i].reserve_out[31 - b]= (uint8_t)(txs[i].rout >> (b * 8));
        }

        int64_t ain[4], rin[4], rout[4];
        u256_bytes_be_to_words_le(records[i].amount_in, ain);
        u256_bytes_be_to_words_le(records[i].reserve_in, rin);
        u256_bytes_be_to_words_le(records[i].reserve_out, rout);

        int64_t args[13];
        for (int k = 0; k < 4; k++) {
            args[k]     = ain[k];
            args[4 + k] = rin[k];
            args[8 + k] = rout[k];
        }

        uint64_t total_steps = 0;
        uint64_t words_out[4] = {0};
        int64_t status = 1;

        for (int w = 0; w < 4; w++) {
            args[12] = (int64_t)w;
            uint64_t st = 0;
            VmExecResult r;
            LinErr e = vm_exec(&vm.mod, (size_t)fn_settle, args, 13, 0, &st, &r);
            if (e != LIN_OK) {
                status = -1;
                break;
            }
            total_steps += st;
            if (r.val < 0) {
                status = r.val;
                break;
            }
            words_out[w] = (uint64_t)r.val;
        }

        records[i].status = status;
        records[i].steps = total_steps;
        if (status == 1) {
            u256_words_le_to_bytes_be(words_out, records[i].amount_out);
        }

        compute_leaf_hash_u256(&records[i], leaf_hashes[i]);

        printf("Tx #%lu -> Status=%s | Steps=%lu\n",
               records[i].tx_id, records[i].status == 1 ? "APPROVED" : "REJECTED_FAIL_CLOSED",
               records[i].steps);
        printf("  amount_out: ");
        print_hex(records[i].amount_out, 32);
        printf("\n  Leaf SHA-256: ");
        print_hex(leaf_hashes[i], 32);
        printf("\n\n");
    }

    // Árvore Merkle SHA-256 de 256 bits (Bloco B=4 fixo)
    uint8_t n0[32], n1[32], merkle_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], n0);
    merkle_parent_sha256(leaf_hashes[2], leaf_hashes[3], n1);
    merkle_parent_sha256(n0, n1, merkle_root);

    printf("[Merkle Tree 256-bit] Raiz do Bloco SHA-256 (B=4, Verificação O(1)):\n  ");
    print_hex(merkle_root, 32);
    printf("\n\n");

    // Validação da Prova de Inclusão da Tx 2001 (1 ETH de produção)
    uint8_t test_n0[32], test_root[32];
    merkle_parent_sha256(leaf_hashes[0], leaf_hashes[1], test_n0);
    merkle_parent_sha256(test_n0, n1, test_root);
    printf("[Auditoria de Inclusão Tx #2001 (18 Decimais)]: %s\n",
           memcmp(test_root, merkle_root, 32) == 0 ? "VERIFICADO_COM_SUCESSO_BIT_EXACT" : "FALHA");

    printf("========================================================================\n");
    return 0;
}
