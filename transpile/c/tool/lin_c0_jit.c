/*
 * lin_c0_jit.c — In-Memory C11 JIT Compiler & Runner for LinVM Compiler 0.
 *
 * Implements direct in-memory C11 transpilation, compilation and execution
 * of Lin VmModule bytecode via libtcc with ZERO disk files.
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 199309L

#include "lin_c0_jit.h"
#include "lin_tcc_dyn.h"
#include "lin_common.h"
#include "lin_vm.h"
#include "lin_sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
#include <unistd.h>

typedef int64_t (*LinJitFn)(const int64_t *args);

/* Dynamic string buffer */
typedef struct {
    char *data;
    size_t len;
    size_t cap;
} StrBuf;

static void sb_init(StrBuf *sb) {
    sb->cap = 4096;
    sb->len = 0;
    sb->data = (char *)malloc(sb->cap);
    if (sb->data) sb->data[0] = '\0';
}

static void sb_ensure(StrBuf *sb, size_t extra) {
    if (sb->len + extra + 1 >= sb->cap) {
        while (sb->len + extra + 1 >= sb->cap) sb->cap *= 2;
        sb->data = (char *)realloc(sb->data, sb->cap);
    }
}

static void sb_puts(StrBuf *sb, const char *s) {
    size_t slen = strlen(s);
    sb_ensure(sb, slen);
    memcpy(sb->data + sb->len, s, slen);
    sb->len += slen;
    sb->data[sb->len] = '\0';
}

static void sb_printf(StrBuf *sb, const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n > 0) {
        sb_ensure(sb, (size_t)n);
        memcpy(sb->data + sb->len, buf, (size_t)n);
        sb->len += (size_t)n;
        sb->data[sb->len] = '\0';
    }
}

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* Sanitizes function name into a safe C identifier */
static void sanitize_fn_name(const char *in, char *out, size_t max) {
    size_t i = 0;
    while (in[i] && i < max - 1) {
        char c = in[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_') {
            out[i] = c;
        } else {
            out[i] = '_';
        }
        i++;
    }
    out[i] = '\0';
}

int c0_jit_is_available(void) {
    LinTccDyn dyn;
    if (lin_tcc_dyn_load(&dyn)) {
        lin_tcc_dyn_unload(&dyn);
        return 1;
    }
    return 0;
}

/* Transpiles a VmModule to a complete standalone C11 source string in memory */
char *c0_jit_emit_c11(const VmModule *mod) {
    if (!mod || mod->fns_len == 0) return NULL;

    StrBuf sb;
    sb_init(&sb);

    /* Hermetic In-Memory Boilerplate: zero filesystem include dependencies */
    sb_puts(&sb,
        "typedef unsigned long long uint64_t;\n"
        "typedef long long int64_t;\n"
        "typedef unsigned int uint32_t;\n"
        "typedef int int32_t;\n"
        "typedef unsigned short uint16_t;\n"
        "typedef short int16_t;\n"
        "typedef unsigned char uint8_t;\n"
        "typedef unsigned long size_t;\n"
        "#define INT64_MIN (-9223372036854775807LL - 1)\n\n"
        "static inline int64_t lin_wadd(int64_t a, int64_t b) { return (int64_t)((uint64_t)a + (uint64_t)b); }\n"
        "static inline int64_t lin_wsub(int64_t a, int64_t b) { return (int64_t)((uint64_t)a - (uint64_t)b); }\n"
        "static inline int64_t lin_wmul(int64_t a, int64_t b) { return (int64_t)((uint64_t)a * (uint64_t)b); }\n"
        "static inline int64_t lin_wdiv(int64_t x, int64_t y) {\n"
        "    if (y == 0) return 0;\n"
        "    if (x == INT64_MIN && y == -1) return INT64_MIN;\n"
        "    return x / y;\n"
        "}\n"
        "static inline int64_t lin_wrem(int64_t x, int64_t y) {\n"
        "    if (y == 0) return 0;\n"
        "    if (x == INT64_MIN && y == -1) return 0;\n"
        "    return x % y;\n"
        "}\n\n"
    );

    /* Forward declarations for all module functions */
    for (size_t fi = 0; fi < mod->fns_len; fi++) {
        const VmFn *f = &mod->fns[fi];
        if (!f->ok) continue;
        char safe_name[128];
        sanitize_fn_name(f->name, safe_name, sizeof(safe_name));
        sb_printf(&sb, "int64_t lin_fn_%s(const int64_t *args);\n", safe_name);
    }
    sb_puts(&sb, "\n");

    /* Emit each function body */
    for (size_t fi = 0; fi < mod->fns_len; fi++) {
        const VmFn *f = &mod->fns[fi];
        if (!f->ok) continue;

        char safe_name[128];
        sanitize_fn_name(f->name, safe_name, sizeof(safe_name));

        sb_printf(&sb, "int64_t lin_fn_%s(const int64_t *args) {\n", safe_name);
        sb_puts(&sb, "    int64_t locals[64] = {0};\n");
        sb_puts(&sb, "    int64_t stack[256];\n");
        sb_puts(&sb, "    size_t sp = 0;\n");

        /* Copy args into locals */
        if (f->nparams > 0) {
            sb_printf(&sb, "    if (args) {\n");
            for (size_t p = 0; p < f->nparams && p < 64; p++) {
                sb_printf(&sb, "        locals[%zu] = args[%zu];\n", p, p);
            }
            sb_printf(&sb, "    }\n");
        }

        /* Setup array storage if function uses arrays */
        if (f->arr_n_len > 0) {
            sb_puts(&sb, "    int64_t pool[8][256] = {{0}};\n");
            sb_puts(&sb, "    uint16_t pool_len[8] = {0};\n");
            sb_puts(&sb, "    size_t pool_used = 0;\n");
            for (size_t li = 0; li < f->arr_n_len; li++) {
                uint16_t an = f->arr_n[li];
                if (an > 0) {
                    sb_printf(&sb, "    if (pool_used < 8) {\n"
                                   "        size_t slot = pool_used++;\n"
                                   "        pool_len[slot] = %u;\n"
                                   "        locals[%zu] = (int64_t)slot;\n"
                                   "    }\n", (unsigned int)an, li);
                }
            }
        }

        /* Emit instruction labels and logic */
        for (size_t pc = 0; pc < f->code_len; pc++) {
            VmIns ins = f->code[pc];
            sb_printf(&sb, "pc_%zu:;\n", pc);

            switch (ins.op) {
            case OP_PUSH_CONST:
                sb_printf(&sb, "    stack[sp++] = %lldLL;\n", (long long)ins.a);
                break;

            case OP_LOAD_LOCAL:
                sb_printf(&sb, "    stack[sp++] = locals[%zu];\n", (size_t)ins.a);
                break;

            case OP_STORE_LOCAL:
                sb_printf(&sb, "    locals[%zu] = stack[--sp];\n", (size_t)ins.a);
                break;

            case OP_POP:
                sb_puts(&sb, "    if (sp > 0) sp--;\n");
                break;

            case OP_ADD:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = lin_wadd(a, b); }\n");
                break;

            case OP_SUB:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = lin_wsub(a, b); }\n");
                break;

            case OP_MUL:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = lin_wmul(a, b); }\n");
                break;

            case OP_DIV:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = lin_wdiv(a, b); }\n");
                break;

            case OP_MOD:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = lin_wrem(a, b); }\n");
                break;

            case OP_BIT_AND:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a & b); }\n");
                break;

            case OP_BIT_OR:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a | b); }\n");
                break;

            case OP_BIT_XOR:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a ^ b); }\n");
                break;

            case OP_BIT_NOT:
                sb_puts(&sb, "    stack[sp - 1] = ~stack[sp - 1];\n");
                break;

            case OP_NEG:
                sb_puts(&sb, "    stack[sp - 1] = lin_wsub(0, stack[sp - 1]);\n");
                break;

            case OP_LOG_NOT:
                sb_puts(&sb, "    stack[sp - 1] = (stack[sp - 1] == 0) ? 1 : 0;\n");
                break;

            case OP_SHL:
                sb_puts(&sb, "    { int64_t s = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (int64_t)((uint64_t)a << (s & 63)); }\n");
                break;

            case OP_SHR:
                sb_puts(&sb, "    { int64_t s = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a >> (s & 63)); }\n");
                break;

            case OP_USHR:
                sb_puts(&sb, "    { int64_t s = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (int64_t)((uint64_t)a >> (s & 63)); }\n");
                break;

            case OP_CMP_EQ:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a == b) ? 1 : 0; }\n");
                break;

            case OP_CMP_NE:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a != b) ? 1 : 0; }\n");
                break;

            case OP_CMP_LT:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a < b) ? 1 : 0; }\n");
                break;

            case OP_CMP_GT:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a > b) ? 1 : 0; }\n");
                break;

            case OP_CMP_LE:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a <= b) ? 1 : 0; }\n");
                break;

            case OP_CMP_GE:
                sb_puts(&sb, "    { int64_t b = stack[--sp]; int64_t a = stack[--sp]; stack[sp++] = (a >= b) ? 1 : 0; }\n");
                break;

            case OP_JUMP:
                sb_printf(&sb, "    goto pc_%lld;\n", (long long)ins.a);
                break;

            case OP_JUMP_IF_FALSE:
                sb_printf(&sb, "    if (stack[--sp] == 0) goto pc_%lld;\n", (long long)ins.a);
                break;

            case OP_JUMP_IF_FALSE_KEEP:
                sb_printf(&sb, "    if (stack[sp - 1] == 0) goto pc_%lld;\n", (long long)ins.a);
                break;

            case OP_JUMP_IF_TRUE_KEEP:
                sb_printf(&sb, "    if (stack[sp - 1] != 0) goto pc_%lld;\n", (long long)ins.a);
                break;

            case OP_RET:
                sb_puts(&sb, "    return (sp > 0) ? stack[sp - 1] : 0;\n");
                break;

            case OP_LOAD_INDEX:
                sb_printf(&sb,
                    "    {\n"
                    "        int64_t ix = stack[--sp];\n"
                    "        size_t slot = (size_t)locals[%zu];\n"
                    "        int64_t v = 0;\n"
                    "        if (slot < 8 && ix >= 0 && ix < (int64_t)pool_len[slot]) {\n"
                    "            v = pool[slot][(size_t)ix];\n"
                    "        }\n"
                    "        stack[sp++] = v;\n"
                    "    }\n", (size_t)ins.a);
                break;

            case OP_STORE_INDEX:
                sb_printf(&sb,
                    "    {\n"
                    "        int64_t ix = stack[sp - 2];\n"
                    "        int64_t val = stack[sp - 1];\n"
                    "        sp -= 2;\n"
                    "        size_t slot = (size_t)locals[%zu];\n"
                    "        if (slot < 8 && ix >= 0 && ix < (int64_t)pool_len[slot]) {\n"
                    "            pool[slot][(size_t)ix] = val;\n"
                    "        }\n"
                    "    }\n", (size_t)ins.a);
                break;

            case OP_ARR_LEN:
                sb_printf(&sb,
                    "    {\n"
                    "        size_t slot = (size_t)locals[%zu];\n"
                    "        stack[sp++] = (slot < 8) ? (int64_t)pool_len[slot] : 0;\n"
                    "    }\n", (size_t)ins.a);
                break;

            case OP_CALL: {
                size_t ti = (size_t)ins.a;
                if (ti < mod->fns_len) {
                    const VmFn *target = &mod->fns[ti];
                    char target_safe[128];
                    sanitize_fn_name(target->name, target_safe, sizeof(target_safe));
                    sb_printf(&sb,
                        "    {\n"
                        "        size_t np = %zu;\n"
                        "        int64_t cargs[64] = {0};\n"
                        "        for (size_t j = 0; j < np && j < 64; j++) cargs[j] = stack[sp - np + j];\n"
                        "        sp -= np;\n"
                        "        int64_t ret = lin_fn_%s(cargs);\n"
                        "        stack[sp++] = ret;\n"
                        "    }\n", target->nparams, target_safe);
                }
                break;
            }

            default:
                break;
            }
        }

        /* Safety return if control falls through */
        sb_puts(&sb, "    return (sp > 0) ? stack[sp - 1] : 0;\n");
        sb_puts(&sb, "}\n\n");
    }

    return sb.data;
}

/* Compiles a VmModule in memory via libtcc and executes the named function */
int c0_jit_exec(
    const VmModule *mod,
    const char *fn_name,
    const int64_t *args,
    size_t nargs,
    LinJitResult *out
) {
    if (!out) return 0;
    memset(out, 0, sizeof(*out));

    if (!mod || !fn_name) {
        out->err = "NULL_MODULE_OR_FN";
        return 0;
    }

    LinTccDyn dyn;
    if (!lin_tcc_dyn_load(&dyn)) {
        out->err = "LIBTCC_UNAVAILABLE";
        return 0;
    }

    /* 1. Emit C11 source string in memory */
    char *c11_src = c0_jit_emit_c11(mod);
    if (!c11_src) {
        lin_tcc_dyn_unload(&dyn);
        out->err = "C11_EMIT_FAILED";
        return 0;
    }

    /* 2. Initialize libtcc state in RAM */
    double t0_comp = get_time_sec();
    TCCState *s = dyn.tcc_new();
    if (!s) {
        free(c11_src);
        lin_tcc_dyn_unload(&dyn);
        out->err = "TCC_NEW_FAILED";
        return 0;
    }

    const char *env_tcc_dir = getenv("LIN_TCC_DIR");
    if (env_tcc_dir) {
        dyn.tcc_set_lib_path(s, env_tcc_dir);
    } else if (access("/tmp/tinycc/libtcc1.a", 0) == 0) {
        dyn.tcc_set_lib_path(s, "/tmp/tinycc");
    } else if (dyn.lib_path) {
        dyn.tcc_set_lib_path(s, "/usr/local/lib/tcc");
    }
    dyn.tcc_set_output_type(s, TCC_OUTPUT_MEMORY);

    /* 3. Compile string directly in RAM */
    if (dyn.tcc_compile_string(s, c11_src) != 0) {
        dyn.tcc_delete(s);
        free(c11_src);
        lin_tcc_dyn_unload(&dyn);
        out->err = "TCC_COMPILE_FAILED";
        return 0;
    }

    if (dyn.tcc_relocate(s) < 0) {
        dyn.tcc_delete(s);
        free(c11_src);
        lin_tcc_dyn_unload(&dyn);
        out->err = "TCC_RELOCATE_FAILED";
        return 0;
    }
    double t1_comp = get_time_sec();
    out->compile_ms = (t1_comp - t0_comp) * 1000.0;

    /* 4. Find function symbol */
    char safe_target[160];
    char safe_fn[128];
    sanitize_fn_name(fn_name, safe_fn, sizeof(safe_fn));
    snprintf(safe_target, sizeof(safe_target), "lin_fn_%s", safe_fn);

    LinJitFn fn_ptr = (LinJitFn)dyn.tcc_get_symbol(s, safe_target);
    if (!fn_ptr) {
        dyn.tcc_delete(s);
        free(c11_src);
        lin_tcc_dyn_unload(&dyn);
        out->err = "SYMBOL_NOT_FOUND";
        return 0;
    }

    /* 5. Execute native code */
    double t0_exec = get_time_sec();
    int64_t safe_args[64] = {0};
    for (size_t i = 0; i < nargs && i < 64; i++) safe_args[i] = args[i];

    int64_t val = fn_ptr(safe_args);
    double t1_exec = get_time_sec();
    out->exec_us = (t1_exec - t0_exec) * 1e6;
    out->val = val;
    out->success = 1;

    /* 6. Cleanup */
    dyn.tcc_delete(s);
    free(c11_src);
    lin_tcc_dyn_unload(&dyn);
    return 1;
}

/* Runs roundtrip between interpreted LinVM and in-memory JIT, checking consensus */
int c0_jit_roundtrip(
    const VmModule *mod,
    const char *fn_name,
    const int64_t *args,
    size_t nargs
) {
    if (!mod || !fn_name) return 0;

    int fi = -1;
    for (size_t i = 0; i < mod->fns_len; i++) {
        if (strcmp(mod->fns[i].name, fn_name) == 0) {
            fi = (int)i;
            break;
        }
    }
    if (fi < 0) {
        printf("@RULEL:LIN_JIT_ROUNDTRIP:1.0.0\n.verdict{ status=\"DIVERGENCE\" why=\"fn_not_found\" }\n");
        return 0;
    }

    /* 1. Execute on interpreted LinVM */
    uint64_t vm_steps = 0;
    VmExecResult vm_res;
    memset(&vm_res, 0, sizeof(vm_res));
    int64_t safe_args[64] = {0};
    for (size_t i = 0; i < nargs && i < 64; i++) safe_args[i] = args[i];

    LinErr err = vm_exec((VmModule *)mod, (size_t)fi, safe_args, nargs, 0, &vm_steps, &vm_res);
    if (err != LIN_OK) {
        printf("@RULEL:LIN_JIT_ROUNDTRIP:1.0.0\n.verdict{ status=\"DIVERGENCE\" why=\"vm_error\" code=\"%s\" }\n",
               lin_err_name(err));
        return 0;
    }

    /* 2. Execute on in-memory C11 JIT */
    LinJitResult jit_res;
    if (!c0_jit_exec(mod, fn_name, args, nargs, &jit_res)) {
        printf("@RULEL:LIN_JIT_ROUNDTRIP:1.0.0\n.verdict{ status=\"DIVERGENCE\" why=\"jit_error\" code=\"%s\" }\n",
               jit_res.err ? jit_res.err : "UNKNOWN");
        return 0;
    }

    /* 3. Assert consensus */
    if (vm_res.val == jit_res.val) {
        printf("@RULEL:LIN_JIT_ROUNDTRIP:1.0.0\n"
               ".verdict{ status=\"CONSENSUS\" fn=\"%s\" value=%lld vm_steps=%llu "
               "jit_compile_ms=%.2f jit_exec_us=%.2f }\n",
               fn_name, (long long)jit_res.val, (unsigned long long)vm_steps,
               jit_res.compile_ms, jit_res.exec_us);
        return 1;
    } else {
        printf("@RULEL:LIN_JIT_ROUNDTRIP:1.0.0\n"
               ".verdict{ status=\"DIVERGENCE\" fn=\"%s\" vm_value=%lld jit_value=%lld }\n",
               fn_name, (long long)vm_res.val, (long long)jit_res.val);
        return 0;
    }
}

/* Verifies all eligible functions in a module under JIT */
int c0_jit_verify_module(const VmModule *mod) {
    if (!mod) return 0;
    size_t passed = 0;
    size_t total = 0;

    for (size_t i = 0; i < mod->fns_len; i++) {
        const VmFn *f = &mod->fns[i];
        if (!f->ok) continue;
        total++;

        int64_t dummy_args[64] = {0};
        LinJitResult jr;
        if (c0_jit_exec(mod, f->name, dummy_args, f->nparams, &jr)) {
            passed++;
        }
    }
    printf("@RULEL:LIN_JIT_VERIFY:1.0.0\n.summary{ total=%zu compiled_and_run=%zu }\n", total, passed);
    return (passed == total);
}
