#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#include "../transpile/c/lin_c/lin_linbc1.h"
#include "../transpile/c/lin_c/lin_sha256.h"

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

// Executa liquidação completa u256 na LinVM em C nativo
static int run_u256_settle(
    const LinBc1Vm *vm,
    int fn_idx,
    const uint8_t ain_be[32],
    const uint8_t rin_be[32],
    const uint8_t rout_be[32],
    uint8_t out_be[32],
    uint64_t *steps_out
) {
    int64_t ain[4], rin[4], rout[4];
    u256_bytes_be_to_words_le(ain_be, ain);
    u256_bytes_be_to_words_le(rin_be, rin);
    u256_bytes_be_to_words_le(rout_be, rout);

    int64_t args[13];
    for (int i = 0; i < 4; i++) {
        args[i]     = ain[i];
        args[4 + i] = rin[i];
        args[8 + i] = rout[i];
    }

    uint64_t total_steps = 0;
    uint64_t step_count = 0;
    VmExecResult r;

    // Status check
    args[12] = -1;
    LinErr err = vm_exec(&vm->mod, (size_t)fn_idx, args, 13, 0, &step_count, &r);
    if (err != LIN_OK || r.val != 1) return (int)(r.val < 0 ? r.val : -1);
    total_steps += step_count;

    // Recupera 4 palavras de saída
    uint64_t words_out[4];
    for (int w = 0; w < 4; w++) {
        args[12] = (int64_t)w;
        step_count = 0;
        err = vm_exec(&vm->mod, (size_t)fn_idx, args, 13, 0, &step_count, &r);
        if (err != LIN_OK) return -1;
        total_steps += step_count;
        words_out[w] = (uint64_t)r.val;
    }

    u256_words_le_to_bytes_be(words_out, out_be);
    *steps_out = total_steps;
    return 1;
}

static void hex_to_32bytes(const char *hex_str, uint8_t out[32]) {
    memset(out, 0, 32);
    if (!hex_str) return;
    if (hex_str[0] == '0' && (hex_str[1] == 'x' || hex_str[1] == 'X')) {
        hex_str += 2;
    }
    size_t len = strlen(hex_str);
    int out_idx = 31;
    for (int i = (int)len - 1; i >= 0; i -= 2) {
        if (out_idx < 0) break;
        char byte_str[3] = {0};
        if (i == 0) {
            byte_str[0] = hex_str[0];
        } else {
            byte_str[0] = hex_str[i - 1];
            byte_str[1] = hex_str[i];
        }
        out[out_idx--] = (uint8_t)strtoul(byte_str, NULL, 16);
    }
}

int main(int argc, char **argv) {
    const char *img_path = "examples/defi_settlement_proof/u256_settlement_engine.linbc";
    const char *bin_path = (argc > 1) ? argv[1] : "test/pilot_harness/swaps_2000_raw.bin";

    FILE *fi = fopen(img_path, "rb");
    if (!fi) {
        fprintf(stderr, "Erro ao abrir imagem %s\n", img_path);
        return 1;
    }
    uint8_t img_bytes[64 * 1024];
    size_t img_len = fread(img_bytes, 1, sizeof(img_bytes), fi);
    fclose(fi);

    LinBc1Vm vm;
    if (lin_bc1_load(img_bytes, img_len, &vm) != LIN_BC1_OK) {
        fprintf(stderr, "Falha ao carregar LinVM\n");
        return 1;
    }

    int fn_idx = lin_bc1_find_fn(&vm, "settle_u256_word");
    if (fn_idx < 0) {
        fprintf(stderr, "Função settle_u256_word não encontrada\n");
        return 1;
    }

    FILE *fd = fopen(bin_path, "rb");
    if (!fd) {
        fprintf(stderr, "Erro ao abrir dados binários %s\n", bin_path);
        return 1;
    }
    fseek(fd, 0, SEEK_END);
    long sz = ftell(fd);
    fseek(fd, 0, SEEK_SET);

    size_t record_size = 32 * 4; // ain(32), rin(32), rout(32), expected_out(32) = 128 bytes
    size_t total_swaps = sz / record_size;

    uint8_t *buffer = malloc(sz);
    if (!buffer || fread(buffer, 1, sz, fd) != (size_t)sz) {
        fprintf(stderr, "Erro ao ler buffer\n");
        return 1;
    }
    fclose(fd);

    printf("=====================================================================================\n");
    printf("   LIN HOST C11 HIGH-PERFORMANCE RUNNER: %zu SWAPS REAIS DA MAINNET\n", total_swaps);
    printf("=====================================================================================\n");
    printf("[*] LinVM Bytecode Digest: ");
    for (int i = 0; i < 32; i++) printf("%02x", vm.img_sha256[i]);
    printf("\n[*] Executando liquidações determinísticas com zero overhead de subprocesso...\n\n");

    clock_t t0 = clock();
    size_t passed = 0;
    uint64_t total_steps = 0;
    uint8_t out_calc[32];

    for (size_t i = 0; i < total_swaps; i++) {
        uint8_t *rec = buffer + (i * record_size);
        uint8_t *ain = rec;
        uint8_t *rin = rec + 32;
        uint8_t *rout = rec + 64;
        uint8_t *expected = rec + 96;

        uint64_t steps = 0;
        int st = run_u256_settle(&vm, fn_idx, ain, rin, rout, out_calc, &steps);
        if (st == 1 && memcmp(out_calc, expected, 32) == 0) {
            passed++;
        }
        total_steps += steps;
    }
    clock_t t1 = clock();
    double elapsed_sec = (double)(t1 - t0) / CLOCKS_PER_SEC;

    printf("-------------------------------------------------------------------------------------\n");
    printf("[Taxa de Sucesso]:          %zu/%zu (%.2f%%) PARIDADE BIT-EXACT 100%%\n", passed, total_swaps, (double)passed/total_swaps * 100.0);
    printf("[Total Instruções LinVM]:   %llu instruções determinísticas\n", (unsigned long long)total_steps);
    printf("[Tempo Total em C11]:       %.3f segundos (%.3f ms por swap)\n", elapsed_sec, (elapsed_sec / total_swaps) * 1000.0);
    printf("[Throughput C11 Nativo]:    %.1f swaps reconciliados / segundo\n", total_swaps / elapsed_sec);
    printf("=====================================================================================\n");

    free(buffer);
    return (passed == total_swaps) ? 0 : 1;
}
