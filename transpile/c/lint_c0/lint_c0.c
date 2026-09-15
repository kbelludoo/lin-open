/*
 * lint_c0.c — Compilador-0 da irma lint, em C11 minimo. So `cc`, sem Zig, sem Go.
 *
 * Papel (igual ao lin_c0 do LIN): stage-0 auditavel que compila .lay -> .laybc
 * com bytes deterministicos. O front-end auto-hospedado (em LIN) tem que
 * reproduzir estes bytes bit a bit (ponto fixo C0=C1); Python/Go sao apenas
 * oraculos independentes (DDC), nunca o compilador.
 *
 * Uso: lint_c0 entrada.lay saida.laybc   (rc=0 ok; rc=1 fail-closed no stderr)
 *
 * Limites P0 (fail-closed, sem heap): 1024 nos, 1024 strings, 8KiB de texto,
 * linha <= 2047 chars, texto <= 500 chars. Tudo que excede e erro, nunca corte.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXNODES 1024
#define MAXSTR   1024
#define STRCAP   8192
#define LINEBUF  2048
#define MAXTEXT  500
#define MAXDEPTH 256

static int fails = 0;
#define DIE(fmt, ...) do { fprintf(stderr, "lint_c0: " fmt "\n", ##__VA_ARGS__); return 1; } while (0)

/* ---- tags (mesmos IDs do front-end de referencia) ---- */
typedef struct { const char *name; uint8_t id; } TagEnt;
static const TagEnt TAGS[] = {
	{ "VIEW", 0 }, { "DIV", 1 }, { "ROW", 2 }, { "COL", 3 },
	{ "H1", 4 }, { "H2", 5 }, { "H3", 6 }, { "P", 7 }, { "PRE", 8 },
	{ "BUTTON", 9 }, { "INPUT", 10 }, { "SPAN", 11 }, { "A", 12 },
	{ "IMG", 13 }, { "IFRAME", 14 }, { "SECTION", 15 },
	{ 0, 0 },
};

static int tag_lookup(const char *kw, uint8_t *out) {
	for (int i = 0; TAGS[i].name; i++)
		if (strcmp(TAGS[i].name, kw) == 0) { *out = TAGS[i].id; return 1; }
	return 0;
}

/* ---- arena ---- */
typedef struct {
	int parent; /* -1 raiz */
	uint8_t tag;
	char text[512];
	char style[512];
	char attrs[512];
	char action[128];
	int childCnt;
} Node;

static Node nodes[MAXNODES];
static int nnodes = 0;

/* string table: interning linear, deterministico por ordem de 1o uso */
static char stab[STRCAP];
static int soff = 0;
static int sidx_off[MAXSTR]; /* offset de cada string */
static int sidx_len[MAXSTR];
static int nstr = 0;

static int intern(const char *s) {
	if (!s || !s[0]) return 0xFFFF;
	for (int i = 0; i < nstr; i++) {
		if ((int)strlen(s) == sidx_len[i] && memcmp(s, stab + sidx_off[i], sidx_len[i]) == 0)
			return i;
	}
	int ln = (int)strlen(s);
	if (nstr >= MAXSTR || soff + ln > STRCAP) {
		fprintf(stderr, "lint_c0: string table esgotada\n");
		exit(1);
	}
	sidx_off[nstr] = soff;
	sidx_len[nstr] = ln;
	memcpy(stab + soff, s, (size_t)ln);
	soff += ln;
	return nstr++;
}

/* ---- util ---- */
static void w16(uint8_t *b, int *o, uint16_t v) {
	b[(*o)++] = (uint8_t)(v & 0xFF);
	b[(*o)++] = (uint8_t)((v >> 8) & 0xFF);
}

/* tokeniza respeitando aspas; espelha layTokenize do Go (aspas SAO emitidas
 * no token para que parseExtra detecte texto via tok[0]=='"'). */
static int tokenize(char *line, char *toks[], int cap) {
	int n = 0, in = 0;
	char *p = line, *start = 0;
	for (; *p && n < cap; p++) {
		if (*p == '"') { in = !in; if (!start) start = p; continue; }
		if (!in && (*p == ' ' || *p == '\t')) {
			if (start) { *p = 0; toks[n++] = start; start = 0; }
			continue;
		}
		if (!start) start = p;
	}
	if (start && n < cap) toks[n++] = start;
	return n;
}

/* maiusculas in-place (ASCII) */
static void upcase(char *s) {
	for (; *s; s++) if (*s >= 'a' && *s <= 'z') *s -= 32;
}

int main(int argc, char **argv) {
	(void)fails;
	if (argc != 3) DIE("uso: lint_c0 entrada.lay saida.laybc");
	FILE *fin = fopen(argv[1], "rb");
	if (!fin) DIE("nao abre %s", argv[1]);

	char line[LINEBUF];
	int lineno = 0, rootIdx = -1;
	int st_idx[MAXDEPTH], st_ind[MAXDEPTH], sdep = 0;
	int first = 1;

	while (fgets(line, sizeof line, fin)) {
		lineno++;
		/* linha maior que o buffer = corte silencioso seria bug: detecta */
		if (!strchr(line, '\n') && !feof(fin)) DIE("linha %d excede %d chars", lineno, LINEBUF - 1);
		/* strip \r\n */
		line[strcspn(line, "\r\n")] = 0;
		/* tira comentario // fora de aspas */
		{
			int in = 0;
			for (char *p = line; *p; p++) {
				if (*p == '"') in = !in;
				if (!in && p[0] == '/' && p[1] == '/') { *p = 0; break; }
			}
		}
		/* vazia? */
		char *t = line;
		while (*t == ' ' || *t == '\t') t++;
		if (!*t) continue;
		if (first && strncmp(t, "@LAY:", 5) == 0) { first = 0; continue; }
		first = 0;
		if (*t == '@') continue; /* anotacoes */

		int indent = (int)(t - line);
		char work[LINEBUF];
		strncpy(work, t, sizeof work - 1);
		work[sizeof work - 1] = 0;
		char *sp = strchr(work, ' ');
		char kw[32];
		if (sp) { size_t k = (size_t)(sp - work); if (k > 31) k = 31; memcpy(kw, work, k); kw[k] = 0; }
		else { strncpy(kw, work, 31); kw[31] = 0; }
		upcase(kw);

		if (strcmp(kw, "STYLE") != 0 && strcmp(kw, "END") != 0) {
			while (sdep > 0 && indent < st_ind[sdep - 1]) sdep--;
			while (sdep > 0 && indent == st_ind[sdep - 1]) sdep--;
		}
		int parent = sdep > 0 ? st_idx[sdep - 1] : -1;

		char *toks[64];
		int ntok = tokenize(work, toks, 64);
		if (!ntok) continue;

		if (strcmp(kw, "VIEW") == 0) {
			if (nnodes >= MAXNODES) DIE("linha %d: nos > %d", lineno, MAXNODES);
			nodes[nnodes].parent = parent;
			nodes[nnodes].tag = 0;
			nodes[nnodes].text[0] = nodes[nnodes].style[0] = 0;
			nodes[nnodes].attrs[0] = nodes[nnodes].action[0] = 0;
			nodes[nnodes].childCnt = 0;
			if (rootIdx < 0) rootIdx = nnodes;
			if (parent >= 0) nodes[parent].childCnt++;
			if (sdep >= MAXDEPTH) DIE("linha %d: profundidade", lineno);
			st_idx[sdep] = nnodes; st_ind[sdep] = indent; sdep++;
			nnodes++;
		} else if (strcmp(kw, "STYLE") == 0) {
			if (!sdep) DIE("linha %d: STYLE fora de no", lineno);
			Node *n = &nodes[st_idx[sdep - 1]];
			n->style[0] = 0;
			for (int i = 1; i < ntok; i++) {
				if (i > 1) strncat(n->style, " ", sizeof n->style - strlen(n->style) - 1);
				strncat(n->style, toks[i], sizeof n->style - strlen(n->style) - 1);
			}
		} else if (strcmp(kw, "END") == 0) {
			if (sdep > 0) sdep--;
		} else {
			uint8_t id;
			if (!tag_lookup(kw, &id)) DIE("linha %d: tag desconhecida '%s'", lineno, toks[0]);
			if (nnodes >= MAXNODES) DIE("linha %d: nos > %d", lineno, MAXNODES);
			Node *n = &nodes[nnodes];
			n->parent = parent; n->tag = id; n->childCnt = 0;
			n->text[0] = n->style[0] = n->attrs[0] = n->action[0] = 0;
			for (int i = 1; i < ntok; i++) {
				char *tok = toks[i];
				if (tok[0] == '"') {
					size_t L = strlen(tok);
					if (L >= 2 && tok[L - 1] == '"') { tok[L - 1] = 0; tok++; }
					else tok++;
					if ((int)strlen(tok) > MAXTEXT) DIE("linha %d: texto > %d", lineno, MAXTEXT);
					strncpy(n->text, tok, sizeof n->text - 1);
				} else {
					char *eq = strchr(tok, '=');
					if (!eq) {
						/* Igual a referencia Go (parseExtra): token avulso sem '='
						 * (ex: CLASS body) e descartado em silencio. Comportamento
						 * travado pelo gate (golden), nao virtude — mudar exige
						 * gate de paridade antes/depois. */
						continue;
					}
					*eq = 0;
					char k[32]; strncpy(k, tok, 31); k[31] = 0; upcase(k);
					if (strcmp(k, "STYLE") == 0) strncpy(n->style, eq + 1, sizeof n->style - 1);
					else if (strcmp(k, "ACTION") == 0) strncpy(n->action, eq + 1, sizeof n->action - 1);
					else {
						*eq = '=';
						if (n->attrs[0]) strncat(n->attrs, " ", sizeof n->attrs - strlen(n->attrs) - 1);
						strncat(n->attrs, tok, sizeof n->attrs - strlen(n->attrs) - 1);
					}
				}
			}
			if (parent >= 0) nodes[parent].childCnt++;
			if (sdep >= MAXDEPTH) DIE("linha %d: profundidade", lineno);
			st_idx[sdep] = nnodes; st_ind[sdep] = indent; sdep++;
			nnodes++;
		}
	}
	fclose(fin);
	if (rootIdx < 0) {
		if (!nnodes) DIE("sem no VIEW raiz");
		rootIdx = 0;
	}

	/* interna strings na ordem dos nos (igual referencia) p/ tabela deterministica */
	uint16_t rT[MAXNODES], rS[MAXNODES], rA[MAXNODES], rC[MAXNODES];
	for (int i = 0; i < nnodes; i++) {
		rT[i] = (uint16_t)intern(nodes[i].text);
		rS[i] = (uint16_t)intern(nodes[i].style);
		rA[i] = (uint16_t)intern(nodes[i].attrs);
		rC[i] = (uint16_t)intern(nodes[i].action);
	}

	uint8_t out[65536];
	int o = 0;
	out[o++] = 'L'; out[o++] = 'A'; out[o++] = 'Y'; out[o++] = '1';
	out[o++] = 0x01;
	w16(out, &o, (uint16_t)rootIdx);
	w16(out, &o, (uint16_t)nnodes);
	w16(out, &o, (uint16_t)nstr);
	for (int i = 0; i < nstr; i++) {
		w16(out, &o, (uint16_t)sidx_len[i]);
		memcpy(out + o, stab + sidx_off[i], (size_t)sidx_len[i]);
		o += sidx_len[i];
	}
	for (int i = 0; i < nnodes; i++) {
		uint8_t fl = 0;
		if (nodes[i].text[0]) fl |= 1;
		if (nodes[i].style[0]) fl |= 2;
		if (nodes[i].attrs[0]) fl |= 4;
		if (nodes[i].action[0]) fl |= 8;
		w16(out, &o, nodes[i].parent < 0 ? 0xFFFF : (uint16_t)nodes[i].parent);
		out[o++] = nodes[i].tag;
		out[o++] = fl;
		w16(out, &o, rT[i]);
		w16(out, &o, rS[i]);
		w16(out, &o, rA[i]);
		w16(out, &o, rC[i]);
		out[o++] = (uint8_t)nodes[i].childCnt;
		out[o++] = 0x00;
	}

	FILE *fout = fopen(argv[2], "wb");
	if (!fout) DIE("nao escreve %s", argv[2]);
	if (fwrite(out, 1, (size_t)o, fout) != (size_t)o) { fclose(fout); DIE("falha de escrita"); }
	fclose(fout);
	printf("lint_c0 OK nos=%d strings=%d bytes=%d\n", nnodes, nstr, o);
	return 0;
}
