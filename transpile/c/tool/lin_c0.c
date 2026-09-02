/*
 * lin_c0.c — COMPILER 0 sem Zig: o host da LinVM que substitui `lin vm`.
 *
 *   lin_c0 vm <file.lin> [fn] [int args...]     compila + executa (saída idêntica
 *                                               ao `lin vm` do Stage0, linha a linha)
 *   lin_c0 info <file.lin>                      cobertura + tabela de funções
 *   lin_c0 image <file.lin> [-o img.bin] [--hex]  fonte -> imagem LINBC1 congelada
 *   lin_c0 roundtrip <file.lin> <fn> [args...]  imagem -> loader -> exec == exec direto
 *   lin_c0 selftest                             vetores dourados publicados
 *
 * Por que isto existe: o bootstrap do LIN tinha como único compilador confiável
 * um binário Zig (`compiler/lin.zig`, Stage0 congelado). Onde não há Zig — sandbox
 * limpa, container mínimo, auditoria em máquina sem toolchain — a cadeia inteira
 * parava. Este driver fecha essa lacuna com o host C11: mesmo bytecode canônico,
 * mesmas rejeições, mesmos passos, medidos contra os goldens publicados do Zig
 * (docs/P1_LINVM_SELFHOST.rulel, docs/V1_LINBC1_HOST_EVIDENCE.rulel).
 *
 * Fronteira honesta (R5): o que é aceito aqui é o SUBCONJUNTO de LIN que o
 * `lin vm` do Stage0 aceita (inteiros i64 com wrap, arrays locais ≤ 8×256, sem
 * strings, sem I/O). `lin check` / typechecker completo / MIR / GPU / receipts
 * continuam sendo Stage0. Nada aqui é promovido a produção: ver
 * docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lin_c0_front.h"
#include "../lin_c/lin_linbc1.h"
#include "../lin_c/lin_sha256.h"

#define C0_SRC_CAP (8u * 1024u * 1024u)
#define C0_IMG_CAP (256u * 1024u)

static const char *c0_err_name(LinErr e) {
    switch (e) {
    case LIN_ERR_VM_STEP_LIMIT:      return "VmStepLimit";
    case LIN_ERR_VM_STACK_OVERFLOW:  return "VmStackOverflow";
    case LIN_ERR_VM_STACK_UNDERFLOW: return "VmStackUnderflow";
    case LIN_ERR_VM_BAD_FN:          return "VmBadFunction";
    case LIN_ERR_VM_DEPTH:           return "VmDepth";
    case LIN_ERR_VM_ARITY:           return "VmArity";
    case LIN_ERR_VM_DIV_ZERO:        return "VmDivisionByZero";
    default:                         return "VmError";
    }
}

static void print_host_banner(void) {
    printf(".host{ engine=\"C11-lin_c0\" zig=false subset=\"LINVM-1/i64\" spec=\"docs/LINVM_ISA_V1.rulel\" }\n");
}

/* Lê o arquivo inteiro num buffer estático (heap-free como o resto do host). */
static int read_file(const char *path, uint8_t **out, size_t *out_len) {
    static uint8_t buf[C0_SRC_CAP];
    FILE *f = fopen(path, "rb");
    size_t n;
    if (!f) return 0;
    n = fread(buf, 1, C0_SRC_CAP, f);
    fclose(f);
    if (n == 0) return 0;
    *out = buf;
    *out_len = n;
    return 1;
}

static void print_coverage(const C0Module *m) {
    size_t i, eligible = 0;
    if (m->fatal) {
        printf("@RULEL:LIN_VM:1.0.0\n");
        printf(".fatal{ reason=\"%s\" }\n", m->fatal);
        print_host_banner();
        return;
    }
    for (i = 0; i < m->total_fns; i++) if (m->fns[i].ok) eligible++;
    printf("@RULEL:LIN_VM:1.0.0\n");
    printf(".engine{ opcodes=%d overflow=wrapping shifts=lia_compatible step_limit=%llu }\n",
           33, (unsigned long long)LIN_VM_STEP_LIMIT);
    printf(".coverage{ total=%zu eligible=%zu rejected=%zu }\n",
           m->total_fns, eligible, m->total_fns - eligible);
    printf(".fns{\n");
    for (i = 0; i < m->total_fns; i++) {
        const VmFn *f = &m->fns[i];
        if (f->ok)
            printf("  .fn{ name=\"%s\" params=%zu status=OK locals=%zu code=%zu }\n",
                   f->name, f->nparams, f->nlocals, f->code_len);
        else
            printf("  .fn{ name=\"%s\" params=%zu status=REJECTED reason=\"%s\" }\n",
                   f->name, f->nparams, f->reject ? f->reject : "");
    }
    printf("}\n");
    print_host_banner();
}

static int cmd_vm(int argc, char **argv) {
    static C0Module mod;
    uint8_t *src;
    size_t len;
    int fi;
    const char *path = argv[2];

    if (!read_file(path, &src, &len)) {
        fprintf(stderr, "lin_c0: cannot read source: %s\n", path);
        return 1;
    }
    c0_build(src, len, &mod);
    if (argc < 4) { print_coverage(&mod); return mod.fatal ? 1 : 0; }
    if (mod.fatal) { print_coverage(&mod); return 1; }

    fi = c0_find_fn(&mod, argv[3]);
    if (fi < 0) {
        fprintf(stderr, "vm: unknown function: %s\n", argv[3]);
        return 1;
    }
    if (!mod.fns[fi].ok) {
        printf("@RULEL:LIN_VM_RUN:1.0.0\n");
        printf(".refused{ fn=\"%s\" reason=\"%s\" }\n", mod.fns[fi].name,
               mod.fns[fi].reject ? mod.fns[fi].reject : "");
        print_host_banner();
        return 1;
    }
    {
        int64_t args64[64];
        size_t nargs = 0;
        int k;
        uint64_t steps = 0;
        VmExecResult r;
        LinErr e;
        for (k = 4; k < argc; k++) {
            char *end = 0;
            long long v;
            if (nargs >= 64) { fprintf(stderr, "vm: too many arguments\n"); return 1; }
            v = strtoll(argv[k], &end, 10);
            if (end == argv[k] || *end != '\0') {
                fprintf(stderr, "vm: bad integer: %s\n", argv[k]);
                return 1;
            }
            args64[nargs++] = (int64_t)v;
        }
        e = vm_exec(&mod.mod, (size_t)fi, args64, nargs, 0, &steps, &r);
        if (e != LIN_OK) {
            printf("@RULEL:LIN_VM_RUN:1.0.0\n");
            printf(".error{ fn=\"%s\" code=\"%s\" steps=%llu }\n",
                   mod.fns[fi].name, c0_err_name(e), (unsigned long long)steps);
            print_host_banner();
            return 1;
        }
        printf("@RULEL:LIN_VM_RUN:1.0.0\n");
        printf(".result{ fn=\"%s\" value=%lld steps=%llu }\n",
               mod.fns[fi].name, (long long)r.val, (unsigned long long)steps);
        print_host_banner();
    }
    return 0;
}

/* ---- imagem LINBC1 ------------------------------------------------------- */
static int build_image(C0Module *mod, uint8_t *img, size_t *img_len) {
    C0Image ci;
    ci.out = img;
    ci.cap = C0_IMG_CAP;
    ci.len = 0;
    ci.ok = 0;
    ci.err = 0;
    c0_emit_linbc1(mod, &ci);
    if (!ci.ok) { *img_len = 0; return 0; }
    *img_len = ci.len;
    return 1;
}

static int cmd_image(int argc, char **argv) {
    static C0Module mod;
    static uint8_t img[C0_IMG_CAP];
    uint8_t *src;
    size_t len, img_len = 0;
    const char *out_path = 0;
    int want_hex = 0, k;
    uint8_t hex[65];
    LinBc1Err le;
    static LinBc1Vm vm;

    for (k = 2; k < argc; k++) {
        if (strcmp(argv[k], "-o") == 0 && k + 1 < argc) { out_path = argv[++k]; continue; }
        if (strcmp(argv[k], "--hex") == 0) { want_hex = 1; continue; }
        break;
    }
    if (k >= argc || strcmp(argv[1], "image") != 0) {
        fprintf(stderr, "usage: lin_c0 image <file.lin> [-o out.bin] [--hex]\n");
        return 2;
    }
    if (!read_file(argv[k], &src, &len)) { fprintf(stderr, "lin_c0: cannot read %s\n", argv[k]); return 1; }
    c0_build(src, len, &mod);
    if (mod.fatal) { printf("@RULEL:LIN_C0_IMAGE:1.0.0\n.fatal{ reason=\"%s\" }\n", mod.fatal); return 1; }
    {
        C0Image ci;
        ci.out = img; ci.cap = C0_IMG_CAP; ci.len = 0; ci.ok = 0; ci.err = 0;
        c0_emit_linbc1(&mod, &ci);
        if (!ci.ok) {
            printf("@RULEL:LIN_C0_IMAGE:1.0.0\n.refused{ reason=\"%s\" total=%zu eligible=%zu }\n",
                   ci.err, mod.total_fns, mod.eligible_fns);
            return 1;
        }
        img_len = ci.len;
    }
    /* fail-closed: a imagem só é publicada se o próprio loader a aceitar */
    le = lin_bc1_load(img, img_len, &vm);
    if (le != LIN_BC1_OK) {
        printf("@RULEL:LIN_C0_IMAGE:1.0.0\n.refused{ reason=\"loader.%s\" }\n", lin_bc1_err_name(le));
        return 1;
    }
    lin_sha256_hex(vm.img_sha256, (char *)hex);
    printf("@RULEL:LIN_C0_IMAGE:1.0.0\n");
    printf(".image{ bytes=%zu fns=%zu strings=%zu profile=%u domain=\"linbc1:img:\" }\n",
           img_len, vm.mod.fns_len, vm.mod.fns_len, (unsigned)vm.profile);
    printf(".sha256{ img=\"%s\" fold=%lld }\n", (char *)hex,
           (long long)lin_bc1_fold_digest(vm.img_sha256));
    if (out_path) {
        FILE *f = fopen(out_path, "wb");
        if (!f) { fprintf(stderr, "lin_c0: cannot write %s\n", out_path); return 1; }
        fwrite(img, 1, img_len, f);
        fclose(f);
        printf(".written{ path=\"%s\" }\n", out_path);
    }
    if (want_hex) {
        size_t i;
        printf(".hex{ bytes=\"");
        for (i = 0; i < img_len; i++) printf("%02x", img[i]);
        printf("\" }\n");
    }
    return 0;
}

/* round-trip: fonte -> imagem -> loader -> exec deve ser IDENTICO ao exec direto
 * da módulo compilado. Duas rotas, mesmo resultado; sem Zig em parte alguma. */
static int cmd_roundtrip(int argc, char **argv) {
    static C0Module mod;
    static uint8_t img[C0_IMG_CAP];
    static LinBc1Vm vm;
    uint8_t *src;
    size_t len, img_len = 0;
    int fi, vfi;
    int64_t args64[64];
    size_t nargs = 0;
    int k;
    uint64_t s1 = 0, s2 = 0;
    VmExecResult r1, r2;
    LinErr e1, e2;
    LinBc1Err le;

    if (argc < 4) { fprintf(stderr, "usage: lin_c0 roundtrip <file.lin> <fn> [int args...]\n"); return 2; }
    if (!read_file(argv[2], &src, &len)) { fprintf(stderr, "lin_c0: cannot read %s\n", argv[2]); return 1; }
    c0_build(src, len, &mod);
    if (mod.fatal) { printf("@RULEL:LIN_C0_ROUNDTRIP:1.0.0\n.fatal{ reason=\"%s\" }\n", mod.fatal); return 1; }
    fi = c0_find_fn(&mod, argv[3]);
    if (fi < 0) { fprintf(stderr, "roundtrip: unknown function: %s\n", argv[3]); return 1; }
    if (!build_image(&mod, img, &img_len)) {
        C0Image ci;
        ci.out = img; ci.cap = C0_IMG_CAP; ci.len = 0; ci.ok = 0; ci.err = 0;
        c0_emit_linbc1(&mod, &ci);
        printf("@RULEL:LIN_C0_ROUNDTRIP:1.0.0\n.refused{ reason=\"%s\" }\n", ci.err ? ci.err : "emit_failed");
        return 1;
    }
    le = lin_bc1_load(img, img_len, &vm);
    if (le != LIN_BC1_OK) {
        printf("@RULEL:LIN_C0_ROUNDTRIP:1.0.0\n.refused{ reason=\"loader.%s\" }\n", lin_bc1_err_name(le));
        return 1;
    }
    vfi = lin_bc1_find_fn(&vm, argv[3]);
    if (vfi < 0) { printf("@RULEL:LIN_C0_ROUNDTRIP:1.0.0\n.refused{ reason=\"fn_absent_in_image\" }\n"); return 1; }
    for (k = 4; k < argc && nargs < 64; k++) {
        char *end = 0;
        long long v = strtoll(argv[k], &end, 10);
        if (end == argv[k] || *end != '\0') { fprintf(stderr, "roundtrip: bad integer: %s\n", argv[k]); return 1; }
        args64[nargs++] = (int64_t)v;
    }
    e1 = vm_exec(&mod.mod, (size_t)fi, args64, nargs, 0, &s1, &r1);
    e2 = vm_exec(&vm.mod, (size_t)vfi, args64, nargs, 0, &s2, &r2);
    {
        uint8_t hex[65];
        lin_sha256_hex(vm.img_sha256, (char *)hex);
        printf("@RULEL:LIN_C0_ROUNDTRIP:1.0.0\n");
        printf(".direct{ fn=\"%s\" status=\"%s\" value=%lld steps=%llu sp=%zu }\n",
               mod.fns[fi].name, e1 ? c0_err_name(e1) : "OK",
               (long long)r1.val, (unsigned long long)s1, r1.sp_at_ret);
        printf(".image{ fn=\"%s\" status=\"%s\" value=%lld steps=%llu sp=%zu img_sha256=\"%s\" bytes=%zu }\n",
               argv[3], e2 ? c0_err_name(e2) : "OK",
               (long long)r2.val, (unsigned long long)s2, r2.sp_at_ret, (char *)hex, img_len);
    }
    if (e1 != e2 || r1.val != r2.val || s1 != s2 || r1.sp_at_ret != r2.sp_at_ret) {
        printf(".verdict{ status=\"DIVERGENCE\" }\n");
        return 1;
    }
    printf(".verdict{ status=\"CONSENSUS\" meaning=\"fonte == imagem == host C11, sem Zig\" }\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr,
            "lin_c0 — Compilador 0 da LinVM (host C11, sem Zig)\n"
            "  lin_c0 vm <file.lin> [fn] [int args...]\n"
            "  lin_c0 info <file.lin>\n"
            "  lin_c0 image <file.lin> [-o out.bin] [--hex]\n"
            "  lin_c0 roundtrip <file.lin> <fn> [int args...]\n"
            "Escopo: subconjunto LINVM-1/i64 do Stage0 (`lin vm`). Não é `lin check`.\n");
        return 2;
    }
    if (strcmp(argv[1], "vm") == 0) return cmd_vm(argc, argv);
    if (strcmp(argv[1], "info") == 0) {
        static C0Module mod;
        uint8_t *src;
        size_t len;
        if (argc < 3) { fprintf(stderr, "usage: lin_c0 info <file.lin>\n"); return 2; }
        if (!read_file(argv[2], &src, &len)) { fprintf(stderr, "lin_c0: cannot read %s\n", argv[2]); return 1; }
        c0_build(src, len, &mod);
        print_coverage(&mod);
        return mod.fatal ? 1 : 0;
    }
    if (strcmp(argv[1], "image") == 0) return cmd_image(argc, argv);
    if (strcmp(argv[1], "roundtrip") == 0) return cmd_roundtrip(argc, argv);
    if (strcmp(argv[1], "--version") == 0) {
        printf("@RULEL:LIN_C0:1.0.0\n.engine{ name=\"C11-lin_c0\" compiler_0=\"linvm\" zig=false }\n");
        return 0;
    }
    fprintf(stderr, "lin_c0: unknown command: %s\n", argv[1]);
    return 2;
}
