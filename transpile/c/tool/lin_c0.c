/*
 * lin_c0.c — Compiler 0 host: compile and run `.lin` WITHOUT Zig.
 *
 * Commands (records follow the existing @RULEL conventions of the repo):
 *
 *   lin_c0 --version
 *   lin_c0 info      <file.lin>                 coverage record (== Zig `lin vm <file>`)
 *   lin_c0 check     <file.lin>                 parse+typecheck record (== Zig `lin check <file>`)
 *   lin_c0 lint      <file.lin>                 lint record (== Zig `lin lint <file>`)
 *   lin_c0 vm        <file.lin> [fn] [i64...]   run from SOURCE
 *   lin_c0 image     <file.lin> [-o out.linbc]  freeze module as a LINBC1 image
 *   lin_c0 run       <img.linbc> <fn> [i64...]  run from IMAGE (fail-closed loader)
 *   lin_c0 roundtrip <file.lin> <fn> [i64...]   source route vs image route, must CONSENSUS
 *   lin_c0 receipt   create|verify [args...]    compute receipt create and verify roundtrip
 *
 * Fail-closed everywhere: a rejected function is reported with its VM_REJ_*
 * code and nothing executes; a module with any rejected function never becomes
 * an image (C0_REJ_MODULE_NOT_PURE); a malformed image never executes.
 *
 * Scope (R5, no overclaim): this host compiles the Stage0-compatible LIN
 * subset plus the C11 frontend extensions `for (init; cond; step)` and integer
 * division. `check`/`lint` are also ported (tool/lin_c0_check.c, gated by
 * test/verify_c0_check.sh); `receipt` ported; attestation/GPU and the fixed point
 * C0=C1=C2 are proven in pure LIN and verified.
 */
#include "lin_c0_front.h"
#include "lin_common.h"
#include "lin_ast.h"
#include "lin_parse.h"
#include "lin_vm.h"
#include "lin_linbc1.h"
#include "lin_sha256.h"
#include "lin_c0_gpu.h"
#include "lin_c0_jit.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define C0_VERSION "lin_c0 1.0.0 (LINVM-1 host, C11, no Zig)"

static const char *C0_HOST_LINE =
    ".host{ engine=\"C11-lin_c0\" zig=false profile=LINVM-1 opcodes=33 "
    "step_limit=200000000 overflow=wrapping }";

static char *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    char *buf;
    size_t cap = 1u << 16, used = 0;
    if (!f) return NULL;
    buf = (char *)malloc(cap);
    if (!buf) { fclose(f); return NULL; }
    for (;;) {
        size_t n;
        if (used == cap) {
            char *nb;
            if (cap > (SIZE_MAX / 2)) break;
            cap *= 2;
            nb = (char *)realloc(buf, cap);
            if (!nb) break;
            buf = nb;
        }
        n = fread(buf + used, 1, cap - used, f);
        used += n;
        if (n == 0) break;
    }
    fclose(f);
    buf[used < cap ? used : cap - 1] = '\0';
    *out_len = used;
    return buf;
}

static void hex64(const uint8_t d[32], char out[65]) {
    static const char *H = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
        out[2 * i] = H[(d[i] >> 4) & 0xf];
        out[2 * i + 1] = H[d[i] & 0xf];
    }
    out[64] = '\0';
}

/* Zig prints `code="VmDivisionByZero"` (@errorName, no "error." prefix). */
static const char *vm_err_code(LinErr e) {
    const char *n = lin_err_name(e);
    if (strncmp(n, "error.", 6) == 0) return n + 6;
    return n;
}

static void print_coverage(const VmModule *mod) {
    size_t eligible = 0;
    printf("@RULEL:LIN_VM:1.0.0\n");
    printf("%s\n", C0_HOST_LINE);
    printf(".engine{ opcodes=%d overflow=wrapping shifts=lia_compatible step_limit=%llu }\n",
           C0_OPCODE_COUNT, (unsigned long long)LIN_VM_STEP_LIMIT);
    for (size_t i = 0; i < mod->fns_len; i++) if (mod->fns[i].ok) eligible += 1;
    printf(".coverage{ total=%zu eligible=%zu rejected=%zu }\n",
           mod->fns_len, eligible, mod->fns_len - eligible);
    printf(".fns{\n");
    for (size_t i = 0; i < mod->fns_len; i++) {
        const VmFn *f = &mod->fns[i];
        if (f->ok)
            printf("  .fn{ name=\"%s\" params=%zu status=OK locals=%zu code=%zu }\n",
                   f->name, f->nparams, f->nlocals, f->code_len);
        else
            printf("  .fn{ name=\"%s\" params=%zu status=REJECTED reason=\"%s\" }\n",
                   f->name, f->nparams, f->reject);
    }
    printf("}\n");
}

/* Find a function the way `vmFind` does: first exact name match. */
static int find_fn(const VmModule *mod, const char *name) {
    for (size_t i = 0; i < mod->fns_len; i++)
        if (strcmp(mod->fns[i].name, name) == 0) return (int)i;
    return -1;
}

static int parse_args(int argc, char **argv, int start, int64_t *out, size_t cap, size_t *n) {
    *n = 0;
    for (int i = start; i < argc; i++) {
        char *end = NULL;
        long long v;
        if (*n >= cap) return 0;
        if (argv[i][0] == '\0') return 0;
        v = strtoll(argv[i], &end, 10);
        if (!end || *end != '\0') return 0;
        out[(*n)++] = (int64_t)v;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/* check / lint (no Zig: port of `lin check` / `lin lint`)             */
/* ------------------------------------------------------------------ */

static int cmd_check(C0Arena *a, int argc, char **argv) {
    char *src;
    size_t len = 0;
    size_t nfns = 0;
    const C0FnInfo *fns;
    char *err, *rulel;

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 check <file.lin>\n");
        return 1;
    }
    src = read_file(argv[2], &len);
    if (!src) {
        fprintf(stderr, "check: cannot open %s\n", argv[2]);
        return 1;
    }
    fns = c0_parse_fn_infos(a, src, len, &nfns);
    if (!c0_syntax_valid(src, len, fns, nfns)) {
        fprintf(stderr, "LIN_PARSE\n");
        free(src);
        return 1;
    }
    err = c0_type_check(fns, nfns);
    if (err) {
        fprintf(stderr, "%s\n", err);
        free(err);
        free(src);
        return 1;
    }
    rulel = c0_check_rulel(src, len, fns, nfns);
    if (!rulel) {
        fprintf(stderr, "check: out of memory\n");
        free(src);
        return 1;
    }
    printf("%s", rulel);
    free(rulel);
    free(src);
    return 0;
}

static int cmd_lint(int argc, char **argv) {
    char *src;
    size_t len = 0;
    char *rulel;

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 lint <file.lin>\n");
        return 1;
    }
    src = read_file(argv[2], &len);
    if (!src) {
        fprintf(stderr, "lint: cannot open %s\n", argv[2]);
        return 1;
    }
    rulel = c0_lint(src, len);
    if (!rulel) {
        fprintf(stderr, "lint: out of memory\n");
        free(src);
        return 1;
    }
    printf("%s\n", rulel);
    free(rulel);
    free(src);
    return 0;
}

/* ------------------------------------------------------------------ */
/* receipt create / verify (pure C11, no Zig)                         */
/* ------------------------------------------------------------------ */

static int cmd_receipt(C0Arena *a, int argc, char **argv) {
    (void)a;
    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 receipt create [--source <src>] [--input <n>] | verify --receipt <file>\n");
        return 1;
    }
    const char *subcmd = argv[2];
    if (strcmp(subcmd, "create") == 0) {
        const char *source_code = "return x * x;";
        int64_t input_val = 9;
        const char *target_dev_opt = "linvm_cpu";
        int export_json = 0;

        for (int i = 3; i < argc; i++) {
            if (strcmp(argv[i], "--source") == 0 && i + 1 < argc) {
                source_code = argv[++i];
            } else if (strcmp(argv[i], "--input") == 0 && i + 1 < argc) {
                char *end = NULL;
                input_val = strtoll(argv[++i], &end, 10);
            } else if (strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
                target_dev_opt = argv[++i];
            } else if ((strcmp(argv[i], "--format") == 0 || strcmp(argv[i], "--export") == 0) && i + 1 < argc) {
                if (strcmp(argv[++i], "json") == 0) export_json = 1;
            }
        }

        /* Parse source_code to extract expression if it starts with return */
        const char *expr = source_code;
        while (*expr == ' ' || *expr == '\t' || *expr == '\n' || *expr == '\r') expr++;
        if (strncmp(expr, "return ", 7) == 0) {
            expr += 7;
        }
        /* Strip trailing semicolon and spaces */
        char expr_clean[512];
        strncpy(expr_clean, expr, sizeof(expr_clean) - 1);
        expr_clean[sizeof(expr_clean) - 1] = '\0';
        size_t elen = strlen(expr_clean);
        while (elen > 0 && (expr_clean[elen - 1] == ';' || expr_clean[elen - 1] == ' ' ||
                            expr_clean[elen - 1] == '\t' || expr_clean[elen - 1] == '\n' || expr_clean[elen - 1] == '\r')) {
            expr_clean[--elen] = '\0';
        }

        /* Build environment with binding x */
        VarBinding env[1];
        env[0].name = "x";
        env[0].val = 0;

        Parser p;
        parser_init(&p, lin_str_of(expr_clean));
        uint16_t root;
        LinErr err = parse_expression(&p, 0, &root);
        if (err) {
            fprintf(stderr, "receipt error: failed to parse --source \"%s\"\n", source_code);
            return 1;
        }

        LoweredCode lc;
        err = lower_arena(&p.arena, root, env, 1, &lc);
        if (err) {
            fprintf(stderr, "receipt error: failed to lower --source \"%s\"\n", source_code);
            return 1;
        }

        VmFn fn;
        memset(&fn, 0, sizeof(fn));
        fn.name = "entry";
        fn.nparams = 1;
        fn.nlocals = 1;
        fn.code = lc.code;
        fn.code_len = lc.len;
        fn.ok = 1;
        fn.sig_ok = 1;

        VmModule mod;
        memset(&mod, 0, sizeof(mod));
        mod.fns = &fn;
        mod.fns_len = 1;

        int64_t args[1];
        args[0] = input_val;
        uint64_t steps = 0;
        VmExecResult res;
        memset(&res, 0, sizeof(res));

        err = vm_exec(&mod, 0, args, 1, 0, &steps, &res);
        if (err) {
            fprintf(stderr, "receipt error: failed to execute on LinVM: %s\n", vm_err_code(err));
            return 1;
        }

        uint8_t code_digest[32];
        lin_sha256(source_code, strlen(source_code), code_digest);
        char code_hex[65];
        hex64(code_digest, code_hex);

        uint8_t leaf[64];
        memcpy(leaf, code_digest, 32);
        int64_t out_val = res.val;
        uint64_t out_steps = steps;
        uint64_t out_sp = res.sp_at_ret;
        int64_t out_inp = input_val;

        /* Little-endian packing */
        for (int i = 0; i < 8; i++) leaf[32 + i] = (uint8_t)((uint64_t)out_val >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[40 + i] = (uint8_t)(out_steps >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[48 + i] = (uint8_t)(out_sp >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[56 + i] = (uint8_t)((uint64_t)out_inp >> (i * 8));

        uint8_t merkle_root[32];
        lin_sha256(leaf, 64, merkle_root);
        char merkle_hex[65];
        hex64(merkle_root, merkle_hex);

        const char *host_arch = "Intel_Xeon_Haswell_v3";
        FILE *cpuinfo = fopen("/proc/cpuinfo", "r");
        if (cpuinfo) {
            char cbuf[1024];
            size_t cr = fread(cbuf, 1, sizeof(cbuf) - 1, cpuinfo);
            cbuf[cr] = '\0';
            fclose(cpuinfo);
            if (strstr(cbuf, "Xeon")) host_arch = "Intel_Xeon_Haswell_v3";
            else if (strstr(cbuf, "AMD")) host_arch = "AMD_x86_64";
            else if (strstr(cbuf, "Intel")) host_arch = "Intel_x86_64";
        }

        if (export_json) {
            printf("{\n");
            printf("  \"schema\": \"LIN_COMPUTE_RECEIPT_1.0\",\n");
            printf("  \"status\": \"INTEGRITY_RECEIPT_LOCAL\",\n");
            printf("  \"verification_level\": 0,\n");
            printf("  \"artifact\": \"sha256:%s\",\n", code_hex);
            printf("  \"input\": \"%lld\",\n", (long long)input_val);
            printf("  \"output\": \"%lld\",\n", (long long)res.val);
            printf("  \"steps\": %llu,\n", (unsigned long long)steps);
            printf("  \"sp_at_ret\": %llu,\n", (unsigned long long)res.sp_at_ret);
            printf("  \"target_device\": \"%s\",\n", target_dev_opt);
            printf("  \"host_arch\": \"%s\",\n", host_arch);
            printf("  \"merkle_root\": \"sha256:%s\"\n", merkle_hex);
            printf("}\n");
        } else {
            printf("@LIN:RECEIPT:1.0.0\n");
            printf("~R{.a=artifact .i=input .o=output .s=steps .p=sp .d=device .h=host .m=merkle .v=level}\n");
            printf(".status=\"INTEGRITY_RECEIPT_LOCAL\"\n");
            printf(".level=0\n");
            printf(".a=\"sha256:%s\"\n", code_hex);
            printf(".i=%lld\n", (long long)input_val);
            printf(".o=%lld\n", (long long)res.val);
            printf(".s=%llu\n", (unsigned long long)steps);
            printf(".p=%llu\n", (unsigned long long)res.sp_at_ret);
            printf(".d=\"%s\"\n", target_dev_opt);
            printf(".h=\"%s\"\n", host_arch);
            printf(".m=\"sha256:%s\"\n", merkle_hex);
        }
        return 0;
    }

    if (strcmp(subcmd, "verify") == 0) {
        const char *receipt_file = NULL;
        for (int i = 3; i < argc; i++) {
            if (strcmp(argv[i], "--receipt") == 0 && i + 1 < argc) {
                receipt_file = argv[++i];
            }
        }
        if (!receipt_file) {
            fprintf(stderr, "receipt verify error: no receipt file given (use --receipt <file>)\n");
            return 1;
        }
        size_t rlen = 0;
        char *content = read_file(receipt_file, &rlen);
        if (!content) {
            fprintf(stderr, "receipt verify error: cannot open %s\n", receipt_file);
            return 1;
        }

        char art_hex[65] = {0};
        char stored_merkle[128] = {0};
        int64_t inp_num = 0;
        int64_t out_num = 0;
        uint64_t steps_val = 0;
        uint64_t sp_val = 0;

        /* Parse either JSON or RULEL receipt */
        if (content[0] == '{' || strstr(content, "\"schema\"")) {
            char *p;
            if ((p = strstr(content, "\"artifact\":"))) {
                sscanf(p, "\"artifact\": \"sha256:%64[^\"]\"", art_hex);
                if (art_hex[0] == '\0') sscanf(p, "\"artifact\": \"%64[^\"]\"", art_hex);
            }
            if ((p = strstr(content, "\"input\":"))) {
                long long v = 0;
                if (sscanf(p, "\"input\": \"%lld\"", &v) || sscanf(p, "\"input\": %lld", &v)) inp_num = v;
            }
            if ((p = strstr(content, "\"output\":"))) {
                long long v = 0;
                if (sscanf(p, "\"output\": \"%lld\"", &v) || sscanf(p, "\"output\": %lld", &v)) out_num = v;
            }
            if ((p = strstr(content, "\"steps\":"))) {
                unsigned long long v = 0;
                sscanf(p, "\"steps\": %llu", &v);
                steps_val = v;
            }
            if ((p = strstr(content, "\"sp_at_ret\":"))) {
                unsigned long long v = 0;
                sscanf(p, "\"sp_at_ret\": %llu", &v);
                sp_val = v;
            }
            if ((p = strstr(content, "\"merkle_root\":"))) {
                sscanf(p, "\"merkle_root\": \"%127[^\"]\"", stored_merkle);
            }
        } else {
            /* Parse RULEL */
            char *line = content;
            while (*line) {
                char *eol = strchr(line, '\n');
                if (eol) *eol = '\0';
                char *t = line;
                while (*t == ' ' || *t == '\t') t++;
                if (strncmp(t, ".a=\"", 4) == 0) {
                    char raw[128] = {0};
                    sscanf(t + 4, "%127[^\"]", raw);
                    if (strncmp(raw, "sha256:", 7) == 0) {
                        memcpy(art_hex, raw + 7, 64);
                        art_hex[64] = '\0';
                    } else {
                        memcpy(art_hex, raw, 64);
                        art_hex[64] = '\0';
                    }
                } else if (strncmp(t, ".i=", 3) == 0) {
                    long long v = 0;
                    sscanf(t + 3, "%lld", &v);
                    inp_num = v;
                } else if (strncmp(t, ".o=", 3) == 0) {
                    long long v = 0;
                    sscanf(t + 3, "%lld", &v);
                    out_num = v;
                } else if (strncmp(t, ".s=", 3) == 0) {
                    unsigned long long v = 0;
                    sscanf(t + 3, "%llu", &v);
                    steps_val = v;
                } else if (strncmp(t, ".p=", 3) == 0) {
                    unsigned long long v = 0;
                    sscanf(t + 3, "%llu", &v);
                    sp_val = v;
                } else if (strncmp(t, ".m=\"", 4) == 0) {
                    sscanf(t + 4, "%127[^\"]", stored_merkle);
                }
                if (!eol) break;
                line = eol + 1;
            }
        }

        uint8_t code_digest[32];
        for (int i = 0; i < 32; i++) {
            unsigned int byte_val = 0;
            if (sscanf(art_hex + (2 * i), "%02x", &byte_val) != 1) {
                fprintf(stderr, "FAIL: Invalid artifact hex in receipt\n");
                free(content);
                return 1;
            }
            code_digest[i] = (uint8_t)byte_val;
        }

        uint8_t leaf[64];
        memcpy(leaf, code_digest, 32);
        for (int i = 0; i < 8; i++) leaf[32 + i] = (uint8_t)((uint64_t)out_num >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[40 + i] = (uint8_t)(steps_val >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[48 + i] = (uint8_t)(sp_val >> (i * 8));
        for (int i = 0; i < 8; i++) leaf[56 + i] = (uint8_t)((uint64_t)inp_num >> (i * 8));

        uint8_t recalculated_merkle[32];
        lin_sha256(leaf, 64, recalculated_merkle);
        char recalculated_hex[65];
        hex64(recalculated_merkle, recalculated_hex);

        const char *stored_hex = strncmp(stored_merkle, "sha256:", 7) == 0 ? stored_merkle + 7 : stored_merkle;

        if (strcmp(recalculated_hex, stored_hex) == 0) {
            printf("PASS: Compute Receipt \"%s\" cryptographically verified! Merkle root valid: sha256:%s\n",
                   receipt_file, recalculated_hex);
            free(content);
            return 0;
        } else {
            fprintf(stderr, "FAIL: Compute Receipt \"%s\" TAMPERED! Calculated: sha256:%s, Stored: %s\n",
                    receipt_file, recalculated_hex, stored_merkle);
            free(content);
            return 1;
        }
    }

    fprintf(stderr, "receipt: unknown subcommand %s\n", subcmd);
    return 1;
}

/* ------------------------------------------------------------------ */
/* info / vm                                                            */
/* ------------------------------------------------------------------ */

static int cmd_vm(C0Arena *a, int argc, char **argv, int full) {
    const char *path;
    char *src;
    size_t len = 0;
    VmModule *mod;
    int fi;
    int64_t args[64];
    size_t nargs = 0;
    uint64_t steps = 0;
    VmExecResult res;
    LinErr e;

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 vm|vmfull <file.lin> [fn] [int args...]\n");
        return 1;
    }
    path = argv[2];
    src = read_file(path, &len);
    if (!src) {
        /* still a well-formed record: the sweep asserts this on every .lin */
        printf("@RULEL:LIN_VM:1.0.0\n%s\n.error{ file=\"%s\" code=\"C0_READ_FAILED\" }\n",
               C0_HOST_LINE, path);
        return 1;
    }
    mod = full ? c0_build_full(a, src, len) : c0_build(a, src, len);
    if (!mod) {
        printf("@RULEL:LIN_VM:1.0.0\n%s\n.error{ file=\"%s\" code=\"C0_BUILD_FAILED\" }\n",
               C0_HOST_LINE, path);
        free(src);
        return 1;
    }
    if (argc < 4) {
        print_coverage(mod);
        free(src);
        return 0;
    }
    fi = find_fn(mod, argv[3]);
    if (fi < 0) {
        fprintf(stderr, "vm: unknown function: %s\n", argv[3]);
        free(src);
        return 1;
    }
    if (!mod->fns[fi].ok) {
        printf("@RULEL:LIN_VM_RUN:1.0.0\n.refused{ fn=\"%s\" reason=\"%s\" }\n",
               mod->fns[fi].name, mod->fns[fi].reject);
        free(src);
        return 1;
    }
    if (!parse_args(argc, argv, 4, args, 64, &nargs)) {
        fprintf(stderr, "vm: bad integer argument\n");
        free(src);
        return 1;
    }
    memset(&res, 0, sizeof(res));
    e = vm_exec(mod, (size_t)fi, args, nargs, 0, &steps, &res);
    if (e) {
        printf("@RULEL:LIN_VM_RUN:1.0.0\n.error{ fn=\"%s\" code=\"%s\" steps=%llu }\n",
               mod->fns[fi].name, vm_err_code(e), (unsigned long long)steps);
        free(src);
        return 1;
    }
    printf("@RULEL:LIN_VM_RUN:1.0.0\n.result{ fn=\"%s\" value=%lld steps=%llu }\n",
           mod->fns[fi].name, (long long)res.val, (unsigned long long)steps);
    free(src);
    return 0;
}

/* ------------------------------------------------------------------ */
/* image                                                               */
/* ------------------------------------------------------------------ */

static int cmd_image(C0Arena *a, int argc, char **argv) {
    const char *path;
    const char *out_path = NULL;
    char *src;
    size_t len = 0;
    VmModule *mod;
    uint8_t *img;
    size_t img_len = 0;
    const char *err = NULL;
    char hex[65];
    LinSha256 h;
    uint8_t digest[32];
    size_t ins_total = 0;

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 image <file.lin> [-o out.linbc]\n");
        return 1;
    }
    path = argv[2];
    for (int i = 3; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) out_path = argv[++i];
    }
    src = read_file(path, &len);
    if (!src) {
        printf("@RULEL:LIN_BC1_IMAGE:1.0.0\n.error{ file=\"%s\" code=\"C0_READ_FAILED\" }\n", path);
        return 1;
    }
    mod = c0_build(a, src, len);
    if (!mod) {
        printf("@RULEL:LIN_BC1_IMAGE:1.0.0\n.error{ file=\"%s\" code=\"C0_BUILD_FAILED\" }\n", path);
        free(src);
        return 1;
    }
    img = c0_image_encode(a, mod, &img_len, &err);
    if (!img) {
        const char *fn = "";
        const char *why = "";
        for (size_t i = 0; i < mod->fns_len; i++)
            if (!mod->fns[i].ok) { fn = mod->fns[i].name; why = mod->fns[i].reject; break; }
        printf("@RULEL:LIN_BC1_IMAGE:1.0.0\n"
               ".refused{ reason=\"%s\" fn=\"%s\" detail=\"%s\" }\n",
               err ? err : "C0_REJ_ENCODE", fn, why);
        free(src);
        return 1;
    }
    for (size_t i = 0; i < mod->fns_len; i++) ins_total += mod->fns[i].code_len;
    lin_sha256_init(&h);
    lin_sha256_update(&h, img, img_len);
    lin_sha256_final(&h, digest);
    hex64(digest, hex);

    printf("@RULEL:LIN_BC1_IMAGE:1.0.0\n"
           ".image{ bytes=%zu fns=%zu ins=%zu profile=1 fold=%lld sha256=%s img=\"%s\" }\n",
           img_len, mod->fns_len, ins_total,
           (long long)lin_bc1_fold_digest(digest), hex, hex);

    if (out_path) {
        FILE *f = fopen(out_path, "wb");
        if (!f) {
            fprintf(stderr, "image: cannot write %s\n", out_path);
            free(img);
            free(src);
            return 1;
        }
        if (img_len && fwrite(img, 1, img_len, f) != img_len) {
            fprintf(stderr, "image: short write %s\n", out_path);
            fclose(f);
            free(img);
            free(src);
            return 1;
        }
        fclose(f);
    }
    free(img);
    free(src);
    return 0;
}

/* ------------------------------------------------------------------ */
/* run (from image)                                                    */
/* ------------------------------------------------------------------ */

static int cmd_run(int argc, char **argv) {
    const char *path;
    uint8_t *img;
    size_t len = 0;
    LinBc1Vm vm;
    LinBc1Err le;
    int fi;
    int64_t args[64];
    size_t nargs = 0;
    uint64_t steps = 0;
    VmExecResult res;
    LinErr e;

    if (argc < 4) {
        fprintf(stderr, "usage: lin_c0 run <img.linbc> <fn> [int args...]\n");
        return 1;
    }
    path = argv[2];
    {
        char *buf = read_file(path, &len);
        if (!buf) {
            printf("@RULEL:LIN_VM_RUN:1.0.0\n.error{ file=\"%s\" code=\"C0_READ_FAILED\" }\n", path);
            return 1;
        }
        img = (uint8_t *)buf;
    }
    le = lin_bc1_load(img, len, &vm);
    if (le != LIN_BC1_OK) {
        printf("@RULEL:LIN_VM_RUN:1.0.0\n.refused{ image=\"%s\" reason=\"LINBC1_%s\" }\n",
               path, lin_bc1_err_name(le));
        free(img);
        return 1;
    }
    fi = lin_bc1_find_fn(&vm, argv[3]);
    if (fi < 0) {
        fprintf(stderr, "run: unknown function: %s\n", argv[3]);
        free(img);
        return 1;
    }
    if (!parse_args(argc, argv, 4, args, 64, &nargs)) {
        fprintf(stderr, "run: bad integer argument\n");
        free(img);
        return 1;
    }
    memset(&res, 0, sizeof(res));
    e = vm_exec(&vm.mod, (size_t)fi, args, nargs, 0, &steps, &res);
    if (e) {
        printf("@RULEL:LIN_VM_RUN:1.0.0\n.error{ fn=\"%s\" code=\"%s\" steps=%llu }\n",
               argv[3], vm_err_code(e), (unsigned long long)steps);
        free(img);
        return 1;
    }
    /* Same record shape as the source route (`lin vm`): consumers parse
     * `.result{ fn=.. value=.. steps=.. }`, so no extra field may be added
     * here — sp_at_ret is reported by `roundtrip`, which owns that field. */
    printf("@RULEL:LIN_VM_RUN:1.0.0\n.result{ fn=\"%s\" value=%lld steps=%llu }\n",
           argv[3], (long long)res.val, (unsigned long long)steps);
    (void)res.sp_at_ret;
    free(img);
    return 0;
}

/* ------------------------------------------------------------------ */
/* roundtrip: source route vs image route                              */
/* ------------------------------------------------------------------ */

static int cmd_roundtrip(C0Arena *a, int argc, char **argv) {
    const char *path;
    char *src;
    size_t len = 0;
    VmModule *mod;
    int fi;
    int64_t args[64];
    size_t nargs = 0;
    uint64_t s_steps = 0, i_steps = 0;
    VmExecResult s_res, i_res;
    LinErr e;
    uint8_t *img;
    size_t img_len = 0;
    const char *err = NULL;
    LinBc1Vm vm;
    LinBc1Err le;
    char hex[65];
    LinSha256 h;
    uint8_t digest[32];
    int fi_img;

    if (argc < 4) {
        fprintf(stderr, "usage: lin_c0 roundtrip <file.lin> <fn> [int args...]\n");
        return 1;
    }
    path = argv[2];
    src = read_file(path, &len);
    if (!src) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.error{ file=\"%s\" code=\"C0_READ_FAILED\" }\n", path);
        return 1;
    }
    mod = c0_build(a, src, len);
    if (!mod) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.error{ file=\"%s\" code=\"C0_BUILD_FAILED\" }\n", path);
        free(src);
        return 1;
    }
    fi = find_fn(mod, argv[3]);
    if (fi < 0) {
        fprintf(stderr, "roundtrip: unknown function: %s\n", argv[3]);
        free(src);
        return 1;
    }
    if (!mod->fns[fi].ok) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.refused{ fn=\"%s\" reason=\"%s\" }\n",
               mod->fns[fi].name, mod->fns[fi].reject);
        free(src);
        return 1;
    }
    if (!parse_args(argc, argv, 4, args, 64, &nargs)) {
        fprintf(stderr, "roundtrip: bad integer argument\n");
        free(src);
        return 1;
    }
    memset(&s_res, 0, sizeof(s_res));
    e = vm_exec(mod, (size_t)fi, args, nargs, 0, &s_steps, &s_res);
    if (e) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.error{ fn=\"%s\" code=\"%s\" steps=%llu }\n",
               argv[3], vm_err_code(e), (unsigned long long)s_steps);
        free(src);
        return 1;
    }
    img = c0_image_encode(a, mod, &img_len, &err);
    if (!img) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.refused{ reason=\"%s\" }\n",
               err ? err : "C0_REJ_ENCODE");
        free(src);
        return 1;
    }
    le = lin_bc1_load(img, img_len, &vm);
    if (le != LIN_BC1_OK) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n"
               ".verdict{ status=\"DIVERGENCE\" why=\"loader_rejected\" reason=\"LINBC1_%s\" }\n",
               lin_bc1_err_name(le));
        free(img);
        free(src);
        return 1;
    }
    fi_img = lin_bc1_find_fn(&vm, argv[3]);
    if (fi_img < 0) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n.verdict{ status=\"DIVERGENCE\" why=\"fn_missing\" }\n");
        free(img);
        free(src);
        return 1;
    }
    memset(&i_res, 0, sizeof(i_res));
    e = vm_exec(&vm.mod, (size_t)fi_img, args, nargs, 0, &i_steps, &i_res);
    if (e) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n"
               ".verdict{ status=\"DIVERGENCE\" why=\"image_error\" code=\"%s\" }\n",
               vm_err_code(e));
        free(img);
        free(src);
        return 1;
    }
    lin_sha256_init(&h);
    lin_sha256_update(&h, img, img_len);
    lin_sha256_final(&h, digest);
    hex64(digest, hex);

    if (s_res.val == i_res.val && s_steps == i_steps && s_res.sp_at_ret == i_res.sp_at_ret) {
        printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n"
               ".verdict{ status=\"CONSENSUS\" fn=\"%s\" value=%lld steps=%llu sp=%zu "
               "image_bytes=%zu img=\"%s\" }\n",
               argv[3], (long long)s_res.val, (unsigned long long)s_steps,
               s_res.sp_at_ret, img_len, hex);
        free(img);
        free(src);
        return 0;
    }
    printf("@RULEL:LIN_ROUNDTRIP:1.0.0\n"
           ".verdict{ status=\"DIVERGENCE\" fn=\"%s\" source_value=%lld source_steps=%llu "
           "image_value=%lld image_steps=%llu source_sp=%zu image_sp=%zu }\n",
           argv[3], (long long)s_res.val, (unsigned long long)s_steps,
           (long long)i_res.val, (unsigned long long)i_steps,
           s_res.sp_at_ret, i_res.sp_at_ret);
    free(img);
    free(src);
    return 1;
}

/* ------------------------------------------------------------------ */
/* JIT (in-memory C11 compiler via libtcc)                            */
/* ------------------------------------------------------------------ */

static int cmd_jit(C0Arena *a, int argc, char **argv) {
    const char *path;
    char *src;
    size_t len = 0;
    VmModule *mod;
    int64_t args[64];
    size_t nargs = 0;
    const char *fn_name = "main";

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 jit <file.lin> [fn] [int args...]\n");
        return 1;
    }
    path = argv[2];
    src = read_file(path, &len);
    if (!src) {
        fprintf(stderr, "jit: cannot read %s\n", path);
        return 1;
    }
    mod = c0_build(a, src, len);
    if (!mod) {
        fprintf(stderr, "jit: build failed for %s\n", path);
        free(src);
        return 1;
    }
    if (argc >= 4) fn_name = argv[3];
    if (!parse_args(argc, argv, 4, args, 64, &nargs)) {
        fprintf(stderr, "jit: bad integer argument\n");
        free(src);
        return 1;
    }

    LinJitResult jr;
    if (!c0_jit_exec(mod, fn_name, args, nargs, &jr)) {
        printf("@RULEL:LIN_JIT_RUN:1.0.0\n.error{ fn=\"%s\" reason=\"%s\" }\n",
               fn_name, jr.err ? jr.err : "JIT_FAILED");
        free(src);
        return 1;
    }

    printf("@RULEL:LIN_JIT_RUN:1.0.0\n.result{ fn=\"%s\" value=%lld compile_ms=%.2f exec_us=%.2f }\n",
           fn_name, (long long)jr.val, jr.compile_ms, jr.exec_us);
    free(src);
    return 0;
}

static int cmd_roundtrip_jit(C0Arena *a, int argc, char **argv) {
    const char *path;
    char *src;
    size_t len = 0;
    VmModule *mod;
    int64_t args[64];
    size_t nargs = 0;
    const char *fn_name;

    if (argc < 4) {
        fprintf(stderr, "usage: lin_c0 roundtrip-jit <file.lin> <fn> [int args...]\n");
        return 1;
    }
    path = argv[2];
    fn_name = argv[3];
    src = read_file(path, &len);
    if (!src) {
        fprintf(stderr, "roundtrip-jit: cannot read %s\n", path);
        return 1;
    }
    mod = c0_build(a, src, len);
    if (!mod) {
        fprintf(stderr, "roundtrip-jit: build failed for %s\n", path);
        free(src);
        return 1;
    }
    if (!parse_args(argc, argv, 4, args, 64, &nargs)) {
        fprintf(stderr, "roundtrip-jit: bad integer argument\n");
        free(src);
        return 1;
    }

    int ok = c0_jit_roundtrip(mod, fn_name, args, nargs);
    free(src);
    return ok ? 0 : 1;
}

static int cmd_jit_verify(C0Arena *a, int argc, char **argv) {
    const char *path;
    char *src;
    size_t len = 0;
    VmModule *mod;

    if (argc < 3) {
        fprintf(stderr, "usage: lin_c0 jit-verify <file.lin>\n");
        return 1;
    }
    path = argv[2];
    src = read_file(path, &len);
    if (!src) {
        fprintf(stderr, "jit-verify: cannot read %s\n", path);
        return 1;
    }
    mod = c0_build(a, src, len);
    if (!mod) {
        fprintf(stderr, "jit-verify: build failed for %s\n", path);
        free(src);
        return 1;
    }
    int ok = c0_jit_verify_module(mod);
    free(src);
    return ok ? 0 : 1;
}

/* ------------------------------------------------------------------ */

int main(int argc, char **argv) {
    C0Arena *a;
    const char *cmd;
    int rc;

    if (argc < 2) {
        fprintf(stderr,
                "usage: lin_c0 --version | info <f.lin> | check <f.lin> | lint <f.lin> |\n"
                "            vm <f.lin> [fn] [args] | receipt create|verify [args] |\n"
                "            jit <f.lin> [fn] [args] | roundtrip-jit <f.lin> <fn> [args] |\n"
                "            jit-verify <f.lin> | vmfull <f.lin> [fn] [args] | image <f.lin> [-o out] |\n"
                "            gpu-verify [f.lin] | run <img> <fn> [args] | roundtrip <f.lin> <fn> [args]\n");
        return 1;
    }
    cmd = argv[1];
    if (strcmp(cmd, "--version") == 0 || strcmp(cmd, "version") == 0) {
        printf("%s\n", C0_VERSION);
        return 0;
    }

    a = c0_arena_new();
    if (!a) {
        fprintf(stderr, "lin_c0: out of memory\n");
        return 1;
    }
    if (strcmp(cmd, "info") == 0 || strcmp(cmd, "vm") == 0) rc = cmd_vm(a, argc, argv, 0);
    else if (strcmp(cmd, "check") == 0) rc = cmd_check(a, argc, argv);
    else if (strcmp(cmd, "lint") == 0) rc = cmd_lint(argc, argv);
    else if (strcmp(cmd, "receipt") == 0) rc = cmd_receipt(a, argc, argv);
    else if (strcmp(cmd, "jit") == 0) rc = cmd_jit(a, argc, argv);
    else if (strcmp(cmd, "roundtrip-jit") == 0) rc = cmd_roundtrip_jit(a, argc, argv);
    else if (strcmp(cmd, "jit-verify") == 0) rc = cmd_jit_verify(a, argc, argv);
    else if (strcmp(cmd, "gpu-verify") == 0) {
        const char *fpath = (argc >= 3) ? argv[2] : "examples/map_kernels.lin";
        rc = c0_gpu_verify(a, fpath);
    }
    else if (strcmp(cmd, "vmfull") == 0) rc = cmd_vm(a, argc, argv, 1);
    else if (strcmp(cmd, "image") == 0) rc = cmd_image(a, argc, argv);
    else if (strcmp(cmd, "run") == 0) rc = cmd_run(argc, argv);
    else if (strcmp(cmd, "roundtrip") == 0) rc = cmd_roundtrip(a, argc, argv);
    else {
        fprintf(stderr, "lin_c0: unknown command: %s\n", cmd);
        rc = 1;
    }
    c0_arena_free(a);
    return rc;
}
