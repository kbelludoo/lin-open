/*
 * examples/defi_settlement_proof/merkle_512_settler.c
 * Host C11 de Liquidação Uniswap v2 com Numerador de 512 bits e Árvore Merkle Nativa.
 * 
 * Propriedades:
 * 1. Interface Uniswap v2: Valores canônicos em uint256 (4 x 64-bit words).
 * 2. Álgebra Intermediária de 512 bits: Zero overflow em reservas da Mainnet.
 * 3. Blocos de Árvore Merkle de 512 bits: left (32B) || right (32B) = 64 bytes (512 bits),
 *    perfeitamente alinhados com o bloco de compressão FIPS 180-4 do SHA-256.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#include "../../transpile/c/lin_c/lin_sha256.h"

// Estrutura canônica de Swap Uniswap v2 (256 bits nas entradas e saídas)
typedef struct {
    uint64_t tx_id;
    uint64_t amount_in[4];    // uint256
    uint64_t reserve_in[4];   // uint256
    uint64_t reserve_out[4];  // uint256
    uint64_t amount_out[4];   // uint256 calculado
    int64_t  status;          // 1 = Aprovado, -1 = Entrada Inválida, -2 = Overflow
} UniswapV2SwapU512;

// Motor C11 de referência para simulação e benchmark acelerado (idêntico ao u512_uniswap_v2_core.lin)
int settle_u512_reference(
    const uint64_t amt_in[4],
    const uint64_t r_in[4],
    const uint64_t r_out[4],
    uint64_t out_val[4]
) {
    uint16_t amount[16] = {0};
    uint16_t reserve_in[16] = {0};
    uint16_t reserve_out[16] = {0};
    uint16_t fee_amount[16] = {0};
    uint16_t denominator[16] = {0};
    uint16_t remainder[16] = {0};
    uint16_t quotient[16] = {0};
    uint16_t numerator[32] = {0}; // 32 limbs de 16 bits = 512 BITS!

    // Desempacota 4 palavras de 64 bits em 16 limbs de 16 bits
    for (int w = 0; w < 4; w++) {
        for (int i = 0; i < 4; i++) {
            amount[w * 4 + i] = (uint16_t)((amt_in[w] >> (16 * i)) & 0xffff);
            reserve_in[w * 4 + i] = (uint16_t)((r_in[w] >> (16 * i)) & 0xffff);
            reserve_out[w * 4 + i] = (uint16_t)((r_out[w] >> (16 * i)) & 0xffff);
        }
    }

    // Checagem de zero
    if ((amt_in[0] | amt_in[1] | amt_in[2] | amt_in[3]) == 0) return -1;
    if ((r_in[0] | r_in[1] | r_in[2] | r_in[3]) == 0) return -1;
    if ((r_out[0] | r_out[1] | r_out[2] | r_out[3]) == 0) return -1;

    // 1. fee_amount = amount_in * 997
    uint32_t carry = 0;
    for (int i = 0; i < 16; i++) {
        uint32_t t = (uint32_t)amount[i] * 997 + carry;
        fee_amount[i] = (uint16_t)(t & 0xffff);
        carry = t >> 16;
    }
    if (carry != 0) return -2;

    // 2. denominator = reserve_in * 1000 + fee_amount
    carry = 0;
    for (int i = 0; i < 16; i++) {
        uint32_t t = (uint32_t)reserve_in[i] * 1000 + carry + fee_amount[i];
        denominator[i] = (uint16_t)(t & 0xffff);
        carry = t >> 16;
    }
    if (carry != 0) return -2;

    // 3. Numerador de 512 bits: fee_amount (16 limbs) * reserve_out (16 limbs) -> 32 limbs (512 bits)
    for (int i = 0; i < 16; i++) {
        carry = 0;
        for (int j = 0; j < 16; j++) {
            int k = i + j;
            uint64_t t = (uint64_t)numerator[k] + (uint64_t)fee_amount[i] * reserve_out[j] + carry;
            numerator[k] = (uint16_t)(t & 0xffff);
            carry = (uint32_t)(t >> 16);
        }
        int k = i + 16;
        while (k < 32 && carry != 0) {
            uint32_t t = (uint32_t)numerator[k] + carry;
            numerator[k] = (uint16_t)(t & 0xffff);
            carry = t >> 16;
            k++;
        }
    }

    // 4. Divisão restauradora de 512 bits por 256 bits: numerator (512b) / denominator (256b)
    for (int bit = 511; bit >= 0; bit--) {
        int limb = bit >> 4;
        int pos = bit & 15;
        uint16_t in_bit = (uint16_t)((numerator[limb] >> pos) & 1);

        // Desloca remainder à esquerda por 1 bit e insere in_bit
        carry = in_bit;
        for (int j = 0; j < 16; j++) {
            uint32_t t = (uint32_t)remainder[j] * 2 + carry;
            remainder[j] = (uint16_t)(t & 0xffff);
            carry = t >> 16;
        }

        // Compara remainder (16 limbs) com denominator (16 limbs)
        int cmp = 0;
        for (int j = 15; j >= 0; j--) {
            if (remainder[j] > denominator[j]) { cmp = 1; break; }
            else if (remainder[j] < denominator[j]) { cmp = -1; break; }
        }

        if (carry == 1 || cmp >= 0) {
            if (bit >= 256) return -2; // overflow do quociente além de 256 bits
            int qlimb = bit >> 4;
            quotient[qlimb] |= (uint16_t)(1 << pos);

            uint32_t borrow = 0;
            for (int j = 0; j < 16; j++) {
                int32_t t = (int32_t)remainder[j] - (int32_t)denominator[j] - (int32_t)borrow;
                if (t < 0) {
                    remainder[j] = (uint16_t)(t + 65536);
                    borrow = 1;
                } else {
                    remainder[j] = (uint16_t)t;
                    borrow = 0;
                }
            }
        }
    }

    // Empacota 16 limbs de volta em 4 palavras de 64 bits
    for (int w = 0; w < 4; w++) {
        out_val[w] = (uint64_t)quotient[w * 4] |
                     ((uint64_t)quotient[w * 4 + 1] << 16) |
                     ((uint64_t)quotient[w * 4 + 2] << 32) |
                     ((uint64_t)quotient[w * 4 + 3] << 48);
    }
    return 1;
}

// Hashing de Folha Canônica de 64 bytes (512 bits)
static void compute_swap_leaf(const UniswapV2SwapU512 *swap, uint8_t leaf_out[32]) {
    uint8_t buffer[64];
    // Empacota tx_id (8B), status (8B), out_val words 0..1 (16B), words 2..3 (16B), amount_in w0..1 (16B)
    memcpy(buffer, &swap->tx_id, 8);
    memcpy(buffer + 8, &swap->status, 8);
    memcpy(buffer + 16, &swap->amount_out[0], 16);
    memcpy(buffer + 32, &swap->amount_out[2], 16);
    memcpy(buffer + 48, &swap->amount_in[0], 16);

    lin_sha256(buffer, 64, leaf_out);
}

// Combinação de Nós da Árvore Merkle: Nó Esquerdo (32B) || Nó Direito (32B) = 64 Bytes (512 BITS!)
static void compute_merkle_parent_512(const uint8_t left[32], const uint8_t right[32], uint8_t parent_out[32]) {
    uint8_t block_512[64]; // Exatamente 512 bits!
    memcpy(block_512, left, 32);
    memcpy(block_512 + 32, right, 32);
    lin_sha256(block_512, 64, parent_out);
}

// Constrói Árvore Merkle sobre um lote de N swaps
void compute_batch_merkle_root(const UniswapV2SwapU512 *swaps, size_t count, uint8_t root_out[32]) {
    if (count == 0) {
        memset(root_out, 0, 32);
        return;
    }

    uint8_t *nodes = (uint8_t *)malloc(count * 32);
    for (size_t i = 0; i < count; i++) {
        compute_swap_leaf(&swaps[i], nodes + i * 32);
    }

    size_t current_count = count;
    while (current_count > 1) {
        size_t next_count = (current_count + 1) / 2;
        for (size_t i = 0; i < current_count; i += 2) {
            size_t left_idx = i;
            size_t right_idx = (i + 1 < current_count) ? (i + 1) : i;
            compute_merkle_parent_512(
                nodes + left_idx * 32,
                nodes + right_idx * 32,
                nodes + (i / 2) * 32
            );
        }
        current_count = next_count;
    }

    memcpy(root_out, nodes, 32);
    free(nodes);
}

int main(int argc, char **argv) {
    size_t batch_size = 1000;
    if (argc > 1) {
        batch_size = (size_t)atoi(argv[1]);
        if (batch_size == 0) batch_size = 1000;
    }

    printf("=== LIN UNISWAP V2 512-BIT ACCELERATED SETTLEMENT ENGINE ===\n");
    printf("Configuração: Lote de %zu swaps com numerador intermediário u512\n", batch_size);
    printf("Blocos Merkle: Nós empacotados em chunks nativos de 512 bits (64 bytes)\n\n");

    UniswapV2SwapU512 *swaps = (UniswapV2SwapU512 *)calloc(batch_size, sizeof(UniswapV2SwapU512));
    if (!swaps) {
        fprintf(stderr, "Erro de alocação de memória.\n");
        return 1;
    }

    // Configura swaps com reservas reais da Mainnet (18 decimais)
    // Exemplo: 10 ETH in (10e18), Reserva In: 10.000 ETH, Reserva Out: 30.000.000 USDC
    // Palavras 64-bit little-endian:
    for (size_t i = 0; i < batch_size; i++) {
        swaps[i].tx_id = (uint64_t)(i + 1);
        // amount_in = 10 * 10^18 + i
        swaps[i].amount_in[0] = 10000000000000000000ULL + i;
        swaps[i].amount_in[1] = 0;
        swaps[i].amount_in[2] = 0;
        swaps[i].amount_in[3] = 0;

        // reserve_in = 10.000 * 10^18
        swaps[i].reserve_in[0] = 1864712049423024128ULL;
        swaps[i].reserve_in[1] = 542ULL;
        swaps[i].reserve_in[2] = 0;
        swaps[i].reserve_in[3] = 0;

        // reserve_out = 30.000.000 * 10^18
        swaps[i].reserve_out[0] = 4772693935078244352ULL;
        swaps[i].reserve_out[1] = 1626303ULL;
        swaps[i].reserve_out[2] = 0;
        swaps[i].reserve_out[3] = 0;
    }

    // Execução do lote
    clock_t t0 = clock();
    size_t approved = 0;
    for (size_t i = 0; i < batch_size; i++) {
        int status = settle_u512_reference(
            swaps[i].amount_in,
            swaps[i].reserve_in,
            swaps[i].reserve_out,
            swaps[i].amount_out
        );
        swaps[i].status = status;
        if (status == 1) approved++;
    }
    clock_t t1 = clock();
    double time_eval_ms = ((double)(t1 - t0) / CLOCKS_PER_SEC) * 1000.0;

    // Construção da Árvore Merkle com blocos de 512 bits
    clock_t t2 = clock();
    uint8_t root[32];
    compute_batch_merkle_root(swaps, batch_size, root);
    clock_t t3 = clock();
    double time_merkle_ms = ((double)(t3 - t2) / CLOCKS_PER_SEC) * 1000.0;

    char hex_root[65];
    lin_sha256_hex(root, hex_root);

    printf("RESULTADO DO PROCESSAMENTO:\n");
    printf("  • Swaps Processados com Sucesso: %zu / %zu\n", approved, batch_size);
    printf("  • Tempo de Execução Aritmética (u512): %.2f ms (%.3f µs/swap)\n", time_eval_ms, (time_eval_ms * 1000.0) / batch_size);
    printf("  • Tempo de Construção Merkle (512-bit blocks): %.2f ms (%.3f µs/swap)\n", time_merkle_ms, (time_merkle_ms * 1000.0) / batch_size);
    printf("  • Throughput Efetivo: %.0f swaps/segundo\n", (double)batch_size / ((time_eval_ms + time_merkle_ms) / 1000.0));
    printf("  • Raiz Merkle Canônica (256-bit): sha256:%s\n", hex_root);
    printf("  • Exemplo Swap #1: In = 10 ETH -> Out = (0x%016llx, 0x%016llx) = 29.880 USDC\n\n",
           (unsigned long long)swaps[0].amount_out[0],
           (unsigned long long)swaps[0].amount_out[1]);

    free(swaps);
    return 0;
}
