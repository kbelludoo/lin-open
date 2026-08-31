/*
 * tool/lin_c_receipt.c — independent C implementation of the LIN cross-version
 * execution receipt.
 *
 * This is the "second implementation" of the N-Version check: it runs the SAME
 * expression through the C port of the LIN pipeline (tokenizer -> Pratt parser
 * -> flat AST arena -> bytecode lowerer -> LinVM interpreter) and emits a
 * canonical SHA-256 Merkle root over what it computed. The Zig side
 * (`lin crosscheck-c` in compiler/lin.zig) computes the same root from its own
 * parser/VM. Equal roots = two independently written implementations agree on
 * source, environment, bytecode, result, step count and final stack depth.
 *
 * Canonicalisation (must stay byte-identical to the Zig side):
 *
 *   env_canonical = the environment exactly as passed, e.g. "x=10,y=20,z=5"
 *   code_bytes    = for each instruction: 1 byte opcode ordinal, then the
 *                   signed 64-bit operand in little-endian
 *
 *   leaf_source = SHA256("lin:xver:source:" || expr)
 *   leaf_env    = SHA256("lin:xver:env:"    || env_canonical)
 *   leaf_code   = SHA256("lin:xver:code:"   || code_bytes)
 *   leaf_exec   = SHA256("lin:xver:exec:"   || dec(result) ":" dec(steps) ":" dec(sp_at_ret))
 *
 *   root = SHA256("node:" || SHA256("node:"||leaf_source||leaf_env)
 *                         || SHA256("node:"||leaf_code ||leaf_exec))
 *
 * Usage:
 *   lin_c_receipt --expr "x * y + z" [--env "x=10,y=20,z=5,x1=15"]
 * Exit codes: 0 = evaluated, 2 = rejected by the pipeline, 1 = bad usage.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#include "lin_common.h"
#include "lin_token.h"
#include "lin_ast.h"
#include "lin_parse.h"
#include "lin_vm.h"
#include "lin_sha256.h"

#define MAX_ENV 32

static const char DEFAULT_ENV[] = "x=10,y=20,z=5,x1=15";

static void leaf(const char *domain, const void *data, size_t len, uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, domain, strlen(domain));
    lin_sha256_update(&ctx, data, len);
    lin_sha256_final(&ctx, out);
}

static void node(const uint8_t l[32], const uint8_t r[32], uint8_t out[32]) {
    LinSha256 ctx;
    lin_sha256_init(&ctx);
    lin_sha256_update(&ctx, "node:", 5);
    lin_sha256_update(&ctx, l, 32);
    lin_sha256_update(&ctx, r, 32);
    lin_sha256_final(&ctx, out);
}

/* Parse "x=10,y=20" into bindings. Values are parsed as signed 64-bit. */
static size_t parse_env(const char *spec, VarBinding *out_names, size_t cap,
                        int64_t *vals, char (*names)[64]) {
    size_t n = 0;
    const char *p = spec;
    while (*p != '\0' && n < cap) {
        const char *eq = strchr(p, '=');
        if (eq == NULL) break;
        size_t name_len = (size_t)(eq - p);
        if (name_len == 0 || name_len >= 64) break;
        memcpy(names[n], p, name_len);
        names[n][name_len] = '\0';
        const char *val_start = eq + 1;
        char *end = NULL;
        long long v = strtoll(val_start, &end, 10);
        if (end == val_start) break;
        out_names[n].name = names[n];
        out_names[n].val = (int64_t)v;
        vals[n] = (int64_t)v;
        n++;
        p = (*end == ',') ? end + 1 : end;
        if (*end != ',' && *end != '\0') break;
    }
    return n;
}

int main(int argc, char **argv) {
    const char *expr = NULL;
    const char *env_spec = DEFAULT_ENV;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--expr") == 0 && i + 1 < argc) {
            expr = argv[++i];
        } else if (strcmp(argv[i], "--env") == 0 && i + 1 < argc) {
            env_spec = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0) {
            printf("usage: lin_c_receipt --expr \"<expr>\" [--env \"x=10,y=20\"]\n");
            return 0;
        }
    }
    if (expr == NULL) {
        fprintf(stderr, "lin_c_receipt: --expr is required\n");
        return 1;
    }

    VarBinding env[MAX_ENV];
    int64_t vals[MAX_ENV];
    char names[MAX_ENV][64];
    const size_t env_len = parse_env(env_spec, env, MAX_ENV, vals, names);

    /* 1. Parse */
    Parser p;
    parser_init(&p, lin_str_of(expr));
    uint16_t root = 0;
    LinErr err = parse_full(&p, &root);
    if (err != LIN_OK) {
        printf("@LIN:XVER:1.0 engine=\"C\" status=\"REJECTED\" stage=\"parse\" error=\"%s\" expr=\"%s\" env=\"%s\"\n",
               lin_err_name(err), expr, env_spec);
        return 2;
    }

    /* 2. AST evaluation (independent of the VM) */
    int64_t ast_val = 0;
    err = ast_arena_eval(&p.arena, root, env, env_len, &ast_val);
    if (err != LIN_OK) {
        printf("@LIN:XVER:1.0 engine=\"C\" status=\"REJECTED\" stage=\"eval\" error=\"%s\" expr=\"%s\" env=\"%s\"\n",
               lin_err_name(err), expr, env_spec);
        return 2;
    }

    /* 3. Lower to bytecode */
    LoweredCode lc;
    err = lower_arena(&p.arena, root, env, env_len, &lc);
    if (err != LIN_OK) {
        printf("@LIN:XVER:1.0 engine=\"C\" status=\"REJECTED\" stage=\"lower\" error=\"%s\" expr=\"%s\" env=\"%s\"\n",
               lin_err_name(err), expr, env_spec);
        return 2;
    }

    /* 4. Execute on the C LinVM */
    VmFn fn;
    fn.name = "xver_expr";
    fn.nparams = env_len;
    fn.nlocals = env_len;
    fn.code = lc.code;
    fn.code_len = lc.len;
    fn.sig_ok = 1;
    fn.ok = 1;
    fn.reject = "";
    fn.arr_n = NULL;
    fn.arr_n_len = 0;
    VmModule mod;
    mod.fns = &fn;
    mod.fns_len = 1;

    uint64_t steps = 0;
    VmExecResult res;
    res.val = 0;
    res.sp_at_ret = 0;
    err = vm_exec(&mod, 0, vals, env_len, 0, &steps, &res);
    if (err != LIN_OK) {
        printf("@LIN:XVER:1.0 engine=\"C\" status=\"REJECTED\" stage=\"vm\" error=\"%s\" expr=\"%s\" env=\"%s\"\n",
               lin_err_name(err), expr, env_spec);
        return 2;
    }

    /* 5. Canonical bytecode image: opcode ordinal (u8) + operand (i64 LE) */
    unsigned char code_img[LIN_LOWER_CAP * 9];
    size_t code_len = 0;
    for (size_t i = 0; i < lc.len; i++) {
        code_img[code_len++] = (unsigned char)((int)lc.code[i].op & 0xff);
        uint64_t a = (uint64_t)lc.code[i].a;
        for (int b = 0; b < 8; b++) code_img[code_len++] = (unsigned char)((a >> (8 * b)) & 0xff);
    }

    /* 6. Leaves and root */
    uint8_t leaf_source[32], leaf_env[32], leaf_code[32], leaf_exec[32];
    leaf("lin:xver:source:", expr, strlen(expr), leaf_source);
    leaf("lin:xver:env:", env_spec, strlen(env_spec), leaf_env);
    leaf("lin:xver:code:", code_img, code_len, leaf_code);

    char exec_buf[96];
    int exec_len = snprintf(exec_buf, sizeof(exec_buf), "%" PRId64 ":%" PRIu64 ":%zu",
                            res.val, steps, res.sp_at_ret);
    leaf("lin:xver:exec:", exec_buf, (size_t)exec_len, leaf_exec);

    uint8_t n01[32], n23[32], root_hash[32];
    node(leaf_source, leaf_env, n01);
    node(leaf_code, leaf_exec, n23);
    node(n01, n23, root_hash);

    char hex_root[65], hex_code[65];
    lin_sha256_hex(root_hash, hex_root);
    lin_sha256_hex(leaf_code, hex_code);

    printf("@LIN:XVER:1.0 engine=\"C\" status=\"EVALUATED\" expr=\"%s\" env=\"%s\" "
           "ast_val=%" PRId64 " result=%" PRId64 " steps=%" PRIu64 " sp_at_ret=%zu insts=%zu "
           "code_sha256=\"%s\" root=\"sha256:%s\"\n",
           expr, env_spec, ast_val, res.val, steps, res.sp_at_ret, lc.len, hex_code, hex_root);
    return 0;
}
