/*
 * verify_batch_c.c — Auditor independente (C11) do lote de liquidação v2.
 *
 * Prova três coisas SEM depender do Python:
 *   1. "Qualquer implementação SHA-256 padrão pode auditar": recalcula folhas,
 *      provas, raízes por bloco e a raiz encadeada do lote a partir dos campos
 *      brutos, usando apenas SHA-256 (lin_sha256.c, FIPS 180-4), e compara
 *      bit-exact com o compromisso emitido pelo Python/hashlib.
 *   2. "Verificar é mais barato que reexecutar": mede ns/prova vs
 *      ns/execução-na-VM (mesma linguagem, mesma máquina, sem spawn de
 *      processo), executando settle_swap in-process na imagem LINBC1.
 *   3. Paridade Uniswap V2 + contagem de passos idêntica aos recibos.
 *
 * Entrada: batch.bin (formato canônico little-endian escrito pelo benchmark v2)
 *          + caminho da imagem .linbc.
 * Saída: linhas "CVER chave=valor" parseáveis pelo benchmark v2.
 *
 * Formato batch.bin:
 *   magic "LINV2B1" (7 bytes) | u8 version=1
 *   u32 n_blocks
 *   u8[32] image_file_sha256
 *   por bloco, 4 registros:
 *     i64 tx_id, amount_in, reserve_in, reserve_out, min_out, out, steps
 *     u8  path_bits
 *     u8[32] leaf, s0, s1
 *   por bloco: u8[32] root
 *   final: u8[32] batch_root
 *
 * Compilação: cc -O3 -std=c11 -Wall -Wextra (sem dependências externas).
 */
#define _POSIX_C_SOURCE 199309L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "lin_sha256.h"
#include "lin_linbc1.h"

#define MAX_BLOCKS 256
#define REC_DOMAIN "lin:settle:v2:leaf"
#define NODE_DOMAIN "lin:settle:v2:node"
#define CHAIN_DOMAIN "lin:settle:v2:chain"

typedef struct {
    int64_t tx, ain, rin, rout, mino, out, steps;
    uint8_t pb;
    uint8_t leaf[32], s0[32], s1[32];
} Rec;

static Rec  recs[MAX_BLOCKS * 4];
static uint8_t roots[MAX_BLOCKS][32];
static uint8_t committed_batch_root[32];
static uint8_t img_sha_file[32];
static uint32_t n_blocks;

/* ---- leitura little-endian ---- */
typedef struct { const uint8_t *p; size_t len, at; int bad; } Rd;
static uint32_t rd_u32(Rd *r) {
    if (r->at + 4 > r->len) { r->bad = 1; return 0; }
    uint32_t v = 0; for (int i = 0; i < 4; i++) v |= (uint32_t)r->p[r->at + i] << (8*i);
    r->at += 4; return v;
}
static uint64_t rd_u64(Rd *r) {
    if (r->at + 8 > r->len) { r->bad = 1; return 0; }
    uint64_t v = 0; for (int i = 0; i < 8; i++) v |= (uint64_t)r->p[r->at + i] << (8*i);
    r->at += 8; return v;
}
static void rd_bytes(Rd *r, uint8_t *o, size_t n) {
    if (r->at + n > r->len) { r->bad = 1; return; }
    memcpy(o, r->p + r->at, n); r->at += n;
}

/* ---- camada Merkle v2 (espelho exato do Python) ---- */
static void put_u64(uint8_t *b, uint64_t v){ for (int i=0;i<8;i++) b[i]=(uint8_t)(v>>(8*i)); }
static void put_i64(uint8_t *b, int64_t v){ put_u64(b,(uint64_t)v); }

static void leaf_v2(uint64_t blk, uint64_t idx, const Rec *r,
                    const uint8_t img_file[32], uint8_t dg[32]) {
    uint8_t buf[sizeof(REC_DOMAIN)-1 + 16 + 56 + 32];
    size_t at = 0;
    memcpy(buf+at, REC_DOMAIN, sizeof(REC_DOMAIN)-1); at += sizeof(REC_DOMAIN)-1;
    put_u64(buf+at, blk); at += 8;
    put_u64(buf+at, idx); at += 8;
    int64_t f[7] = { r->tx, r->ain, r->rin, r->rout, r->mino, r->out, r->steps };
    for (int k = 0; k < 7; k++) { put_i64(buf+at, f[k]); at += 8; }
    memcpy(buf+at, img_file, 32); at += 32;
    lin_sha256(buf, at, dg);
}
static void node_v2(const uint8_t l[32], const uint8_t rr[32], uint8_t dg[32]) {
    uint8_t buf[sizeof(NODE_DOMAIN)-1 + 64];
    memcpy(buf, NODE_DOMAIN, sizeof(NODE_DOMAIN)-1);
    memcpy(buf + sizeof(NODE_DOMAIN)-1, l, 32);
    memcpy(buf + sizeof(NODE_DOMAIN)-1 + 32, rr, 32);
    lin_sha256(buf, sizeof(buf), dg);
}
static void chain_v2(uint32_t nb, const uint8_t img_file[32], uint8_t dg[32]) {
    uint8_t buf[sizeof(CHAIN_DOMAIN)-1 + 4 + MAX_BLOCKS*32 + 32];
    size_t at = 0;
    memcpy(buf, CHAIN_DOMAIN, sizeof(CHAIN_DOMAIN)-1); at += sizeof(CHAIN_DOMAIN)-1;
    buf[at++] = (uint8_t)nb; buf[at++] = (uint8_t)(nb>>8);
    buf[at++] = (uint8_t)(nb>>16); buf[at++] = (uint8_t)(nb>>24);
    for (uint32_t b = 0; b < nb; b++) { memcpy(buf+at, roots[b], 32); at += 32; }
    memcpy(buf+at, img_file, 32); at += 32;
    lin_sha256(buf, at, dg);
}

static int pb_ok(int pb){ return pb >= 0 && pb <= 3; }

/* Verifica a prova de 1 folha (a unidade auditada). Fail-closed em pb inválido. */
static int verify_proof(const uint8_t leaf[32], const uint8_t s0[32],
                        const uint8_t s1[32], int pb, const uint8_t root[32]) {
    if (!pb_ok(pb)) return 0;
    uint8_t cur[32], tmp[32];
    memcpy(cur, leaf, 32);
    if ((pb & 1) == 0) node_v2(cur, s0, tmp); else node_v2(s0, cur, tmp);
    memcpy(cur, tmp, 32);
    if (((pb >> 1) & 1) == 0) node_v2(cur, s1, tmp); else node_v2(s1, cur, tmp);
    memcpy(cur, tmp, 32);
    return memcmp(cur, root, 32) == 0;
}

static double now_ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static int cmp_dbl(const void *a, const void *b) {
    double x = *(const double*)a, y = *(const double*)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "uso: verify_batch_c <batch.bin> <imagem.linbc>\n"); return 2; }

    /* ---- carrega batch.bin ---- */
    static uint8_t batch[1 << 20];
    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "batch.bin ausente\n"); return 2; }
    size_t blen = fread(batch, 1, sizeof(batch), f); fclose(f);

    Rd r = { batch, blen, 0, 0 };
    if (blen < 12 || memcmp(batch, "LINV2B1", 7) != 0 || batch[7] != 1) {
        fprintf(stderr, "CVER error=batch_magic\n"); return 1;
    }
    r.at = 8;
    n_blocks = rd_u32(&r);
    rd_bytes(&r, img_sha_file, 32);
    if (r.bad || n_blocks == 0 || n_blocks > MAX_BLOCKS) {
        fprintf(stderr, "CVER error=batch_header\n"); return 1;
    }

    int leaves_ok = 0, proofs_ok = 0, roots_ok = 0;
    for (uint32_t b = 0; b < n_blocks; b++) {
        uint8_t n0[32], n1[32], root_calc[32];
        for (int i = 0; i < 4; i++) {
            Rec *rc = &recs[b*4 + i];
            rc->tx   = (int64_t)rd_u64(&r); rc->ain  = (int64_t)rd_u64(&r);
            rc->rin  = (int64_t)rd_u64(&r); rc->rout = (int64_t)rd_u64(&r);
            rc->mino = (int64_t)rd_u64(&r); rc->out  = (int64_t)rd_u64(&r);
            rc->steps= (int64_t)rd_u64(&r);
            rd_bytes(&r, &rc->pb, 1);
            rd_bytes(&r, rc->leaf, 32); rd_bytes(&r, rc->s0, 32); rd_bytes(&r, rc->s1, 32);
            if (r.bad) { fprintf(stderr, "CVER error=batch_truncated\n"); return 1; }

            uint8_t calc[32];
            leaf_v2(b, (uint64_t)i, rc, img_sha_file, calc);
            if (memcmp(calc, rc->leaf, 32) == 0) leaves_ok++;
        }
        rd_bytes(&r, roots[b], 32);
        if (r.bad) { fprintf(stderr, "CVER error=batch_truncated_root\n"); return 1; }

        for (int i = 0; i < 4; i++) {
            Rec *rc = &recs[b*4 + i];
            proofs_ok += verify_proof(rc->leaf, rc->s0, rc->s1, rc->pb, roots[b]);
        }
        node_v2(recs[b*4+0].leaf, recs[b*4+1].leaf, n0);
        node_v2(recs[b*4+2].leaf, recs[b*4+3].leaf, n1);
        node_v2(n0, n1, root_calc);
        if (memcmp(root_calc, roots[b], 32) == 0) roots_ok++;
    }
    rd_bytes(&r, committed_batch_root, 32);
    uint8_t batch_calc[32];
    chain_v2(n_blocks, img_sha_file, batch_calc);
    int batch_ok = (memcmp(batch_calc, committed_batch_root, 32) == 0) && !r.bad
                   && (r.at == r.len);

    /* ---- carrega imagem LINBC1 e reexecuta tudo in-process ---- */
    static uint8_t img[64 * 1024];
    FILE *fi = fopen(argv[2], "rb");
    if (!fi) { fprintf(stderr, "CVER error=image_missing\n"); return 2; }
    size_t ilen = fread(img, 1, sizeof(img), fi); fclose(fi);

    LinBc1Vm vm;
    if (lin_bc1_load(img, ilen, &vm) != LIN_BC1_OK) {
        fprintf(stderr, "CVER error=image_load\n"); return 1;
    }
    int fn = lin_bc1_find_fn(&vm, "settle_swap");
    if (fn < 0) { fprintf(stderr, "CVER error=fn_missing\n"); return 1; }

    int exec_ok = 0;
    for (uint32_t b = 0; b < n_blocks; b++) for (int i = 0; i < 4; i++) {
        Rec *rc = &recs[b*4 + i];
        int64_t args[4] = { rc->ain, rc->rin, rc->rout, rc->mino };
        uint64_t steps = 0; VmExecResult res;
        if (vm_exec(&vm.mod, (size_t)fn, args, 4, 0, &steps, &res) != LIN_OK) continue;
        if (res.val == rc->out && (int64_t)steps == rc->steps) exec_ok++;
    }

    /* ---- benchmarks: verificar prova vs reexecutar na VM (mesmo processo) ---- */
    enum { REPS = 31 };
    double vns[REPS], ens[REPS];
    for (int rep = 0; rep < REPS; rep++) {
        double t0 = now_ns();
        uint32_t n = 0;
        for (uint32_t b = 0; b < n_blocks; b++) for (int i = 0; i < 4; i++) {
            Rec *rc = &recs[b*4 + i];
            n += (uint32_t)verify_proof(rc->leaf, rc->s0, rc->s1, rc->pb, roots[b]);
        }
        vns[rep] = (now_ns() - t0) / (double)(n_blocks * 4);
        if (n != n_blocks * 4) { fprintf(stderr, "CVER error=bench_verify_divergence\n"); return 1; }
    }
    for (int rep = 0; rep < REPS; rep++) {
        double t0 = now_ns();
        for (uint32_t b = 0; b < n_blocks; b++) for (int i = 0; i < 4; i++) {
            Rec *rc = &recs[b*4 + i];
            int64_t args[4] = { rc->ain, rc->rin, rc->rout, rc->mino };
            uint64_t steps = 0; VmExecResult res;
            if (vm_exec(&vm.mod, (size_t)fn, args, 4, 0, &steps, &res) != LIN_OK) {}
        }
        ens[rep] = (now_ns() - t0) / (double)(n_blocks * 4);
    }
    qsort(vns, REPS, sizeof(double), cmp_dbl);
    qsort(ens, REPS, sizeof(double), cmp_dbl);
    double v_min = vns[0], v_p50 = vns[REPS/2];
    double e_min = ens[0], e_p50 = ens[REPS/2];

    char hex[65];
    lin_sha256_hex(committed_batch_root, hex);
    printf("CVER roots_ok=%d/%u proofs_ok=%d/%u leaves_ok=%d/%u exec_ok=%d/%u\n",
           roots_ok, n_blocks, proofs_ok, n_blocks*4, leaves_ok, n_blocks*4,
           exec_ok, n_blocks*4);
    printf("CVER batch_ok=%d batch_root=%s\n", batch_ok, hex);
    printf("CVER verify_ns_min=%.0f verify_ns_p50=%.0f exec_ns_min=%.0f exec_ns_p50=%.0f\n",
           v_min, v_p50, e_min, e_p50);
    printf("CVER ratio_reexec_vs_audit=%.2f\n", e_p50 / v_p50);
    return (batch_ok && proofs_ok == (int)n_blocks*4 && leaves_ok == (int)n_blocks*4
            && exec_ok == (int)n_blocks*4 && roots_ok == (int)n_blocks) ? 0 : 1;
}
