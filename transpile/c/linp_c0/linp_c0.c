/*
 * linp_c0.c — Compilador-0 da irma linp, em C11 minimo. So `cc`, sem Zig/Go.
 *
 * Papel (igual ao lin_c0 do LIN): stage-0 auditavel. Le plano .linp canonico
 * + payload base64url ja comprimido, emite .linpbc (byte-identico ao Go),
 * discos v2, manifest.json, manifest.rulel e receipt.json — tudo com o
 * SHA-256 REAL do LIN (linka transpile/c/lin_c/lin_sha256.c, sem copiar).
 *
 * O front-end auto-hospedado (em LIN) tem que reproduzir estes bytes;
 * Python/Go sao apenas oraculos DDC, nunca o compilador.
 *
 * Uso: linp_c0 job.linp payload.b64 orig_bytes comp_bytes outdir/
 *   (orig/comp = tamanhos medidos por quem comprimiu; rc=0 ok, rc=1 fail-closed)
 *
 * Limites P0 (fail-closed, sem heap): payload <= 4MiB, 1 PACK, chunk 64..1800000.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>

#include "lin_sha256.h"

#define PAYLOAD_MAX (4u * 1024u * 1024u)
#define LINEBUF 2048

#define DIE(...) do { fprintf(stderr, "linp_c0: " __VA_ARGS__); fputc('\n', stderr); return 1; } while (0)

static char g_job[256], g_file[1024], g_algo[16];
static long g_chunk;
static int g_packs;

static void w16(uint8_t *b, size_t *o, uint16_t v) {
	b[(*o)++] = (uint8_t)(v & 0xFF);
	b[(*o)++] = (uint8_t)((v >> 8) & 0xFF);
}
static void w32(uint8_t *b, size_t *o, uint32_t v) {
	b[(*o)++] = (uint8_t)(v & 0xFF);
	b[(*o)++] = (uint8_t)((v >> 8) & 0xFF);
	b[(*o)++] = (uint8_t)((v >> 16) & 0xFF);
	b[(*o)++] = (uint8_t)((v >> 24) & 0xFF);
}

static int algo_id(const char *a, uint8_t *out) {
	if (!strcmp(a, "deflate")) { *out = 0; return 1; }
	if (!strcmp(a, "gzip")) { *out = 1; return 1; }
	if (!strcmp(a, "brotli")) { *out = 2; return 1; }
	return 0;
}

/* JSON string com as mesmas regras do encoding/json do Go (inclui <>&). */
static void json_str(FILE *f, const char *s) {
	fputc('"', f);
	for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
		if (*p == '"') fputs("\\\"", f);
		else if (*p == '\\') fputs("\\\\", f);
		else if (*p == '\n') fputs("\\n", f);
		else if (*p == '\r') fputs("\\r", f);
		else if (*p == '\t') fputs("\\t", f);
		else if (*p == '<') fputs("\\u003c", f);
		else if (*p == '>') fputs("\\u003e", f);
		else if (*p == '&') fputs("\\u0026", f);
		else if (*p < 0x20) fprintf(f, "\\u%04x", *p);
		else fputc(*p, f);
	}
	fputc('"', f);
}

/* %q do Go (strconv.Quote) para o RuleL: sem <>&, com escapes C. */
static void go_quote(FILE *f, const char *s) {
	fputc('"', f);
	for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
		if (*p == '"') fputs("\\\"", f);
		else if (*p == '\\') fputs("\\\\", f);
		else if (*p == '\n') fputs("\\n", f);
		else if (*p == '\r') fputs("\\r", f);
		else if (*p == '\t') fputs("\\t", f);
		else if (*p < 0x20 || *p == 0x7F) fprintf(f, "\\x%02x", *p);
		else fputc(*p, f);
	}
	fputc('"', f);
}

static char *read_all(const char *path, size_t *len_out, size_t cap) {
	FILE *f = fopen(path, "rb");
	if (!f) return 0;
	static char big[PAYLOAD_MAX + 4096];
	size_t n = fread(big, 1, cap, f);
	fclose(f);
	if (n >= cap) return 0; /* excedeu: fail-closed pelo chamador */
	*len_out = n;
	return big;
}

int main(int argc, char **argv) {
	if (argc != 6) DIE("uso: linp_c0 job.linp payload.b64 orig_bytes comp_bytes outdir/");
	const char *plan_path = argv[1], *pay_path = argv[2], *outdir = argv[5];
	char *end = 0;
	long orig = strtol(argv[3], &end, 10);
	if (!end || *end || orig < 0) DIE("orig_bytes invalido");
	long comp = strtol(argv[4], &end, 10);
	if (!end || *end || comp < 0) DIE("comp_bytes invalido");

	/* ---- plano (linhas fisicas contadas como no Go, vazias inclusive) ---- */
	size_t plen = 0;
	char *plan = read_all(plan_path, &plen, 65536);
	if (!plan) DIE("nao abre %s", plan_path);
	plan[plen] = 0;
	int lineno = 0, complete = 0;
	char *cur = plan;
	while (1) {
		lineno++;
		char *nl = strchr(cur, '\n');
		char line[LINEBUF];
		size_t ll = nl ? (size_t)(nl - cur) : strlen(cur);
		if (ll >= sizeof line) DIE("linha %d excede %d chars", lineno, LINEBUF - 1);
		memcpy(line, cur, ll);
		line[ll] = 0;
		if (!nl) { cur += ll; } else { cur = nl + 1; }
		int last = !nl && cur >= plan + plen;
		(void)last;
		char *s = line;
		while (*s == ' ' || *s == '\t') s++;
		size_t L = strlen(s);
		while (L && (s[L - 1] == ' ' || s[L - 1] == '\t' || s[L - 1] == '\r')) s[--L] = 0;
		if (!*s) {
			if (!nl) break;
			continue;
		}
		if (lineno == 1 && !strncmp(s, "@LINP:1.0", 8)) {
			if (!nl) break;
			continue;
		}
		if (!strncmp(s, "JOB ", 4)) {
			if (g_job[0]) DIE("linha %d: JOB duplicado", lineno);
			if (strlen(s + 4) == 0 || strlen(s + 4) > 255) DIE("linha %d: JOB invalido", lineno);
			strcpy(g_job, s + 4);
		} else if (!strncmp(s, "FILE ", 5)) {
			if (g_file[0]) DIE("linha %d: FILE duplicado", lineno);
			if (strstr(s + 5, "..") || s[5] == '/' || !s[5]) DIE("linha %d: path fora do repo", lineno);
			if (strlen(s + 5) > 1023) DIE("linha %d: path longo", lineno);
			strcpy(g_file, s + 5);
		} else if (!strncmp(s, "ALGO ", 5)) {
			uint8_t aid;
			if (g_algo[0]) DIE("linha %d: ALGO duplicado", lineno);
			if (!algo_id(s + 5, &aid)) DIE("linha %d: algo desconhecido", lineno);
			strcpy(g_algo, s + 5);
		} else if (!strncmp(s, "CHUNK ", 6)) {
			if (g_chunk) DIE("linha %d: CHUNK duplicado", lineno);
			char *e2 = 0;
			long v = strtol(s + 6, &e2, 10);
			if (!e2 || *e2 || v < 64 || v > 1800000) DIE("linha %d: CHUNK fora de [64,1800000]", lineno);
			g_chunk = v;
		} else if (!strcmp(s, "PACK")) {
			if (++g_packs > 1) DIE("linha %d: P0 aceita 1 PACK", lineno);
		} else if (!strcmp(s, "END")) {
			complete = 1;
		} else {
			DIE("linha %d: diretiva fora do subset linp-P0", lineno);
		}
		if (!nl) break;
	}
	if (!g_job[0] || !g_file[0] || !g_algo[0] || !g_chunk || g_packs != 1 || !complete)
		DIE("plano incompleto (JOB/FILE/ALGO/CHUNK/PACK/END)");

	/* ---- payload (texto b64 exato; tolera CR/LF final) ---- */
	size_t paylen = 0;
	char *pay = read_all(pay_path, &paylen, PAYLOAD_MAX);
	if (!pay) DIE("payload ausente ou > %u bytes", PAYLOAD_MAX);
	while (paylen && (pay[paylen - 1] == '\n' || pay[paylen - 1] == '\r')) paylen--;
	if (!paylen) DIE("payload vazio");

	uint8_t dg[32];
	char root[65];
	lin_sha256(pay, paylen, dg);
	lin_sha256_hex(dg, root);

	/* ---- .linpbc (byte-identico ao Go) ---- */
	uint8_t aid;
	algo_id(g_algo, &aid);
	static uint8_t bc[8192];
	size_t o = 0;
	bc[o++] = 'L'; bc[o++] = 'N'; bc[o++] = 'P'; bc[o++] = '1';
	bc[o++] = 0x01;
	w16(bc, &o, 0);
	w16(bc, &o, 1);
	bc[o++] = aid;
	bc[o++] = 0x00;
	w32(bc, &o, (uint32_t)g_chunk);
	w16(bc, &o, 2);
	w16(bc, &o, (uint16_t)strlen(g_job));
	memcpy(bc + o, g_job, strlen(g_job));
	o += strlen(g_job);
	w16(bc, &o, (uint16_t)strlen(g_file));
	memcpy(bc + o, g_file, strlen(g_file));
	o += strlen(g_file);

	/* saida */
	char path[4096];
	if (mkdir(outdir, 0755) != 0 && errno != EEXIST) DIE("nao cria %s", outdir);
	snprintf(path, sizeof path, "%s/job.linpbc", outdir);
	FILE *f = fopen(path, "wb");
	if (!f) DIE("nao escreve %s", path);
	if (fwrite(bc, 1, o, f) != o) { fclose(f); DIE("falha de escrita"); }
	fclose(f);

	size_t total = (paylen + (size_t)g_chunk - 1) / (size_t)g_chunk;
	static char hashes[65536][65];
	if (total > 65536) DIE("disks demais");
	for (size_t i = 0; i < total; i++) {
		size_t st = i * (size_t)g_chunk, en = st + (size_t)g_chunk;
		if (en > paylen) en = paylen;
		uint8_t d2[32];
		/* sha sobre a fatia sem copiar: update incremental */
		LinSha256 ctx;
		lin_sha256_init(&ctx);
		lin_sha256_update(&ctx, pay + st, en - st);
		lin_sha256_final(&ctx, d2);
		lin_sha256_hex(d2, hashes[i]);
		snprintf(path, sizeof path, "%s/disk_%02zu.txt", outdir, i + 1);
		f = fopen(path, "w");
		if (!f) DIE("nao escreve %s", path);
		fprintf(f, "v2;%s;[%zu/%zu];%s;%s;%.*s", g_algo, i + 1, total,
		        hashes[i], root, (int)(en - st), pay + st);
		fclose(f);
	}

	/* manifest.json (chaves ordenadas == encoding/json do Go) */
	snprintf(path, sizeof path, "%s/manifest.json", outdir);
	f = fopen(path, "w");
	if (!f) DIE("nao escreve %s", path);
	fprintf(f, "{\n");
	fprintf(f, "  \"algorithm\": ");
	json_str(f, g_algo);
	fprintf(f, ",\n  \"compressed_bytes\": %ld,\n  \"disk_hashes\": [", comp);
	for (size_t i = 0; i < total; i++)
		fprintf(f, "%s\n    \"%s\"", i ? "," : "", hashes[i]);
	fprintf(f, "\n  ],\n  \"encoded_chars\": %zu,\n  \"format_version\": \"v2\",\n  \"job\": ", paylen);
	json_str(f, g_job);
	fprintf(f, ",\n  \"original_bytes\": %ld,\n  \"root_sha256\": \"%s\",\n  \"source_file\": ", orig, root);
	json_str(f, g_file);
	fprintf(f, ",\n  \"total_disks\": %zu\n}", total);
	fclose(f);

	/* manifest.rulel (linha a linha == Go) */
	snprintf(path, sizeof path, "%s/manifest.rulel", outdir);
	f = fopen(path, "w");
	if (!f) DIE("nao escreve %s", path);
	fprintf(f, "@RULEL:FLOPPY_MANIFEST:2.0.0\n");
	fprintf(f, "~R{.s=source .a=algo .o=orig_bytes .c=comp_bytes .e=enc_chars .t=total_disks .r=root_sha .f=format}\n");
	fprintf(f, ".source=");
	go_quote(f, g_file);
	fprintf(f, "\n.algo=");
	go_quote(f, g_algo);
	fprintf(f, "\n.format=\"v2\"\n.orig_bytes=%ld\n.comp_bytes=%ld\n.enc_chars=%zu\n.total_disks=%zu\n.root_sha256=\"%s\"\n.disk_hashes=[\n",
	        orig, comp, paylen, total, root);
	for (size_t i = 0; i < total; i++)
		fprintf(f, "  \"%s\",\n", hashes[i]);
	fprintf(f, "]\n");
	fclose(f);

	/* receipt.json (amarra source/bytecode/root, estilo LIN) */
	uint8_t s1[32], s2[32];
	char h1[65], h2[65];
	{
		size_t pl2 = 0;
		char *psrc = read_all(plan_path, &pl2, 65536);
		lin_sha256(psrc, pl2, s1);
	}
	lin_sha256(bc, o, s2);
	lin_sha256_hex(s1, h1);
	lin_sha256_hex(s2, h2);
	snprintf(path, sizeof path, "%s/receipt.json", outdir);
	f = fopen(path, "w");
	if (!f) DIE("nao escreve %s", path);
	fprintf(f, "{\n  \"algo\": ");
	json_str(f, g_algo);
	fprintf(f, ",\n  \"bytecode_sha256\": \"%s\",\n  \"job\": ", h2);
	json_str(f, g_job);
	fprintf(f, ",\n  \"root_sha256\": \"%s\",\n  \"source_sha256\": \"%s\"\n}", root, h1);
	fclose(f);

	printf("linp_c0 OK job=%s root=%s disks=%zu\n", g_job, root, total);
	return 0;
}
