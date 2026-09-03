/*
 * test_linbc1.c — V1 gate evidence for the LINBC1 loader + HOST-ABI-1 intrinsics.
 *
 *   T-STR    the 19 golden vectors S0..S18 of docs/HOST_ABI_1.rulel §3
 *   T-IMG    golden LINBC1 fixture: accept + structure + execution goldens
 *            (lin_add(20,22)=42/4/1 mirrors the P1 sel0 golden 1:1 — the same
 *            bytecode under the same VM on two independent hosts)
 *   T-FUZZ   corrupted images must be rejected 100%, no crash:
 *              · every single-byte XOR sweep over the golden image
 *              · 4096 LCG-seeded random multi-byte mutations
 *              · 24 truncations + extension by one byte
 *
 * Exit 0 iff every suite passes. `--print-fold` prints the self-hash fold of
 * the golden fixture for the cross-host round-trip gate
 * (`make roundtrip-linbc1` compares it with the LIN emitter's own recomputed
 * fold from src/lin_linbc_emit.lin, executed by the Zig LinVM).
 */
#include <stdio.h>
#include <stdlib.h>
#include "../lin_c/lin_linbc1.h"
#include "../lin_c/lin_str.h"

static int g_pass = 0, g_fail = 0;
#define CK(cond, name) do { \
    if (cond) { g_pass++; } \
    else { g_fail++; printf("  [FAIL] %s:%d: %s\n", __FILE__, __LINE__, name); } \
} while (0)

/* ---- golden fixture image (231 bytes; reference emission verified three
 * ways: this test's exec goldens, the LIN emitter fold, and the V0 spec
 * table). Structure: profile 1, 3 fns (lin_add/sq/tri), 0 regions, 0 abis. */
#define IMG_HEX "4c494e42433101010003000000030000000000000000000000070000006c696e5f6164640200000073710300000074726900000000020200040000000100000000000000000101000000000000000300000000000000001d000000000000000001000000010100040000000100000000000000000100000000000000000500000000000000001d000000000000000002000000020200050000000100000000000000001c01000000000000000101000000000000001c00000000000000001d000000000000000066549709a549b421e166b090b621a8d9338018b2b11bf99bfd8679bc5afcf2a4"
#define IMG_BYTES 231
/* sha256("linbc1:img:" || body) = 66549709a549b421e166b090b621a8d9... */
#define IMG_FOLD_I64 (-178321285347216732LL)

static size_t unhex(const char *h, uint8_t *out, size_t cap) {
    size_t n = strlen(h) / 2, i;
    if (n > cap) return 0;
    for (i = 0; i < n; i++) {
        unsigned b;
        sscanf(h + 2*i, "%2x", &b);
        out[i] = (uint8_t)b;
    }
    return n;
}

static void t_str(void) {
    uint8_t buf[64];
    size_t n;
    CK(lin_str_len(lin_str_of("hello")) == 5, "S0");
    CK(lin_str_len(lin_str_of("")) == 0, "S1");
    CK(lin_str_char_code_at(lin_str_of("ABC"), 1) == 66, "S2");
    CK(lin_str_char_code_at(lin_str_of("ABC"), -1) == 0, "S3");
    CK(lin_str_char_code_at(lin_str_of("ABC"), 3) == 0, "S4");
    CK(lin_str_starts_lit(lin_str_of("hello world"), 6, lin_str_of("world")) == 1, "S5");
    CK(lin_str_starts_lit(lin_str_of("hello"), 3, lin_str_of("lo")) == 1, "S6");
    CK(lin_str_starts_lit(lin_str_of("hello"), 4, lin_str_of("lo")) == 0, "S7");
    CK(lin_str_starts_lit(lin_str_of("hello"), 0, lin_str_of("")) == 1, "S8");
    CK(lin_str_count_lit(lin_str_of("ababab"), lin_str_of("ab")) == 3, "S9");
    CK(lin_str_count_lit(lin_str_of("aaa"), lin_str_of("aa")) == 2, "S10");
    CK(lin_str_count_lit(lin_str_of("abc"), lin_str_of("")) == 3, "S11");
    n = lin_str_from_code(65, buf);   CK(n == 1 && buf[0] == 'A', "S12");
    n = lin_str_from_code(256, buf);  CK(n == 0, "S13");
    n = lin_str_from_code(-1, buf);   CK(n == 0, "S14");
    n = lin_str_cat(lin_str_of("a"), lin_str_of("b"), buf, sizeof buf);
    CK(n == 2 && memcmp(buf, "ab", 2) == 0, "S15");
    {
        uint8_t b1[8], b2[8], cat[16];
        size_t l1 = lin_str_of_i64(12, b1, sizeof b1), l2 = lin_str_of_i64(3, b2, sizeof b2);
        n = lin_str_cat((LinStr){ b1, l1 }, (LinStr){ b2, l2 }, cat, sizeof cat);
        CK(n == 3 && memcmp(cat, "123", 3) == 0, "S16");
    }
    n = lin_str_cat(lin_str_of("x"), lin_str_of(""), buf, sizeof buf);
    CK(n == 1 && buf[0] == 'x', "S17");
    {
        uint8_t b1[8], cat[16];
        size_t l1 = lin_str_of_i64(7, b1, sizeof b1);
        n = lin_str_cat(lin_str_of(""), (LinStr){ b1, l1 }, cat, sizeof cat);
        CK(n == 1 && cat[0] == '7', "S18");
    }
}

static void t_img_exec(void) {
    static uint8_t img[IMG_BYTES];
    static LinBc1Vm vm;
    VmExecResult r;
    LinErr e;
    uint64_t steps;
    int64_t args2[2] = {20, 22}, args1[1] = {7}, argst[2] = {7, 2};

    CK(unhex(IMG_HEX, img, sizeof img) == IMG_BYTES, "unhex");
    LinBc1Err le = lin_bc1_load(img, IMG_BYTES, &vm);
    CK(le == LIN_BC1_OK, "load ok");
    if (le != LIN_BC1_OK) { printf("  loader said linbc1.%s\n", lin_bc1_err_name(le)); return; }
    CK(vm.profile == 1, "profile==1");
    CK(vm.mod.fns_len == 3, "3 fns");
    CK(lin_bc1_find_fn(&vm, "lin_add") == 0, "find lin_add");
    CK(lin_bc1_find_fn(&vm, "sq") == 1, "find sq");
    CK(lin_bc1_find_fn(&vm, "tri") == 2, "find tri");
    CK(lin_bc1_find_fn(&vm, "nope") == -1, "find miss");
    CK(lin_bc1_fold_digest(vm.img_sha256) == IMG_FOLD_I64, "fold golden");

    steps = 0; e = vm_exec(&vm.mod, 0, args2, 2, 0, &steps, &r);
    CK(e == LIN_OK && r.val == 42 && steps == 4 && r.sp_at_ret == 1, "lin_add(20,22)=42 st=4 sp=1 (P1 sel0)");
    steps = 0; e = vm_exec(&vm.mod, 1, args1, 1, 0, &steps, &r);
    CK(e == LIN_OK && r.val == 49 && steps == 4 && r.sp_at_ret == 1, "sq(7)=49 st=4 sp=1");
    steps = 0; e = vm_exec(&vm.mod, 2, argst, 2, 0, &steps, &r);
    CK(e == LIN_OK && r.val == 51 && steps == 13 && r.sp_at_ret == 1, "tri(7,2)=51 st=13 sp=1");
    /* arity mismatch fails closed */
    steps = 0; e = vm_exec(&vm.mod, 0, args2, 1, 0, &steps, &r);
    CK(e == LIN_ERR_VM_ARITY, "arity err");
}

static void t_fuzz(void) {
    static uint8_t img[IMG_BYTES], mut[IMG_BYTES + 1];
    static LinBc1Vm vm;
    size_t rej = 0, tot = 0;

    unhex(IMG_HEX, img, sizeof img);

    /* single-byte corruption sweep (XOR 0x5A at every position) */
    for (size_t i = 0; i < IMG_BYTES; i++) {
        memcpy(mut, img, IMG_BYTES);
        mut[i] ^= 0x5A;
        tot++;
        if (lin_bc1_load(mut, IMG_BYTES, &vm) != LIN_BC1_OK) rej++;
    }
    /* multi-byte pseudo-random mutations (fixed LCG seed → deterministic) */
    {
        uint64_t s = 0x9E3779B97F4A7C15ull;
        for (int t = 0; t < 4096; t++) {
            memcpy(mut, img, IMG_BYTES);
            int flips = 1 + (int)(s % 4);
            for (int k = 0; k < flips; k++) {
                s = s * 6364136223846793005ull + 1442695040888963407ull;
                mut[(s >> 33) % IMG_BYTES] ^= (uint8_t)(1u << ((s >> 16) % 8));
            }
            tot++;
            if (lin_bc1_load(mut, IMG_BYTES, &vm) != LIN_BC1_OK) rej++;
        }
    }
    /* truncations */
    for (size_t cut_off = 0; cut_off < 24; cut_off++) {
        size_t keep = IMG_BYTES - 1 - cut_off;
        tot++;
        if (lin_bc1_load(img, keep, &vm) != LIN_BC1_OK) rej++;
    }
    /* 1-byte extension */
    memcpy(mut, img, IMG_BYTES); mut[IMG_BYTES] = 0x00;
    tot++;
    if (lin_bc1_load(mut, IMG_BYTES + 1, &vm) != LIN_BC1_OK) rej++;

    CK(rej == tot, "fuzz: 100% rejected");
    printf("  T-FUZZ: rejected %zu/%zu corrupted images\n", rej, tot);
}

static void t_length_extension(void) {
    static uint8_t img[IMG_BYTES], mut[IMG_BYTES + 64];
    static LinBc1Vm vm;
    size_t body = IMG_BYTES - 32;
    unhex(IMG_HEX, img, sizeof img);

    /* A classic length-extension candidate appends padding/suffix after the
     * original message. LINBC1 must reject it as trailing bytes, regardless of
     * whether an attacker also carries a candidate digest. */
    memcpy(mut, img, IMG_BYTES);
    mut[IMG_BYTES] = 0x80;
    mut[IMG_BYTES + 1] = 'X';
    CK(lin_bc1_load(mut, IMG_BYTES + 2, &vm) == LIN_BC1_ERR_TRAILING,
       "length extension after self_hash rejected");

    /* Put the extension before the old digest, as a forged extended message
     * would do. The fixed function section ends at body, so the loader must
     * reject the bytes before it can inspect any supplied digest. */
    memcpy(mut, img, body);
    mut[body] = 0x80;
    mut[body + 1] = 0;
    mut[body + 2] = 0;
    mut[body + 3] = 0;
    mut[body + 4] = 0;
    mut[body + 5] = 0;
    mut[body + 6] = 0;
    mut[body + 7] = 0;
    memcpy(mut + body + 8, img + body, 32);
    CK(lin_bc1_load(mut, IMG_BYTES + 8, &vm) == LIN_BC1_ERR_TRAILING,
       "length extension before self_hash rejected");

    /* Padding-looking bytes inside the protected body cannot be hidden by
     * retaining the old digest. */
    memcpy(mut, img, IMG_BYTES);
    mut[body - 1] ^= 0x01;
    CK(lin_bc1_load(mut, IMG_BYTES, &vm) == LIN_BC1_ERR_SELFHASH,
       "body mutation with old digest rejected");

    /* Mutating the stored digest itself is independently rejected. */
    memcpy(mut, img, IMG_BYTES);
    mut[body] ^= 0x01;
    CK(lin_bc1_load(mut, IMG_BYTES, &vm) == LIN_BC1_ERR_SELFHASH,
       "self_hash mutation rejected");

    printf("  T-LENEXT: padding/suffix/relocation mutations rejected\n");
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--print-fold") == 0) {
        static uint8_t img[IMG_BYTES];
        static LinBc1Vm vm;
        unhex(IMG_HEX, img, sizeof img);
        if (lin_bc1_load(img, IMG_BYTES, &vm) != LIN_BC1_OK) return 3;
        printf("%lld\n", (long long)lin_bc1_fold_digest(vm.img_sha256));
        return 0;
    }
    t_str();
    printf("  T-STR: 19 golden vectors (HOST_ABI_1 §3)\n");
    t_img_exec();
    printf("  T-IMG: fixture accept/exec goldens\n");
    t_fuzz();
    t_length_extension();
    printf("LINBC1 SUITE: %s (%d pass, %d fail)\n",
           g_fail == 0 ? "ALL PASSED" : "FAILURES", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
