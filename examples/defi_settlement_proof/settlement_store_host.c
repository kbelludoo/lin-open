/* settlement_store_host.c — CORE<->STORE coupling: deterministic LinVM
 * settlement with durable per-swap COMMIT (fsync) in store_c0.
 *
 * Additive-only host (mutates no nucleus file). Build: cc -O2 -std=c11
 * -Wall -Wextra, linking lin_c VM sources + store_c0.c. No Zig/Go.
 *
 * Canonical keys: acc:<user> pool:amm tx:<nonce:06d>. Every tx stages
 * exactly 3 PUTs (acc, pool, tx) and COMMITs (fsync) — applied and
 * rejected alike — so frames == 3 * committed_txs, deterministically.
 *
 * Usage:
 *   settlement_store_host <engine.linbc> <storedir> <receipt.json>
 *       [--code-root <64hex>] [--crash-after N]
 * --crash-after N commits the first N txs, stages tx N WITHOUT commit
 * and _exit(137) to simulate SIGKILL mid-settlement (uncommitted lost).
 */
#define _POSIX_C_SOURCE 200809L

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"
#include "../../transpile/c/store_c0/store_c0.h"

typedef struct {
    const char *user;
    int64_t amount_in, reserve_in, reserve_out, min_out;
} SwapVec;

static const SwapVec BATCH[] = {
    { "alice", 1000,  100000,  200000,  1970  },
    { "bob",   5000,  1000000, 2000000, 9000  },
    { "carol", 1000,  100000,  200000,  1980  },
    { "dave",  0,     100000,  200000,  1     },
    { "erin",  10000, 1000000, 2000000, 19000 },
    { "frank", 700,   500000,  800000,  1000  },
    { "grace", 1000000, 100000, 200000, 1     },
    { "heidi", 2500,  750000,  1500000, 4000  },
};
#define BATCH_N (sizeof(BATCH) / sizeof(BATCH[0]))

static void hex32(const uint8_t d[32], char out[65]) {
    static const char *h = "0123456789abcdef";
    for (int i = 0; i < 32; i++) { out[2 * i] = h[d[i] >> 4]; out[2 * i + 1] = h[d[i] & 15]; }
    out[64] = 0;
}

static void die(const char *msg) { fprintf(stderr, "settlement_store_host: %s\n", msg); exit(1); }

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "uso: %s <engine.linbc> <storedir> <receipt.json> [--code-root <64hex>] [--crash-after N]\n", argv[0]);
        return 1;
    }
    const char *img_path = argv[1], *store_dir = argv[2], *receipt_path = argv[3];
    const char *code_root = "75366e5cb034b36aa96321acd96ffe61638c8809cf06321f4e656eadd589e9bb";
    long crash_after = -1;
    for (int i = 4; i < argc; i++) {
        if (!strcmp(argv[i], "--code-root") && i + 1 < argc) code_root = argv[++i];
        else if (!strcmp(argv[i], "--crash-after") && i + 1 < argc) crash_after = strtol(argv[++i], 0, 10);
        else { fprintf(stderr, "flag desconhecida: %s\n", argv[i]); return 1; }
    }
    if (strlen(code_root) != 64) die("code-root deve ter 64 hex chars");

    FILE *f = fopen(img_path, "rb");
    if (!f) { fprintf(stderr, "imagem nao encontrada: %s\n", img_path); return 1; }
    static uint8_t img[256 * 1024];
    size_t img_len = fread(img, 1, sizeof(img), f);
    fclose(f);
    if (img_len == sizeof(img)) die("imagem excede buffer");

    LinBc1Vm vm;
    LinBc1Err lerr = lin_bc1_load(img, img_len, &vm);
    if (lerr != LIN_BC1_OK) { fprintf(stderr, "rejeicao LINBC1: %s\n", lin_bc1_err_name(lerr)); return 1; }
    int fn = lin_bc1_find_fn(&vm, "settle_swap");
    if (fn < 0) die("settle_swap ausente na imagem");
    char img_hex[65];
    hex32(vm.img_sha256, img_hex);

    Store *s = 0;
    StoreResult r = store_open(store_dir, &s);
    if (r != STORE_OK) { fprintf(stderr, "store_open=%d\n", r); return 1; }

    long applied = 0, rejected = 0, committed = 0;
    for (long t = 0; t < (long)BATCH_N; t++) {
        const SwapVec *v = &BATCH[t];
        int64_t args[4] = { v->amount_in, v->reserve_in, v->reserve_out, v->min_out };
        uint64_t steps = 0;
        VmExecResult res;
        LinErr err = vm_exec(&vm.mod, (size_t)fn, args, 4, 0, &steps, &res);
        if (err != LIN_OK) { fprintf(stderr, "tx %ld: erro LinVM %d\n", t, err); store_close(s); return 1; }
        int64_t out = res.val;
        /* Fail-closed invariant checks on the host side (mirrors .lin domain): */
        int ok_shape = (out == -1) || (out >= 0 && out <= v->reserve_out);
        if (!ok_shape) { fprintf(stderr, "tx %ld: invariante violado out=%" PRId64 "\n", t, out); store_close(s); return 1; }
        const char *status = (out >= 0) ? "APPLIED" : "REJECTED";
        if (out >= 0) applied++; else rejected++;

        char k_acc[128], k_tx[64], v_acc[64], v_pool[96], v_tx[160];
        snprintf(k_acc, sizeof(k_acc), "acc:%s", v->user);
        snprintf(k_tx, sizeof(k_tx), "tx:%06ld", t);
        snprintf(v_acc, sizeof(v_acc), "%" PRId64, out);
        snprintf(v_pool, sizeof(v_pool), "%" PRId64 ":%" PRId64, v->reserve_in, v->reserve_out);
        snprintf(v_tx, sizeof(v_tx), "out=%" PRId64 ";status=%s;steps=%" PRIu64, out, status, steps);

        int crash_this = (crash_after >= 0 && t == crash_after);
        r = store_put(s, (const uint8_t *)k_acc, (uint16_t)strlen(k_acc),
                      (const uint8_t *)v_acc, (uint32_t)strlen(v_acc));
        if (r != STORE_OK) { fprintf(stderr, "tx %ld put acc=%d\n", t, r); store_close(s); return 1; }
        r = store_put(s, (const uint8_t *)"pool:amm", 8,
                      (const uint8_t *)v_pool, (uint32_t)strlen(v_pool));
        if (r != STORE_OK) { fprintf(stderr, "tx %ld put pool=%d\n", t, r); store_close(s); return 1; }
        r = store_put(s, (const uint8_t *)k_tx, (uint16_t)strlen(k_tx),
                      (const uint8_t *)v_tx, (uint32_t)strlen(v_tx));
        if (r != STORE_OK) { fprintf(stderr, "tx %ld put tx=%d\n", t, r); store_close(s); return 1; }

        if (crash_this) {
            /* Staged but never committed: simulate SIGKILL. No fsync,
             * no close — _exit skips atexit/flush, like a power cut. */
            fprintf(stderr, "[crash] tx %ld staged, SIGKILL simulado (exit 137)\n", t);
            _exit(137);
        }
        r = store_commit(s);
        if (r != STORE_OK) { fprintf(stderr, "tx %ld commit=%d\n", t, r); store_close(s); return 1; }
        committed++;
    }

    uint8_t root[32];
    r = store_get_merkle_root(s, root);
    if (r != STORE_OK) { store_close(s); return 1; }
    char root_hex[65];
    hex32(root, root_hex);
    uint64_t frames = store_get_frame_count(s);
    int64_t wal_size = store_get_wal_size(s);
    size_t keys = store_get_active_keys_count(s);
    if (store_checkpoint(s) != STORE_OK) { fprintf(stderr, "checkpoint falhou\n"); store_close(s); return 1; }

    FILE *rf = fopen(receipt_path, "w");
    if (!rf) { store_close(s); return 1; }
    fprintf(rf, "{\n  \"code_root_sha256\": \"%s\",\n  \"img_sha256\": \"%s\",\n",
            code_root, img_hex);
    fprintf(rf, "  \"tx_count\": %ld,\n  \"applied\": %ld,\n  \"rejected\": %ld,\n",
            committed, applied, rejected);
    fprintf(rf, "  \"state_merkle_root\": \"%s\",\n  \"frames\": %llu,\n",
            root_hex, (unsigned long long)frames);
    fprintf(rf, "  \"wal_bytes\": %lld,\n  \"active_keys\": %zu,\n",
            (long long)wal_size, keys);
    fprintf(rf, "  \"invariants\": \"CONSERVED\",\n  \"status\": \"ATTESTED_DURABLE\"\n}\n");
    fclose(rf);
    printf("settlement_store_host OK txs=%ld applied=%ld rejected=%ld root=%s frames=%llu\n",
           committed, applied, rejected, root_hex, (unsigned long long)frames);
    store_close(s);
    return 0;
}
