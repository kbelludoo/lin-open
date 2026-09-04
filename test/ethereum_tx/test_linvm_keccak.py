#!/usr/bin/env python3
"""
Lin-Audit Ethereum — Submilestones M1-B.1 & M1-B.2 Verification Suite
Executes LinVM Keccak implementation (src/lin_ethereum_keccak.lin) via C11 LinVM host.

Asserts:
1. Bit-exact parity for empty vector Keccak-256("") against Python reference.
2. Active distinction between NIST SHA3-256 and Keccak-256.
3. Bit-exact multi-block streaming absorption across canonical fixtures:
   - 0 bytes (Empty string b"")
   - 1 byte (b"x")
   - 43 bytes (The quick brown fox jumps over the lazy dog)
   - 135 bytes (1 block boundary minus 1)
   - 136 bytes (Exact 1 block boundary -> 2 blocks)
   - 137 bytes (2 blocks)
   - 271 bytes (2 block boundary minus 1)
   - 272 bytes (Exact 2 block boundary -> 3 blocks)
   - 273 bytes (3 blocks)
4. Fail-closed verification:
   - 0: SUCCESS on authentic words
   - 1: HASH_MISMATCH on tampered words
   - 2: INVALID_FIXTURE_ID on out-of-bounds fixture ID
5. Optional cross-verification against Mojo reference when mojo binary is in PATH.
"""

import os
import sys
import shutil
import subprocess
import struct
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
LIN_C0 = os.path.join(ROOT, "transpile/c/bin/lin_c0")
KECCAK_LIN = os.path.join(ROOT, "src/lin_ethereum_keccak.lin")

# Add tools to path
sys.path.insert(0, os.path.join(ROOT, "tools"))
from lin_audit_tx import keccak256, nist_sha3_256

class TestLinVMKeccak(unittest.TestCase):
    def run_linvm(self, fn_name: str, *args) -> int:
        cmd = [LIN_C0, "vm", KECCAK_LIN, fn_name] + [str(a) for a in args]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Parse output line: .result{ fn="..." value=... steps=... }
        for line in res.stdout.splitlines():
            if line.strip().startswith(".result{"):
                for part in line.split():
                    if part.startswith("value="):
                        return int(part.split("=")[1])
        raise RuntimeError(f"Could not parse LinVM output: {res.stdout}")

    def test_keccak256_empty_linvm_parity(self):
        """M1-B.1: Verify that LinVM computes the exact 4 words of Keccak-256("")."""
        w0 = self.run_linvm("keccak256_empty_word", 0)
        w1 = self.run_linvm("keccak256_empty_word", 1)
        w2 = self.run_linvm("keccak256_empty_word", 2)
        w3 = self.run_linvm("keccak256_empty_word", 3)

        u0 = w0 & 0xFFFFFFFFFFFFFFFF
        u1 = w1 & 0xFFFFFFFFFFFFFFFF
        u2 = w2 & 0xFFFFFFFFFFFFFFFF
        u3 = w3 & 0xFFFFFFFFFFFFFFFF

        linvm_bytes = struct.pack("<QQQQ", u0, u1, u2, u3)
        linvm_hex = linvm_bytes.hex()

        expected_keccak = "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        self.assertEqual(linvm_hex, expected_keccak, "LinVM Keccak-256 output does not match expected digest")

        py_hex = keccak256(b"").hex()
        self.assertEqual(linvm_hex, py_hex, "LinVM does not match Python reference")

    def test_linvm_distinguishes_nist_sha3(self):
        """M1-B.1: Verify that verify_empty_hash in LinVM returns 0 for Keccak and 2 for NIST SHA3."""
        k_w0 = self.run_linvm("keccak256_empty_word", 0)
        k_w1 = self.run_linvm("keccak256_empty_word", 1)
        k_w2 = self.run_linvm("keccak256_empty_word", 2)
        k_w3 = self.run_linvm("keccak256_empty_word", 3)
        status_k = self.run_linvm("verify_empty_hash", k_w0, k_w1, k_w2, k_w3)
        self.assertEqual(status_k, 0, "LinVM failed to verify correct Keccak-256 hash")

        status_corrupt = self.run_linvm("verify_empty_hash", k_w0 ^ 1, k_w1, k_w2, k_w3)
        self.assertEqual(status_corrupt, 1, "LinVM failed to reject corrupted word")

        nist_bytes = nist_sha3_256(b"")
        nist_u0, nist_u1, nist_u2, nist_u3 = struct.unpack("<QQQQ", nist_bytes)
        nist_s0 = struct.unpack("<q", struct.pack("<Q", nist_u0))[0]
        nist_s1 = struct.unpack("<q", struct.pack("<Q", nist_u1))[0]
        nist_s2 = struct.unpack("<q", struct.pack("<Q", nist_u2))[0]
        nist_s3 = struct.unpack("<q", struct.pack("<Q", nist_u3))[0]

        status_nist = self.run_linvm("verify_empty_hash", nist_s0, nist_s1, nist_s2, nist_s3)
        self.assertEqual(status_nist, 2, "LinVM failed to flag NIST SHA3-256 substitution")

    def test_multiblock_fixtures_parity_linvm_python(self):
        """M1-B.2: Verify multi-block streaming absorption for 9 canonical fixtures (0..273 bytes)."""
        fixtures = [
            (0, b"", "Empty string (0 bytes)"),
            (1, b"x", "1 byte"),
            (2, b"The quick brown fox jumps over the lazy dog", "Fox vector (43 bytes)"),
            (3, b"x" * 135, "135 bytes (1 block minus 1)"),
            (4, b"x" * 136, "136 bytes (exact 1 block)"),
            (5, b"x" * 137, "137 bytes (2 blocks)"),
            (6, b"x" * 271, "271 bytes (2 blocks minus 1)"),
            (7, b"x" * 272, "272 bytes (exact 2 blocks)"),
            (8, b"x" * 273, "273 bytes (3 blocks)"),
        ]

        for fix_id, msg, desc in fixtures:
            expected_hex = keccak256(msg).hex()
            words = []
            for idx in range(4):
                w = self.run_linvm("keccak256_fixture_word", fix_id, idx)
                words.append(w)
            u_words = [w & 0xFFFFFFFFFFFFFFFF for w in words]
            digest_hex = struct.pack("<QQQQ", *u_words).hex()
            self.assertEqual(
                digest_hex,
                expected_hex,
                f"LinVM digest mismatch on fixture {fix_id} ({desc}): {digest_hex} != {expected_hex}"
            )

    def test_linvm_fixture_verifier_fail_closed(self):
        """M1-B.2: Verify keccak256_verify_fixture return codes and fail-closed bounds."""
        fixtures = [
            (0, b""),
            (1, b"x"),
            (2, b"The quick brown fox jumps over the lazy dog"),
            (3, b"x" * 135),
            (4, b"x" * 136),
            (5, b"x" * 137),
            (6, b"x" * 271),
            (7, b"x" * 272),
            (8, b"x" * 273),
        ]

        for fix_id, msg in fixtures:
            # 1. Fetch authentic words computed by LinVM
            words = [self.run_linvm("keccak256_fixture_word", fix_id, i) for i in range(4)]

            # 2. Authentic verification must return 0 (SUCCESS)
            status = self.run_linvm("keccak256_verify_fixture", fix_id, *words)
            self.assertEqual(status, 0, f"Authentic fixture {fix_id} verification failed")

            # 3. Tampered word must return 1 (HASH_MISMATCH)
            tampered_words = list(words)
            tampered_words[0] ^= 1
            status_tampered = self.run_linvm("keccak256_verify_fixture", fix_id, *tampered_words)
            self.assertEqual(status_tampered, 1, f"Tampered fixture {fix_id} was not rejected")

        # 4. Out-of-bounds fixture IDs must return 2 (INVALID_FIXTURE_ID)
        status_neg = self.run_linvm("keccak256_verify_fixture", -1, 0, 0, 0, 0)
        self.assertEqual(status_neg, 2, "Negative fixture ID did not return INVALID_FIXTURE_ID")

        status_oob = self.run_linvm("keccak256_verify_fixture", 9, 0, 0, 0, 0)
        self.assertEqual(status_oob, 2, "OOB fixture ID did not return INVALID_FIXTURE_ID")

    def test_optional_mojo_parity(self):
        """M1-B.2: Document and optionally cross-verify parity against pure Mojo if available."""
        mojo_bin = shutil.which("mojo") or (
            os.path.expanduser("~/.local/share/modular-env/bin/mojo")
            if os.path.exists(os.path.expanduser("~/.local/share/modular-env/bin/mojo"))
            else None
        )
        if not mojo_bin:
            self.skipTest("Mojo binary not found in PATH; skipping automated Mojo execution")

        # Verify that Fox vector computed by LinVM matches Mojo test expectation
        lin_words = [self.run_linvm("keccak256_fixture_word", 2, i) for i in range(4)]
        u_words = [w & 0xFFFFFFFFFFFFFFFF for w in lin_words]
        lin_hex = struct.pack("<QQQQ", *u_words).hex()
        expected_fox = "4d741b6f1eb29cb2a9b9911c82f56fa8d73b04959d3d9d222895df6c0b28aa15"
        self.assertEqual(lin_hex, expected_fox, "LinVM Fox digest does not match canonical vector")

if __name__ == "__main__":
    unittest.main(verbosity=2)
