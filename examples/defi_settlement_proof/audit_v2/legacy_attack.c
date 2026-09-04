/*
 * legacy_attack.c — Forense criptográfica do hash legado de 32 bits
 *                   ("hash_pair" de settlement_engine.lin / benchmark v1).
 *
 * Modo "preimage":
 *   Dados (tx_id, out, steps, s0, s1, path_bits, root) de um bloco REAL,
 *   procura out' != out com hash_leaf_legado(tx, out', steps) == folha original
 *   (segunda pré-imagem; espaço de 2^32, custo esperado ~2^32 sondas).
 *   Ao encontrar, reconstrói a fraude e verifica contra o verificador Merkle
 *   LEGADO: se aceitar, prova que a "detecção 100%" do benchmark v1 não se
 *   sustenta contra um adversário que possa escolher o valor reportado.
 *
 * Modo "sha-budget":
 *   Mesmo ataque (forçar segunda pré-imagem da folha variando out'),
 *   agora contra a folha SHA-256 v2, com orçamento fixo de sondas.
 *   Resultado honesto esperado: 0 colisões (custo esperado 2^256).
 *
 * Uso:
 *   legacy_attack preimage <tx> <out> <steps> <s0> <s1> <pb> <root>
 *   legacy_attack sha-budget <tx> <ain> <rin> <rout> <min> <out> <steps> <img_sha_hex> <budget>
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

/* ------------------------------------------------------------------ */
/* Hash LEGADO (espelho exato de hash_pair_py / !hash_pair do .lin)   */
/* ------------------------------------------------------------------ */

static uint32_t hash_pair(uint64_t left, uint64_t right) {
    uint64_t v = (left * 2146129197ull) ^ (right * 2221712011ull);
    v = (v ^ (v >> 16)) * 16843009ull;
    return (uint32_t)((v ^ (v >> 15)) & 0xFFFFFFFFull);
}

static uint64_t seed_of(int64_t tx, int64_t out, int64_t steps) {
    return (uint64_t)tx * 1000003ull ^ (uint64_t)out * 997ull ^ (uint64_t)steps;
}

static uint32_t leaf_legacy(int64_t tx, int64_t out, int64_t steps) {
    uint64_t s = seed_of(tx, out, steps);
    return hash_pair(s & 0xFFFFFFFFull, (s >> 32) & 0xFFFFFFFFull);
}

/* verify_merkle_path legado (espelho de verify_merkle_branch_2 no .lin) */
static int legacy_path_ok(uint32_t leaf, uint32_t s0, uint32_t s1,
                          int pb, uint32_t root) {
    uint64_t c = leaf;
    if ((pb & 1) == 0) c = ((c * 2146129197ull) ^ ((uint64_t)s0 * 2221712011ull));
    else               c = (((uint64_t)s0 * 2146129197ull) ^ (c * 2221712011ull));
    c = (c ^ (c >> 16)) * 16843009ull;
    c = (c ^ (c >> 15)) & 0xFFFFFFFFull;

    if (((pb >> 1) & 1) == 0) c = ((c * 2146129197ull) ^ ((uint64_t)s1 * 2221712011ull));
    else                      c = (((uint64_t)s1 * 2146129197ull) ^ (c * 2221712011ull));
    c = (c ^ (c >> 16)) * 16843009ull;
    c = (c ^ (c >> 15)) & 0xFFFFFFFFull;
    return (uint32_t)c == root;
}

/* ------------------------------------------------------------------ */
/* SHA-256 v2 (folha do auditor) — domínio idêntico ao benchmark v2    */
/* ------------------------------------------------------------------ */

#define LEAF_DOM "lin:settle:v2:leaf"

static const char *g_img_sha_hex; /* 64 hex chars */

static void hex_to_bytes(const char *hex, uint8_t out[32]) {
    for (int i = 0; i < 32; i++) {
        unsigned b; sscanf(hex + 2 * i, "%2x", &b); out[i] = (uint8_t)b;
    }
}

/* SHA-256 minimalista (apenas para o ataque; independiente de OpenSSL) */
typedef struct { uint32_t st[8]; uint64_t len; uint8_t buf[64]; size_t bl; } Sha;
static const uint32_t K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
static uint32_t ror(uint32_t x, int n){ return (x >> n) | (x << (32 - n)); }
static void sha_block(Sha *s, const uint8_t *p) {
    uint32_t w[64], a,b,c,d,e,f,g,h,t1,t2;
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|p[4*i+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3);
        uint32_t s1 = ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10);
        w[i] = w[i-16]+s0+w[i-7]+s1;
    }
    a=s->st[0];b=s->st[1];c=s->st[2];d=s->st[3];e=s->st[4];f=s->st[5];g=s->st[6];h=s->st[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ror(e,6)^ror(e,11)^ror(e,25);
        uint32_t ch = (e & f) ^ (~e & g);
        t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = ror(a,2)^ror(a,13)^ror(a,22);
        uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
        t2 = S0 + mj;
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    s->st[0]+=a;s->st[1]+=b;s->st[2]+=c;s->st[3]+=d;
    s->st[4]+=e;s->st[5]+=f;s->st[6]+=g;s->st[7]+=h;
}
static void sha_init(Sha *s){
    s->st[0]=0x6a09e667;s->st[1]=0xbb67ae85;s->st[2]=0x3c6ef372;s->st[3]=0xa54ff53a;
    s->st[4]=0x510e527f;s->st[5]=0x9b05688c;s->st[6]=0x1f83d9ab;s->st[7]=0x5be0cd19;
    s->len=0; s->bl=0;
}
static void sha_up(Sha *s, const void *data, size_t n) {
    const uint8_t *p = data;
    s->len += n;
    while (n) {
        size_t take = 64 - s->bl; if (take > n) take = n;
        memcpy(s->buf + s->bl, p, take);
        s->bl += take; p += take; n -= take;
        if (s->bl == 64) { sha_block(s, s->buf); s->bl = 0; }
    }
}
static void sha_fin(Sha *s, uint8_t out[32]) {
    uint64_t bits = s->len * 8;
    uint8_t pad = 0x80; sha_up(s, &pad, 1);
    uint8_t z = 0; while (s->bl != 56) sha_up(s, &z, 1);
    uint8_t l[8]; for (int i = 0; i < 8; i++) l[7-i] = (uint8_t)(bits >> (8*i));
    /* atenção: sha_up somaria len de novo; escreve direto */
    memcpy(s->buf + 56, l, 8); sha_block(s, s->buf); s->bl = 0;
    for (int i = 0; i < 8; i++) {
        out[4*i]   = (uint8_t)(s->st[i] >> 24); out[4*i+1] = (uint8_t)(s->st[i] >> 16);
        out[4*i+2] = (uint8_t)(s->st[i] >> 8);  out[4*i+3] = (uint8_t)s->st[i];
    }
}
static void sha256(const void *d, size_t n, uint8_t out[32]) {
    Sha s; sha_init(&s); sha_up(&s, d, n); sha_fin(&s, out);
}

/* Folha v2: SHA256("lin:settle:v2:leaf" || blk:u64 || idx:u64 ||
 *                  7×i64 campos || img_sha256[32])  */
static void leaf_v2(uint64_t blk, uint64_t idx,
                    int64_t tx, int64_t ain, int64_t rin, int64_t rout,
                    int64_t mino, int64_t out, int64_t steps,
                    uint8_t digest[32]) {
    uint8_t img[32]; hex_to_bytes(g_img_sha_hex, img);
    uint8_t buf[sizeof(LEAF_DOM)-1 + 16 + 56 + 32];
    size_t at = 0;
    memcpy(buf + at, LEAF_DOM, sizeof(LEAF_DOM)-1); at += sizeof(LEAF_DOM)-1;
    for (int i = 0; i < 8; i++) buf[at + i] = (uint8_t)(blk >> (8*i));
    at += 8;
    for (int i = 0; i < 8; i++) buf[at + i] = (uint8_t)(idx >> (8*i));
    at += 8;
    int64_t f[7] = { tx, ain, rin, rout, mino, out, steps };
    for (int k = 0; k < 7; k++) {
        for (int i = 0; i < 8; i++) buf[at + i] = (uint8_t)((uint64_t)f[k] >> (8*i));
        at += 8;
    }
    memcpy(buf + at, img, 32); at += 32;
    sha256(buf, at, digest);
}

static double now_s(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "modo ausente\n"); return 2; }

    if (strcmp(argv[1], "preimage") == 0) {
        if (argc != 9) { fprintf(stderr, "uso: preimage tx out steps s0 s1 pb root\n"); return 2; }
        int64_t tx  = strtoll(argv[2], 0, 10);
        int64_t out = strtoll(argv[3], 0, 10);
        int64_t st  = strtoll(argv[4], 0, 10);
        uint32_t s0 = (uint32_t)strtoul(argv[5], 0, 10);
        uint32_t s1 = (uint32_t)strtoul(argv[6], 0, 10);
        int      pb = (int)strtol(argv[7], 0, 10);
        uint32_t rt = (uint32_t)strtoul(argv[8], 0, 10);

        uint32_t target = leaf_legacy(tx, out, st);
        if (!legacy_path_ok(target, s0, s1, pb, rt)) {
            printf("PREIMAGE_SANITY=0 (bloco nao confere; abortando)\n");
            return 1;
        }
        printf("PREIMAGE_SANITY=1 prova legitima confere no verificador legado\n");
        printf("TARGET_LEAF=%u\n", target);

        double t0 = now_s();
        uint64_t probes = 0;
        int64_t found = 0;
        for (uint64_t o = 1; o < 0x8000000000000000ull; o++) {
            if ((uint64_t)o == (uint64_t)out) continue;
            probes++;
            if (leaf_legacy(tx, (int64_t)o, st) == target) { found = (int64_t)o; break; }
            if ((probes & 0xFFFFFFFull) == 0)
                fprintf(stderr, "  ... %.1f M sondas (%.1fs)\n", probes / 1e6, now_s() - t0);
        }
        double dt = now_s() - t0;
        if (!found) { printf("PREIMAGE_FOUND=0 probes=%" PRIu64 "\n", probes); return 1; }

        printf("PREIMAGE_FOUND=1 probes=%" PRIu64 " tempo=%.2fs\n", probes, dt);
        printf("FORGED_OUT=%" PRId64 " (original=%" PRId64 ")\n", found, out);
        uint32_t forged = leaf_legacy(tx, found, st);
        int accepted = (forged == target) && legacy_path_ok(forged, s0, s1, pb, rt);
        printf("LEGACY_VERIFIER_ACCEPTS_FRAUD=%d\n", accepted);
        printf(accepted
            ? "VEREDITO=hash legado de 32 bits NAO resiste a adversario ativo\n"
            : "VEREDITO=falha inesperada\n");
        return accepted ? 0 : 1;
    }

    if (strcmp(argv[1], "sha-budget") == 0) {
        if (argc != 11) {
            fprintf(stderr, "uso: sha-budget tx ain rin rout min out steps img_sha_hex budget\n");
            return 2;
        }
        int64_t tx  = strtoll(argv[2], 0, 10);
        int64_t ain = strtoll(argv[3], 0, 10);
        int64_t rin = strtoll(argv[4], 0, 10);
        int64_t rout= strtoll(argv[5], 0, 10);
        int64_t mino= strtoll(argv[6], 0, 10);
        int64_t out = strtoll(argv[7], 0, 10);
        int64_t st  = strtoll(argv[8], 0, 10);
        g_img_sha_hex = argv[9];
        uint64_t budget = strtoull(argv[10], 0, 10);

        uint8_t target[32];
        leaf_v2(0, 0, tx, ain, rin, rout, mino, out, st, target);

        double t0 = now_s();
        uint64_t probes = 0; int hit = 0;
        for (uint64_t o = 1; o <= budget; o++) {
            uint8_t d[32];
            leaf_v2(0, 0, tx, ain, rin, rout, mino, (int64_t)o, st, d);
            probes++;
            if (memcmp(d, target, 32) == 0 && (int64_t)o != out) { hit = 1; break; }
        }
        printf("SHA_BUDGET probes=%" PRIu64 " found=%d tempo=%.2fs custo_esperado=2^256\n",
               probes, hit, now_s() - t0);
        return hit ? 1 : 0;
    }

    fprintf(stderr, "modo desconhecido: %s\n", argv[1]);
    return 2;
}
