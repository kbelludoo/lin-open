/*
 * lin_sha256.h — SHA-256 (FIPS 180-4) for the C verifier.
 *
 * The N-Version cross-check (`tool/lin_c_xver.c`) has to produce the *same*
 * Merkle root as the Zig implementation, so the C side needs its own hash:
 * linking OpenSSL would make the "independent implementation" depend on a
 * third codebase and would not be auditable inside this repository.
 *
 * Verified against the FIPS 180-4 examples ("abc" and the 448-bit message) in
 * tool/test_sha256.c.
 */
#ifndef LIN_C_SHA256_H
#define LIN_C_SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t state[8];
    uint64_t bitlen;
    uint8_t buf[64];
    size_t buf_len;
} LinSha256;

void lin_sha256_init(LinSha256 *ctx);
void lin_sha256_update(LinSha256 *ctx, const void *data, size_t len);
void lin_sha256_final(LinSha256 *ctx, uint8_t out[32]);

/* One-shot helper. */
void lin_sha256(const void *data, size_t len, uint8_t out[32]);

/* Lowercase hex of a 32-byte digest into `out` (65 bytes, NUL-terminated). */
void lin_sha256_hex(const uint8_t digest[32], char out[65]);

#endif /* LIN_C_SHA256_H */
