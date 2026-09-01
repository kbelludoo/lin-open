/*
 * lin_bc1_run.c — host_vm driver for LINBC1 images (V1, R6 scope).
 *
 *   lin_bc1_run <image.linbc> <fn> [i64 args...]
 *   lin_bc1_run --hex <hexstring> <fn> [i64 args...]
 *   lin_bc1_run --verify <image.linbc>            (load only; prints verdict)
 *
 * Exit 0 only when the image loads AND the function evaluates. Every failure
 * path prints a REJECTED line and exits non-zero with nothing else written —
 * fail-closed, like the rest of the C11 host.
 *
 * Output line follows the xver convention so receipts stay comparable:
 *   @LIN:XVER:1.0 engine="C11-LINBC1" ... result=<i64> steps=<u64> sp_at_ret=<n>
 *   img_sha256="<hex>" img_fold=<i64> profile=<1|2>
 */
#include <stdio.h>
#include <stdlib.h>
#include "../lin_c/lin_linbc1.h"
#include "../lin_c/lin_sha256.h"

#define MAX_IMG_BYTES (256u * 1024u)

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static void rejected(const char *stage, const char *err) {
    printf("@LIN:XVER:1.0 engine=\"C11-LINBC1\" status=\"REJECTED\" stage=\"%s\" error=\"%s\"\n",
           stage, err);
}

int main(int argc, char **argv) {
    static uint8_t img[MAX_IMG_BYTES];
    static LinBc1Vm vm;
    const char *fn_name;
    size_t len = 0;
    int arg0;

    if (argc >= 3 && strcmp(argv[1], "--hex") == 0) {
        const char *h = argv[2];
        size_t hl = strlen(h), i;
        if (hl % 2 || hl / 2 > MAX_IMG_BYTES) { rejected("hex", "bad_hex"); return 3; }
        for (i = 0; i < hl / 2; i++) {
            int a = hexval((uint8_t)h[2*i]), b = hexval((uint8_t)h[2*i+1]);
            if (a < 0 || b < 0) { rejected("hex", "bad_hex"); return 3; }
            img[i] = (uint8_t)((a << 4) | b);
        }
        len = hl / 2;
        arg0 = 3;
    } else if (argc >= 3) {
        FILE *f = fopen(argv[1], "rb");
        if (!f) { rejected("read", "open_failed"); return 3; }
        len = fread(img, 1, MAX_IMG_BYTES, f);
        fclose(f);
        if (len == 0 || len == MAX_IMG_BYTES) { rejected("read", "bad_size"); return 3; }
        arg0 = 2;
    } else {
        fprintf(stderr, "usage: lin_bc1_run <image.linbc|--hex HEX> <fn> [i64 args...]\n");
        return 2;
    }

    {
        LinBc1Err e = lin_bc1_load(img, len, &vm);
        if (e != LIN_BC1_OK) {
            printf("@LIN:XVER:1.0 engine=\"C11-LINBC1\" status=\"REJECTED\" stage=\"load\" error=\"linbc1.%s\"\n",
                   lin_bc1_err_name(e));
            return 3;
        }
    }

    if (argc >= arg0 + 1 && strcmp(argv[arg0], "--verify") == 0) {
        uint8_t hex[65];
        lin_sha256_hex(vm.img_sha256, (char *)hex);
        printf("@LIN:XVER:1.0 engine=\"C11-LINBC1\" status=\"VERIFIED\" img_sha256=\"%s\" img_fold=%lld profile=%u fns=%zu bytes=%zu\n",
               (char *)hex, (long long)lin_bc1_fold_digest(vm.img_sha256),
               (unsigned)vm.profile, vm.mod.fns_len, vm.img_len);
        return 0;
    }

    if (argc < arg0 + 1) {
        fprintf(stderr, "usage: lin_bc1_run <image.linbc|--hex HEX> <fn> [i64 args...]\n");
        return 2;
    }
    fn_name = argv[arg0];

    {
        int fi = lin_bc1_find_fn(&vm, fn_name);
        int64_t fargs[64];
        size_t n_args = 0, i;
        uint64_t steps = 0;
        VmExecResult r;
        LinErr ve;
        if (fi < 0) { rejected("exec", "unknown_fn"); return 3; }
        for (i = (size_t)arg0 + 1; i < (size_t)argc && n_args < 64; i++) {
            fargs[n_args++] = strtoll(argv[i], NULL, 10);
        }
        ve = vm_exec(&vm.mod, (size_t)fi, fargs, n_args, 0, &steps, &r);
        if (ve != LIN_OK) {
            printf("@LIN:XVER:1.0 engine=\"C11-LINBC1\" status=\"REJECTED\" stage=\"exec\" error=\"%s\" steps=%llu\n",
                   lin_err_name(ve), (unsigned long long)steps);
            return 3;
        }
        uint8_t hex[65];
        lin_sha256_hex(vm.img_sha256, (char *)hex);
        printf("@LIN:XVER:1.0 engine=\"C11-LINBC1\" status=\"EVALUATED\" fn=\"%s\" result=%lld steps=%llu sp_at_ret=%zu img_sha256=\"%s\" img_fold=%lld profile=%u\n",
               fn_name, (long long)r.val, (unsigned long long)steps, r.sp_at_ret,
               (char *)hex, (long long)lin_bc1_fold_digest(vm.img_sha256),
               (unsigned)vm.profile);
    }
    return 0;
}
