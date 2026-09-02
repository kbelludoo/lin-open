/*
 * test_c0_front.c — vetores dourados do COMPILER 0 sem Zig (front-end C11).
 *
 * Oráculo: o próprio fonte do Stage0. Cada valor esperado abaixo é derivado da
 * semântica de `compiler/lin.zig` (vmTokenize / VmComp / vmExecWithSp) com a
 * linha de origem anotada no vetor — o mesmo método do resto de `transpile/c`
 * ("valores copiados do fonte Zig, não da implementação testada"). Os goldens
 * medidos no binário Zig real (vms_gate, folds LINBC1, corpus GPU) estão em
 * `test/verify_c0.sh`, que roda este binário contra a fonte do repositório.
 *
 * Cobertura exigida por R6: todo delta nativo tem vetor dourado + round-trip.
 */
#include <stdio.h>
#include <string.h>

#include "../tool/lin_c0_front.h"
#include "../lin_c/lin_linbc1.h"
#include "../lin_c/lin_sha256.h"

static size_t fails = 0, checks = 0;

#define OK(cond, fmt, ...)                                                       \
    do {                                                                         \
        checks++;                                                                \
        if (!(cond)) {                                                           \
            fails++;                                                             \
            printf("  FAIL  " fmt "\n", ##__VA_ARGS__);                          \
        }                                                                        \
    } while (0)

typedef struct {
    const char *src;
    const char *fn;
    long long args[4];
    size_t nargs;
    long long want_value;
    unsigned long long want_steps;   /* 0 = não derivado à mão: não é asserido */
    size_t want_code_len;            /* 0 = idem                                */
    const char *note;
} Vec;

static void run_vec(const Vec *v) {
    static C0Module m;
    int64_t a[4];
    uint64_t steps = 0;
    VmExecResult r;
    LinErr e;
    size_t i;
    int found = -1;

    r.val = 0;
    r.sp_at_ret = 0;
    e = LIN_OK;
    c0_build((const uint8_t *)v->src, strlen(v->src), &m);
    if (m.fatal) { OK(0, "%s: fatal %s", v->note, m.fatal); return; }
    for (i = 0; i < m.total_fns; i++)
        if (strcmp(m.names[i], v->fn) == 0) found = (int)i;
    OK(found >= 0, "%s: função %s ausente", v->note, v->fn);
    if (found < 0) return;
    OK(m.fns[found].ok, "%s: rejeitada (%s)", v->note,
       m.fns[found].reject ? m.fns[found].reject : "?");
    if (!m.fns[found].ok) return;
    if (v->want_code_len)
        OK(m.fns[found].code_len == v->want_code_len, "%s: code_len=%zu esperado=%zu",
           v->note, m.fns[found].code_len, v->want_code_len);
    for (i = 0; i < v->nargs; i++) a[i] = (int64_t)v->args[i];
    e = vm_exec(&m.mod, (size_t)found, a, v->nargs, 0, &steps, &r);
    OK(e == LIN_OK, "%s: vm_exec=%s", v->note, lin_err_name(e));
    OK(r.val == (int64_t)v->want_value, "%s: value=%lld esperado=%lld",
       v->note, (long long)r.val, v->want_value);
    if (v->want_steps)
        OK(steps == v->want_steps, "%s: steps=%llu esperado=%llu",
           v->note, (unsigned long long)steps, v->want_steps);
    OK(r.sp_at_ret == 1, "%s: sp_at_ret=%zu esperado=1", v->note, r.sp_at_ret);
}

/* rejeições: o front-end tem que recusar exatamente o que o Stage0 recusa. */
typedef struct { const char *src; const char *fn; const char *want; const char *note; } RVec;

static void run_rej(const RVec *v) {
    static C0Module m;
    size_t i;
    int found = -1;
    c0_build((const uint8_t *)v->src, strlen(v->src), &m);
    for (i = 0; i < m.total_fns; i++) if (strcmp(m.names[i], v->fn) == 0) found = (int)i;
    checks++;
    if (found < 0) { fails++; printf("  FAIL  %s: função ausente\n", v->note); return; }
    if (m.fns[found].ok || strcmp(m.fns[found].reject ? m.fns[found].reject : "", v->want) != 0) {
        fails++;
        printf("  FAIL  %s: reason=\"%s\" esperado=\"%s\"\n",
               v->note, m.fns[found].ok ? "(aceita)" : m.fns[found].reject, v->want);
    }
}

int main(int argc, char **argv) {
    /* ---------------- vetores de valor (semântica = lin.zig) ------------- */
    static const Vec vecs[] = {
      { "!f(a: int, b: int) -> int {\n  ^a + b;\n}\n", "f", {20, 22}, 2, 42, 4, 6,
        "add/ret + par final (lin.zig:5906-5926, 6344)" },
      { "!sq(x: int) -> int {\n  q = x * x;\n  ^q;\n}\n", "sq", {7}, 1, 49, 6, 8,
        "store_local + mul" },
      { "!fact(n: int) -> int {\n  acc = 1;\n  while (n > 1) {\n    acc = acc * n;\n    n = n - 1;\n  };\n  ^acc;\n}\n",
        "fact", {4}, 1, 24, 47, 19,
        "while: 13 passos por iteração + condição final (lin.zig:6254-6270)" },
      { "!g(x: int) -> int {\n  ^x * x;\n}\n!h(y: int) -> int {\n  z = g(y);\n  ^z + 1;\n}\n",
        "h", {6}, 1, 37, 11, 9,
        "call: 1 passo da própria instrução + 4 do corpo chamado" },
      { "!w() -> int {\n  a: [4]int;\n  a = [10, 20, 30, 40];\n  i = 0;\n  s = 0;\n  while (i < a.length) {\n    s = s + a[i];\n    i = i + 1;\n  };\n  ^s;\n}\n",
        "w", {0}, 0, 100, 0, 0,
        "array literal + load_index + arr_len (array não atravessa call: args são i64)" },
      { "!shifts(x: int) -> int {\n  ^_lia_shl(x, 3) + _lia_shr(x, 1) + _lia_ushr(x, 1);\n}\n",
        "shifts", {5}, 1, 44, 0, 0, "opcodes 13/14/15 via _lia_* (lin.zig:6013-6021): 40+2+2" },
      { "!cmps() -> int {\n  ^1 < 2 < 3;\n}\n", "cmps", {0}, 0, 1, 0, 0,
        "comparações não transitivas: (1<2)<3 = 1, mesmo grupo de precedência" },
      { "!mask(x: int) -> int {\n  ^x & 4294967295;\n}\n", "mask", {-1}, 1, 4294967295LL, 0, 0,
        "máscara 32-bit dos helpers SHA do corpus (mask32)" },
      { "!wraps() -> int {\n  ^0 - 9223372036854775807 - 2;\n}\n", "wraps", {0}, 0,
        9223372036854775807LL, 0, 0, "wrapping i64: 0-INT64_MAX-2 embrulha para INT64_MAX (lin_wsub)" },
      { "!logic(x: int) -> int {\n  y = 0;\n  ?(x > 0) { y = 1; } : (x < 0) { y = 2; };\n  ^y * 10 + x;\n}\n",
        "logic", {-3}, 1, 17, 0, 0, "if/else-if com `:` (lin.zig:6199-6224); todo stmt de bloco exige `;`" },
      { "!lb(x: int) -> int {\n  ^x > 0 && x < 10;\n}\n", "lb", {5}, 1, 1, 0, 0,
        "jump_if_false_keep + pop (curto-circuito, lin.zig:5832-5841)" },
      { "!lb2(x: int) -> int {\n  ^x > 0 || x < -100;\n}\n", "lb2", {-500}, 1, 1, 0, 0,
        "jump_if_true_keep + pop (curto-circuito à direita)" },
      { "!tail(x: int) -> int {\n  b = x;\n  ^b\n}\n", "tail", {9}, 1, 9, 0, 0,
        "`^expr` dispensa `;` final (stmt lin.zig:6226-6232)" },
    };
    /* ---------------- rejeições (códigos canônicos do Stage0) ------------- */
    static const RVec rejects[] = {
      { "!f(a: int) -> int {\n  ^a / 2;\n}\n", "f", "VM_REJ_INT_DIVISION", "divisão inteira é rejeitada" },
      { "!f() -> int {\n  ^\"oi\";\n}\n", "f", "VM_REJ_STRING_LITERAL", "string literal" },
      { "!f() -> int {\n  ^9223372036854775808;\n}\n", "f", "VM_REJ_LITERAL_RANGE", "literal fora de i64" },
      { "!f() -> int {\n  #i = 0;\n  ^0;\n}\n", "f", "VM_REJ_FOR_LOOP", "for expandido `#`" },
      { "!f(x: int) -> int {\n  ^nope(x);\n}\n", "f", "VM_REJ_UNKNOWN_CALL", "call desconhecida" },
      { "!f(x: int) -> int {\n  ^x.y;\n}\n", "f", "VM_REJ_MEMBER_ACCESS", "acesso a membro" },
      { "!f(x: int) -> int {\n  ^zz;\n}\n", "f", "VM_REJ_UNBOUND_IDENT", "identificador não ligado" },
      { "!f(a: int) : string {\n  ^0;\n}\n", "f", "VM_REJ_RETURN_NOT_INT", "retorno não-inteiro" },
      { "!f(a: bool) -> int {\n  ^0;\n}\n", "f", "VM_REJ_PARAM_NOT_INT", "parâmetro não-inteiro" },
      { "!f(x: [300]int) -> int {\n  ^0;\n}\n", "f", "VM_REJ_ARRAY_TOO_LARGE", "array > 256" },
      { "!f() -> int {\n  a: [4]int;\n  ^a;\n}\n", "f", "VM_REJ_ARRAY_AS_SCALAR", "array como escalar" },
      { "!f() -> int {\n  a: [4]int;\n  ^a.length2;\n}\n", "f", "VM_REJ_MEMBER_ACCESS", "membro que não é length" },
      { "!g(a: int) -> int {\n  ^a;\n}\n!f(x: int) -> int {\n  ^g(x, x);\n}\n", "f", "VM_REJ_ARITY", "aridade errada" },
      { "!bad(x: int) -> int {\n  ^x / 2;\n}\n!uses(x: int) -> int {\n  ^bad(x);\n}\n", "uses", "VM_REJ_DEP_REJECTED",
        "dependência rejeitada contamina o chamador (vmResolveDeps lin.zig:6330)" },
      { "!f(a: int) -> int {\n  b = 1;\n  c = 2\n}\n", "f", "VM_REJ_PARSE", "statement de atribuição sem `;`" },
      { "!f(a: int) -> int {\n  b = 1\n  ^b + a;\n}\n", "f", "VM_REJ_UNBOUND_IDENT",
        "`^` depois de expressão é bit_xor, não o sigil: `b` ainda não é local" },
      { "!f(a: int) -> int {\n  a: [0]int;\n  ^0;\n}\n", "f", "VM_REJ_ARRAY_TOO_LARGE", "array de tamanho 0" },
      { "!f(a) -> int {\n  ^a;\n}\n", "f", "VM_REJ_PARAM_NOT_INT", "parâmetro sem tipo (any)" },
    };
    size_t i;

    printf("@RULEL:LIN_C0_TEST:1.0.0\n.vectors{ values=%zu rejections=%zu }\n",
           sizeof(vecs) / sizeof(vecs[0]), sizeof(rejects) / sizeof(rejects[0]));
    for (i = 0; i < sizeof(vecs) / sizeof(vecs[0]); i++) run_vec(&vecs[i]);
    for (i = 0; i < sizeof(rejects) / sizeof(rejects[0]); i++) run_rej(&rejects[i]);

    /* ---- imagem LINBC1: determinismo, loader fail-closed, round-trip ----- */
    {
        static C0Module m;
        static uint8_t img[16384], img2[16384];
        C0Image ci, ci2;
        static LinBc1Vm vm;
        LinBc1Err le;
        const char *src = "!f(a: int, b: int) -> int {\n  ^a + b;\n}\n!s(x: int) -> int {\n  y = x * x;\n  ^y;\n}\n";
        c0_build((const uint8_t *)src, strlen(src), &m);
        ci.out = img; ci.cap = sizeof img; ci.len = 0; ci.ok = 0; ci.err = 0;
        ci2.out = img2; ci2.cap = sizeof img2; ci2.len = 0; ci2.ok = 0; ci2.err = 0;
        c0_emit_linbc1(&m, &ci);
        c0_emit_linbc1(&m, &ci2);
        OK(ci.ok, "emissão de imagem falhou (%s)", ci.err ? ci.err : "?");
        OK(ci.len == ci2.len && memcmp(img, img2, ci.len) == 0,
           "imagem não é byte-reproduzível");
        le = lin_bc1_load(img, ci.len, &vm);
        OK(le == LIN_BC1_OK, "loader rejeitou imagem válida (%s)", lin_bc1_err_name(le));
        if (le == LIN_BC1_OK) {
            int64_t args[2] = { 20, 22 };
            uint64_t steps = 0;
            VmExecResult r;
            int fi = lin_bc1_find_fn(&vm, "f");
            OK(fi == 0, "índice da função na imagem: %d", fi);
            OK(vm_exec(&vm.mod, (size_t)(fi < 0 ? 0 : fi), args, 2, 0, &steps, &r) == LIN_OK &&
               r.val == 42 && steps == 4,
               "execução via imagem divergiu (value=%lld steps=%llu)",
               (long long)r.val, (unsigned long long)steps);
            /* mutação de 1 byte: nenhuma pode ser aceita (fail-closed) */
            {
                size_t k, accepted = 0, bites = 0;
                for (k = 0; k < ci.len && k < 64; k++) {
                    static LinBc1Vm v2;
                    uint8_t save = img[k];
                    img[k] ^= 0x81;
                    bites++;
                    if (lin_bc1_load(img, ci.len, &v2) == LIN_BC1_OK) accepted++;
                    img[k] = save;
                }
                OK(accepted == 0, "imagem corrompida aceita: %zu/%zu mutações", accepted, bites);
            }
        }
        /* módulo com função rejeitada => nenhuma imagem sai (nada escondido) */
        {
            static C0Module m2;
            C0Image ci3;
            static uint8_t buf[4096];
            const char *dirty = "!ok(a: int) -> int {\n  ^a;\n}\n!bad(x: int) -> int {\n  ^x / 2;\n}\n";
            c0_build((const uint8_t *)dirty, strlen(dirty), &m2);
            ci3.out = buf; ci3.cap = sizeof buf; ci3.len = 0; ci3.ok = 0; ci3.err = 0;
            c0_emit_linbc1(&m2, &ci3);
            OK(!ci3.ok && ci3.err && strcmp(ci3.err, "C0_REJ_MODULE_NOT_PURE") == 0,
               "módulo parcialmente coberto emitiu imagem (=%s)", ci3.err ? ci3.err : "ok");
            OK(ci3.len == 0, "imagem parcial foi escrita (%zu bytes)", ci3.len);
        }
    }

    /* ---- limites do host: fail-closed, nunca truncamento silencioso ------ */
    {
        static C0Module m;
        char big[8192];
        size_t n = 0, k;
        n += (size_t)snprintf(big + n, sizeof big - n, "!f() -> int {\n");
        for (k = 0; k < 70 && n + 40 < sizeof big; k++)
            n += (size_t)snprintf(big + n, sizeof big - n, "  v%zu = %zu;\n", k, k);
        n += (size_t)snprintf(big + n, sizeof big - n, "  ^0;\n}\n");
        c0_build((const uint8_t *)big, n, &m);
        OK(m.total_fns == 1 && !m.fns[0].ok &&
           strcmp(m.fns[0].reject, "VM_REJ_TOO_MANY_LOCALS") == 0,
           "64+ locais: reason=\"%s\" (esperado VM_REJ_TOO_MANY_LOCALS)",
           m.fns[0].ok ? "(aceita)" : m.fns[0].reject);
    }

    if (argc > 1 && strcmp(argv[1], "--quiet") == 0 && fails == 0)
        printf("c0-front: OK (%zu checks)\n", checks);
    else
        printf(".verdict{ checks=%zu failures=%zu status=\"%s\" }\n",
               checks, fails, fails ? "FAILED" : "PASSED");
    return fails ? 1 : 0;
}
