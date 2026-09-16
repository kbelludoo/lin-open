/*
 * In-process LINBC1 host for the u512 numeric coprocessor.
 * Loads one image and evaluates word APIs without respawning the VM.
 * Not part of the compiler TCB (lives under test/oracles/).
 *
 *   u512_lin_host <image.linbc> muldiv a0 a1 a2 a3 b0 b1 b2 b3 d0 d1 d2 d3
 *   u512_lin_host <image.linbc> mul a0 a1 a2 a3 b0 b1 b2 b3
 *   u512_lin_host <image.linbc> ge a0..a7 b0..b7
 *   u512_lin_host <image.linbc> div n0..n7 d0..d3
 *   u512_lin_host <image.linbc> gate
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lin_linbc1.h"
#include "lin_sha256.h"

#define MAX_IMG (256u * 1024u)

static int run_fn(LinBc1Vm *vm, const char *name, const int64_t *args, size_t nargs,
                  int64_t *val, uint64_t *steps) {
    int fi = lin_bc1_find_fn(vm, name);
    VmExecResult r;
    LinErr e;
    if (fi < 0) return -1;
    *steps = 0;
    memset(&r, 0, sizeof(r));
    e = vm_exec(&vm->mod, (size_t)fi, args, nargs, 0, steps, &r);
    if (e != LIN_OK) return -2;
    *val = r.val;
    return 0;
}

static int parse_i64(const char *s, int64_t *out) {
    char *end = NULL;
    long long v = strtoll(s, &end, 10);
    if (!s[0] || (end && *end)) return -1;
    *out = (int64_t)v;
    return 0;
}

static int load_img(const char *path, uint8_t *img, size_t *len, LinBc1Vm *vm) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    *len = fread(img, 1, MAX_IMG, f);
    fclose(f);
    if (*len == 0 || *len == MAX_IMG) return -1;
    return lin_bc1_load(img, *len, vm) == LIN_BC1_OK ? 0 : -2;
}

static void print_digest(const uint8_t d[32]) {
    int i;
    for (i = 0; i < 32; i++) printf("%02x", d[i]);
}

static int fetch_words(LinBc1Vm *vm, const char *fn, int64_t *args, size_t base_n,
                       int nwords, int64_t *outw, uint64_t *steps0) {
    int i;
    int64_t val;
    uint64_t steps;
    args[base_n] = -1;
    if (run_fn(vm, fn, args, base_n + 1, &val, &steps) != 0) return -1;
    *steps0 = steps;
    if (val != 1 && val != -1 && val != -2) return -1;
    if (val != 1) {
        for (i = 0; i < nwords; i++) outw[i] = 0;
        outw[nwords] = val;
        return 0;
    }
    for (i = 0; i < nwords; i++) {
        args[base_n] = i;
        if (run_fn(vm, fn, args, base_n + 1, &outw[i], &steps) != 0) return -1;
    }
    outw[nwords] = 1;
    return 0;
}

int main(int argc, char **argv) {
    static uint8_t img[MAX_IMG];
    static LinBc1Vm vm;
    size_t len = 0;
    const char *cmd;
    int64_t args[20];
    int64_t words[9];
    uint64_t steps = 0;
    int i, need, rc;
    int64_t val;

    if (argc < 3) {
        fprintf(stderr, "usage: u512_lin_host <image.linbc> muldiv|mul|ge|div|gate ...\n");
        return 2;
    }
    if (load_img(argv[1], img, &len, &vm) != 0) {
        fprintf(stderr, "load failed\n");
        return 3;
    }
    cmd = argv[2];
    printf("img_sha256=");
    print_digest(vm.img_sha256);
    printf(" img_bytes=%zu\n", len);

    if (strcmp(cmd, "gate") == 0) {
        rc = run_fn(&vm, "u512_self_gate", NULL, 0, &val, &steps);
        if (rc != 0) { fprintf(stderr, "gate exec failed rc=%d\n", rc); return 1; }
        printf("status=%" PRId64 " steps=%" PRIu64 "\n", val, steps);
        return val == 1 ? 0 : 1;
    }
    if (strcmp(cmd, "ge") == 0) {
        if (argc != 19) return 2;
        for (i = 0; i < 16; i++) if (parse_i64(argv[3 + i], &args[i])) return 2;
        rc = run_fn(&vm, "u512_ge", args, 16, &val, &steps);
        if (rc != 0) return 1;
        printf("ge=%" PRId64 " steps=%" PRIu64 "\n", val, steps);
        return 0;
    }
    if (strcmp(cmd, "mul") == 0) {
        if (argc != 11) return 2;
        for (i = 0; i < 8; i++) if (parse_i64(argv[3 + i], &args[i])) return 2;
        if (fetch_words(&vm, "u512_mul_word", args, 8, 8, words, &steps) != 0) return 1;
        printf("status=%" PRId64 " steps=%" PRIu64 " p=", words[8], steps);
        for (i = 7; i >= 0; i--) printf("%016" PRIx64, (uint64_t)words[i]);
        printf("\n");
        return 0;
    }
    need = (strcmp(cmd, "muldiv") == 0) ? 12 : (strcmp(cmd, "div") == 0) ? 12 : -1;
    if (need < 0 || argc != 3 + need) return 2;
    for (i = 0; i < need; i++) if (parse_i64(argv[3 + i], &args[i])) return 2;
    if (strcmp(cmd, "muldiv") == 0) {
        if (fetch_words(&vm, "u512_muldiv_word", args, 12, 8, words, &steps) != 0) return 1;
    } else {
        if (fetch_words(&vm, "u512_div_word", args, 12, 8, words, &steps) != 0) return 1;
    }
    printf("status=%" PRId64 " steps=%" PRIu64 " q=", words[8], steps);
    for (i = 3; i >= 0; i--) printf("%016" PRIx64, (uint64_t)words[i]);
    printf(" r=");
    for (i = 7; i >= 4; i--) printf("%016" PRIx64, (uint64_t)words[i]);
    printf("\n");
    return 0;
}
