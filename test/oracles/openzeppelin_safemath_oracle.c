/* External GCC oracle for OpenZeppelin SafeMath try* (MIT, v4.9.6).
 * Scalar path: unsigned wrap at 2^64 (OZ uint256 algorithm on uint64).
 * u256 path: 4 little-endian uint64 words, overflow at 2^256.
 * Not linked into LIN. Compile: gcc -O2 -std=c11 this.c -o oracle
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

static int try_add_u64(uint64_t a, uint64_t b, uint64_t *out) {
    uint64_t c = a + b;
    if (c < a) { *out = 0; return 0; }
    *out = c; return 1;
}
static int try_sub_u64(uint64_t a, uint64_t b, uint64_t *out) {
    if (b > a) { *out = 0; return 0; }
    *out = a - b; return 1;
}
static int try_mul_u64(uint64_t a, uint64_t b, uint64_t *out) {
    if (a == 0) { *out = 0; return 1; }
    uint64_t c = a * b;
    if (c / a != b) { *out = 0; return 0; }
    *out = c; return 1;
}
static int try_div_u64(uint64_t a, uint64_t b, uint64_t *out) {
    if (b == 0) { *out = 0; return 0; }
    *out = a / b; return 1;
}
static int try_mod_u64(uint64_t a, uint64_t b, uint64_t *out) {
    if (b == 0) { *out = 0; return 0; }
    *out = a % b; return 1;
}

static int try_add_u256(const uint64_t a[4], const uint64_t b[4], uint64_t c[4]) {
    unsigned __int128 carry = 0;
    for (int i = 0; i < 4; i++) {
        unsigned __int128 t = (unsigned __int128)a[i] + b[i] + carry;
        c[i] = (uint64_t)t;
        carry = t >> 64;
    }
    if (carry) { memset(c, 0, 4 * sizeof(uint64_t)); return 0; }
    return 1;
}

static int try_mul_u256(const uint64_t a[4], const uint64_t b[4], uint64_t c[4]) {
    unsigned __int128 acc[8];
    int i, j;
    memset(acc, 0, sizeof(acc));
    memset(c, 0, 4 * sizeof(uint64_t));
    if (a[0] == 0 && a[1] == 0 && a[2] == 0 && a[3] == 0) return 1;
    for (i = 0; i < 4; i++) {
        unsigned __int128 carry = 0;
        for (j = 0; j < 4; j++) {
            unsigned __int128 t = acc[i + j] + (unsigned __int128)a[i] * b[j] + carry;
            acc[i + j] = (uint64_t)t;
            carry = t >> 64;
        }
        acc[i + 4] += carry;
    }
    if (acc[4] || acc[5] || acc[6] || acc[7]) return 0;
    for (i = 0; i < 4; i++) c[i] = (uint64_t)acc[i];
    return 1;
}

static int parse_u64(const char *s, uint64_t *out) {
    char *end = NULL;
    unsigned long long v = strtoull(s, &end, 10);
    if (!s[0] || (end && *end)) return 0;
    *out = (uint64_t)v;
    return 1;
}

int main(int argc, char **argv) {
    uint64_t a, b, r = 0;
    int ok;
    if (argc < 2) {
        fprintf(stderr, "usage: %s u64_add|u64_sub|u64_mul|u64_div|u64_mod a b\n"
                        "       %s u256_add|u256_mul a0 a1 a2 a3 b0 b1 b2 b3\n",
                argv[0], argv[0]);
        return 2;
    }
    if (strncmp(argv[1], "u64_", 4) == 0) {
        if (argc != 4 || !parse_u64(argv[2], &a) || !parse_u64(argv[3], &b)) return 2;
        if (strcmp(argv[1], "u64_add") == 0) ok = try_add_u64(a, b, &r);
        else if (strcmp(argv[1], "u64_sub") == 0) ok = try_sub_u64(a, b, &r);
        else if (strcmp(argv[1], "u64_mul") == 0) ok = try_mul_u64(a, b, &r);
        else if (strcmp(argv[1], "u64_div") == 0) ok = try_div_u64(a, b, &r);
        else if (strcmp(argv[1], "u64_mod") == 0) ok = try_mod_u64(a, b, &r);
        else return 2;
        printf("ok=%d result=%" PRIu64 "\n", ok, r);
        return 0;
    }
    if (argc != 10) return 2;
    {
        uint64_t aw[4], bw[4], cw[4];
        int i;
        for (i = 0; i < 4; i++) if (!parse_u64(argv[2 + i], &aw[i])) return 2;
        for (i = 0; i < 4; i++) if (!parse_u64(argv[6 + i], &bw[i])) return 2;
        if (strcmp(argv[1], "u256_add") == 0) ok = try_add_u256(aw, bw, cw);
        else if (strcmp(argv[1], "u256_mul") == 0) ok = try_mul_u256(aw, bw, cw);
        else return 2;
        printf("ok=%d w0=%" PRIu64 " w1=%" PRIu64 " w2=%" PRIu64 " w3=%" PRIu64 "\n",
               ok, cw[0], cw[1], cw[2], cw[3]);
    }
    return 0;
}
