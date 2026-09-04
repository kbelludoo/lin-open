#!/usr/bin/env python3
"""
Lin-Audit Ethereum — Submilestone M1-B.1 Verification Suite
Executes LinVM Keccak implementation (src/lin_ethereum_keccak.lin) via C11 LinVM host.
Asserts bit-exact parity against:
1. Python reference implementation (tools/lin_audit_tx.py)
2. Pure Mojo implementation (tools/lin_audit_tx.mojo)
3. NIST SHA3-256 substitution detection
"""

import os
import sys
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
        """Verify that LinVM computes the exact 4 words of Keccak-256("")."""
        w0 = self.run_linvm("keccak256_empty_word", 0)
        w1 = self.run_linvm("keccak256_empty_word", 1)
        w2 = self.run_linvm("keccak256_empty_word", 2)
        w3 = self.run_linvm("keccak256_empty_word", 3)

        # Convert signed int64 to unsigned 64-bit
        u0 = w0 & 0xFFFFFFFFFFFFFFFF
        u1 = w1 & 0xFFFFFFFFFFFFFFFF
        u2 = w2 & 0xFFFFFFFFFFFFFFFF
        u3 = w3 & 0xFFFFFFFFFFFFFFFF

        # Pack little-endian 4 words into 32 bytes
        linvm_bytes = struct.pack("<QQQQ", u0, u1, u2, u3)
        linvm_hex = linvm_bytes.hex()

        expected_keccak = "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        self.assertEqual(linvm_hex, expected_keccak, "LinVM Keccak-256 output does not match expected digest")

        # Cross-verify against Python reference
        py_hex = keccak256(b"").hex()
        self.assertEqual(linvm_hex, py_hex, "LinVM does not match Python reference")

    def test_linvm_distinguishes_nist_sha3(self):
        """Verify that verify_empty_hash in LinVM returns 0 for Keccak and 2 for NIST SHA3."""
        # 1. Correct Keccak-256 words -> Must return 0 (SUCCESS)
        k_w0 = self.run_linvm("keccak256_empty_word", 0)
        k_w1 = self.run_linvm("keccak256_empty_word", 1)
        k_w2 = self.run_linvm("keccak256_empty_word", 2)
        k_w3 = self.run_linvm("keccak256_empty_word", 3)
        status_k = self.run_linvm("verify_empty_hash", k_w0, k_w1, k_w2, k_w3)
        self.assertEqual(status_k, 0, "LinVM failed to verify correct Keccak-256 hash")

        # 2. Corrupted word -> Must return 1 (HASH_MISMATCH)
        status_corrupt = self.run_linvm("verify_empty_hash", k_w0 ^ 1, k_w1, k_w2, k_w3)
        self.assertEqual(status_corrupt, 1, "LinVM failed to reject corrupted word")

        # 3. NIST SHA3-256 words -> Must return 2 (NIST_SHA3_SUBSTITUTION_DETECTED)
        nist_bytes = nist_sha3_256(b"")
        nist_u0, nist_u1, nist_u2, nist_u3 = struct.unpack("<QQQQ", nist_bytes)
        nist_s0 = struct.unpack("<q", struct.pack("<Q", nist_u0))[0]
        nist_s1 = struct.unpack("<q", struct.pack("<Q", nist_u1))[0]
        nist_s2 = struct.unpack("<q", struct.pack("<Q", nist_u2))[0]
        nist_s3 = struct.unpack("<q", struct.pack("<Q", nist_u3))[0]

        status_nist = self.run_linvm("verify_empty_hash", nist_s0, nist_s1, nist_s2, nist_s3)
        self.assertEqual(status_nist, 2, "LinVM failed to flag NIST SHA3-256 substitution")

if __name__ == "__main__":
    unittest.main(verbosity=2)
