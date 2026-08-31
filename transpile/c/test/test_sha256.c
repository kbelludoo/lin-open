/*
 * test/test_sha256.c — validates lin_sha256 against the published digests.
 *
 * Only *published* vectors are used (FIPS 180-4 examples and the NIST CAVP
 * 1,000,000-byte case). No expected value in this file was produced by the
 * implementation under test. `test/attestation_honesty.sh` additionally
 * cross-checks this implementation against Python's hashlib.
 */
#include <stdio.h>
#include <string.h>

#include "lin_sha256.h"

typedef struct {
    const char *name;
    const char *input;
    size_t len;
    const char *expected;
} Vector;

static const Vector vectors[] = {
    { "empty (FIPS)", "", 0,
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" },
    { "abc (FIPS)", "abc", 3,
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" },
    { "448-bit (FIPS)", "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", 56,
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1" },
};

int main(void) {
    size_t fail = 0;
    const size_t n = sizeof(vectors) / sizeof(vectors[0]);

    for (size_t i = 0; i < n; i++) {
        uint8_t d[32];
        char hex[65];
        lin_sha256(vectors[i].input, vectors[i].len, d);
        lin_sha256_hex(d, hex);
        const int ok = strcmp(hex, vectors[i].expected) == 0;
        printf("  [%zu/%zu] %-22s %s\n", i + 1, n + 2, vectors[i].name, ok ? "PASS" : "FAIL");
        if (!ok) {
            printf("        expected %s\n        got      %s\n", vectors[i].expected, hex);
            fail++;
        }
    }

    /* NIST CAVP: one million bytes of 'a' (multi-block + length padding). */
    {
        static char million[1000000];
        memset(million, 'a', sizeof(million));
        uint8_t d[32];
        char hex[65];
        lin_sha256(million, sizeof(million), d);
        lin_sha256_hex(d, hex);
        const char *expected = "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0";
        const int ok = strcmp(hex, expected) == 0;
        printf("  [%zu/%zu] %-22s %s\n", n + 1, n + 2, "1,000,000 x 'a'", ok ? "PASS" : "FAIL");
        if (!ok) {
            printf("        expected %s\n        got      %s\n", expected, hex);
            fail++;
        }
    }

    /* Byte-at-a-time updates must equal the one-shot call. */
    {
        const char *msg = "lin:xver:source:x * y + z";
        uint8_t a[32], b[32];
        LinSha256 ctx;
        lin_sha256_init(&ctx);
        for (const char *p = msg; *p; p++) lin_sha256_update(&ctx, p, 1);
        lin_sha256_final(&ctx, a);
        lin_sha256(msg, strlen(msg), b);
        const int ok = memcmp(a, b, 32) == 0;
        printf("  [%zu/%zu] %-22s %s\n", n + 2, n + 2, "incremental == one-shot", ok ? "PASS" : "FAIL");
        if (!ok) fail++;
    }

    printf("\nSHA-256 SUITE: %s\n", fail == 0 ? "ALL PASSED" : "FAILURES PRESENT");
    return fail == 0 ? 0 : 1;
}
