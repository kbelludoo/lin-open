/*
 * lin_c0_front.h — COMPILER 0 sem Zig: fonte `.lin` -> bytecode LinVM (C11).
 *
 * Este é o front-end que faltava para a LinVM assumir o papel de
 * `compiler_0` em ambientes onde o Zig não existe. Ele é um port **fiel e
 * medido** da cadeia que vive dentro do Stage0 congelado:
 *
 *   vmTokenize            (compiler/lin.zig:5677)  -> c0_tokenize
 *   parse_fn_type_infos   (lin.zig:5287)           -> c0_scan_fns
 *   vmArrLenOf / vmSigEligible (lin.zig:6280,6291) -> c0_arr_len_of / c0_sig_eligible
 *   VmComp (expr/stmt/assign/block/ifChain) (lin.zig:5734-6270) -> c0_compile_fn
 *   vmBuild + vmResolveDeps (lin.zig:6298-6360)    -> c0_build
 *
 * Fidelidade é o contrato: mesmo bytecode canônico, mesmas razões de
 * rejeição (`VM_REJ_*`), mesma contagem de passos. As medidas estão em
 * `docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel` (gate `make c0-gate`).
 *
 * Escopo honesto (R5): isto é um SUBCONJUNTO fechador-falho (fail-closed),
 * exatamente o subconjunto que o `lin vm` do Stage0 aceita. NÃO é o
 * verificador de tipos completo (`lin check`), NÃO é o pipeline MIR/GPU, e NÃO
 * é o ponto fixo C0=C1=C2. Ver `docs/LIN_SEM_ZIG_CAMINHOS.rulel` (faixa 3).
 *
 * Colocação: `tool/` e não `lin_c/` de propósito — o host confiável da LinVM
 * (lin_c) continua o mínimo; o front-end é *compilador*, um programa que
 * emite imagens, validado por vetores dourados independentes do próprio host.
 */
#ifndef LIN_C0_FRONT_H
#define LIN_C0_FRONT_H

#include "../lin_c/lin_vm.h"

/* Limites deste front-end. São limites do HOST C11, não do dialeto: exceder é
 * rejeição determinística (`C0_LIMIT_*`), nunca UB nem truncamento silencioso.
 * Os de imagem batem com os do loader LINBC1 (lin_linbc1.h). */
#define C0_MAX_FNS        64                 /* LIN_BC1_MAX_FNS            */
#define C0_MAX_INS_TOTAL  16384              /* LIN_BC1_MAX_INS_TOTAL      */
#define C0_MAX_TOKS       16384              /* tokens por corpo de função */
#define C0_MAX_PARAMS     64
#define C0_MAX_NAME       128                /* bytes por nome (com NUL)   */
#define C0_MAX_STR_BYTES  4096               /* LIN_BC1_MAX_STR_BYTES      */

#define C0_LIMIT_FNS      "C0_LIMIT_TOO_MANY_FNS"
#define C0_LIMIT_TOKS     "C0_LIMIT_TOO_MANY_TOKENS"
#define C0_LIMIT_INS      "C0_LIMIT_TOO_MANY_INS"
#define C0_LIMIT_NAME     "C0_LIMIT_NAME_TOO_LONG"
#define C0_LIMIT_SRC      "C0_LIMIT_SOURCE_TOO_LARGE"

/* ---- Tokenizador (port de vmTokenize) ------------------------------------
 * kinds na ordem do Zig: ident, number, punct, str, eof. O texto do token
 * ALIASA o buffer de entrada (como as slices do Zig). */
typedef enum { C0_T_IDENT = 0, C0_T_NUMBER, C0_T_PUNCT, C0_T_STR, C0_T_EOF } C0TokKind;

typedef struct {
    C0TokKind kind;
    LinStr text;
} C0Tok;

/* Retorna o nº de tokens (incluindo o `eof` final), ou (size_t)-1 se `cap`
 * for excedido (falha fechada — nunca corta a metade de um corpo). */
size_t c0_tokenize(const uint8_t *src, size_t len, C0Tok *out, size_t cap);

/* ---- Varredura de assinaturas (port de parse_fn_type_infos) -------------- */
typedef struct {
    LinStr name;
    LinStr p_name[C0_MAX_PARAMS];
    LinStr p_type[C0_MAX_PARAMS];
    size_t nparams;
    LinStr ret;      /* "int" | "i64" | "any" | ... (texto após `->` ou `:`) */
    LinStr body;     /* texto entre as chaves do corpo                      */
} C0FnSig;

typedef struct {
    C0FnSig fns[C0_MAX_FNS];
    size_t n_fns;
    int truncated;   /* 1 => havia mais funções que C0_MAX_FNS (nada é aceito) */
} C0SigList;

void c0_scan_fns(const uint8_t *src, size_t len, C0SigList *out);

/* ---- Módulo compilado ---------------------------------------------------- */
typedef struct {
    VmModule mod;                         /* pronto para vm_exec           */
    VmFn fns[C0_MAX_FNS];
    VmIns ins[C0_MAX_INS_TOTAL];          /* arena única, intervalos por fn */
    size_t ins_start[C0_MAX_FNS];
    size_t ins_used;
    uint16_t arrn[C0_MAX_FNS][LIN_VM_MAX_LOCALS]; /* dense: arr_n por local   */
    char names[C0_MAX_FNS][C0_MAX_NAME];  /* cópias NUL-terminadas          */
    size_t total_fns, eligible_fns;
    const char *fatal;                    /* limite global, se houver       */
} C0Module;

/* Compila a fonte inteira (port de vmBuild + vmResolveDeps). */
void c0_build(const uint8_t *src, size_t len, C0Module *m);

/* Primeira função com esse nome (port de vmFind). -1 se ausente. */
int c0_find_fn(const C0Module *m, const char *name);

/* ---- Emissor LINBC1 (docs/LINBC1_FORMAT.rulel) ---------------------------
 * Só emite quando o módulo tem cobertura total (rejected == 0): o formato não
 * tem como expressar função rejeitada, então um módulo parcialmente aceito é
 * recusado em vez de produzir uma imagem que esconde a rejeição. */
typedef struct {
    uint8_t *out;
    size_t cap, len;
    int ok;
    const char *err;
} C0Image;

void c0_emit_linbc1(const C0Module *m, C0Image *img);

/* Exposições utilitárias (testes independentes do mesmo contrato). */
int c0_arr_len_of(LinStr ty, uint16_t *n_out);      /* vmArrLenOf; 1 = array  */
const char *c0_sig_eligible(const C0FnSig *sig);    /* NULL = apto            */

#endif /* LIN_C0_FRONT_H */
