/*
 * Test host: load one LINBC1 image and run many idx scans in-process.
 * Not TCB. Same vm_exec as lin_c0 run; used so remainder/q words share one load.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#include "../../transpile/c/lin_c/lin_linbc1.h"

static char *read_file(const char *path, size_t *len_out) {
    FILE *f = fopen(path, "rb");
    char *buf;
    size_t n;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    n = (size_t)ftell(f);
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    buf = (char *)malloc(n + 1);
    if (!buf) { fclose(f); return NULL; }
    if (fread(buf, 1, n, f) != n) { free(buf); fclose(f); return NULL; }
    buf[n] = 0;
    fclose(f);
    *len_out = n;
    return buf;
}

static int parse_i64(const char *s, int64_t *out) {
    char *end = NULL;
    long long v;
    if (!s || !*s) return 0;
    v = strtoll(s, &end, 10);
    if (end == s || (end && *end != '\0')) return 0;
    *out = (int64_t)v;
    return 1;
}

int main(int argc, char **argv) {
    uint8_t *img;
    size_t len = 0;
    LinBc1Vm vm;
    LinBc1Err le;
    int fi, i, scan_lo = 0, scan_hi = -1, has_scan = 0, nbase = 0;
    int64_t args[32];
    uint64_t steps, steps_total = 0;

    if (argc < 3) {
        fprintf(stderr, "usage: %s <img.linbc> <fn> [i64 args...] [--scan lo hi]\n", argv[0]);
        return 2;
    }
    img = (uint8_t *)read_file(argv[1], &len);
    if (!img) {
        fprintf(stderr, "read failed\n");
        return 1;
    }
    le = lin_bc1_load(img, len, &vm);
    if (le != LIN_BC1_OK) {
        fprintf(stderr, "linbc1 %s\n", lin_bc1_err_name(le));
        free(img);
        return 1;
    }
    fi = lin_bc1_find_fn(&vm, argv[2]);
    if (fi < 0) {
        fprintf(stderr, "unknown fn %s\n", argv[2]);
        free(img);
        return 1;
    }
    printf("img_sha256=");
    for (i = 0; i < 32; i++) printf("%02x", vm.img_sha256[i]);
    printf("\n");
    for (i = 3; i < argc; i++) {
        if (strcmp(argv[i], "--scan") == 0 && i + 2 < argc) {
            scan_lo = atoi(argv[i + 1]);
            scan_hi = atoi(argv[i + 2]);
            has_scan = 1;
            break;
        }
        if (nbase >= 32 || !parse_i64(argv[i], &args[nbase])) {
            fprintf(stderr, "bad arg %s\n", argv[i]);
            free(img);
            return 2;
        }
        nbase++;
    }
    if (!has_scan) {
        VmExecResult res;
        LinErr e;
        memset(&res, 0, sizeof(res));
        steps = 0;
        e = vm_exec(&vm.mod, (size_t)fi, args, (size_t)nbase, 0, &steps, &res);
        if (e) {
            fprintf(stderr, "vm_exec %d\n", (int)e);
            free(img);
            return 1;
        }
        printf("value=%" PRId64 " steps=%" PRIu64 "\n", (int64_t)res.val, steps);
        free(img);
        return 0;
    }
    for (i = scan_lo; i <= scan_hi; i++) {
        VmExecResult res;
        LinErr e;
        args[nbase] = (int64_t)i;
        memset(&res, 0, sizeof(res));
        steps = 0;
        e = vm_exec(&vm.mod, (size_t)fi, args, (size_t)(nbase + 1), 0, &steps, &res);
        if (e) {
            fprintf(stderr, "vm_exec idx=%d err=%d\n", i, (int)e);
            free(img);
            return 1;
        }
        steps_total += steps;
        printf("idx=%d value=%" PRId64 " steps=%" PRIu64 "\n", i, (int64_t)res.val, steps);
    }
    printf("steps_total=%" PRIu64 "\n", steps_total);
    free(img);
    return 0;
}
