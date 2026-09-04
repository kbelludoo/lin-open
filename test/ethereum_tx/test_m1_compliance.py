#!/usr/bin/env python3
"""
Lin-Audit Ethereum — Milestone 1 (M1) Compliance & Mutation Test Suite
Validates:
1. Keccak-256 vs NIST SHA3-256 differentiation
2. Canonical RLP parser correctness and non-canonical rejection
3. All supported transaction envelope types (Types 0, 1, 2, 3)
4. Comprehensive adversarial mutation tests (fail-closed guarantees)
"""

import os
import sys
import unittest
import json

# Add tools directory to path
TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../tools"))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from lin_audit_tx import (
    keccak256,
    nist_sha3_256,
    parse_canonical_rlp,
    encode_canonical_rlp,
    verify_ethereum_tx,
    RLPError
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

class TestKeccakVsSha3(unittest.TestCase):
    def test_empty_string_keccak_and_sha3(self):
        k = keccak256(b"").hex()
        s = nist_sha3_256(b"").hex()
        self.assertEqual(k, "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(s, "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a")
        self.assertNotEqual(k, s, "Keccak-256 MUST NOT equal NIST SHA3-256")

    def test_known_keccak_vector(self):
        msg = b"The quick brown fox jumps over the lazy dog"
        k = keccak256(msg).hex()
        self.assertEqual(k, "4d741b6f1eb29cb2a9b9911c82f56fa8d73b04959d3d9d222895df6c0b28aa15")
        s = nist_sha3_256(msg).hex()
        self.assertNotEqual(k, s)

    def test_block_boundary_lengths(self):
        for length in [135, 136, 137, 271, 272, 273]:
            data = bytes([i % 256 for i in range(length)])
            k = keccak256(data)
            s = nist_sha3_256(data)
            self.assertEqual(len(k), 32)
            self.assertEqual(len(s), 32)
            self.assertNotEqual(k, s)

class TestCanonicalRLP(unittest.TestCase):
    def test_roundtrip_primitives(self):
        cases = [
            b"",
            b"a",
            b"dog",
            b"\x00",
            b"\x7f",
            b"\x80",
            b"Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio.",
            [b"cat", b"dog"],
            [b"", [b"nested", b""]],
        ]
        for c in cases:
            enc = encode_canonical_rlp(c)
            item, next_off = parse_canonical_rlp(enc, 0)
            self.assertEqual(next_off, len(enc))
            self.assertEqual(item.to_python(), c)

    def test_reject_single_byte_below_80_with_length_prefix(self):
        # Byte 0x05 encoded as 0x81 0x05 is NON_CANONICAL
        bad = b"\x81\x05"
        with self.assertRaises(RLPError) as ctx:
            parse_canonical_rlp(bad, 0)
        self.assertEqual(ctx.exception.code, "NON_CANONICAL")

    def test_reject_leading_zeros_in_long_string_length(self):
        # 0xb8 followed by length length=1, with length=0x0050 (0xb9 0x00 0x50 ...)
        bad = b"\xb9\x00\x50" + (b"A" * 80)
        with self.assertRaises(RLPError) as ctx:
            parse_canonical_rlp(bad, 0)
        self.assertEqual(ctx.exception.code, "NON_CANONICAL")

    def test_reject_long_string_prefix_for_short_string(self):
        # 0xb8 (length of length = 1) followed by length 10 (which <= 55)
        bad = b"\xb8\x0a" + (b"A" * 10)
        with self.assertRaises(RLPError) as ctx:
            parse_canonical_rlp(bad, 0)
        self.assertEqual(ctx.exception.code, "NON_CANONICAL")

    def test_reject_truncated_string(self):
        # Declares length 10, provides only 5
        bad = b"\x8a12345"
        with self.assertRaises(RLPError) as ctx:
            parse_canonical_rlp(bad, 0)
        self.assertEqual(ctx.exception.code, "MALFORMED")

class TestAllTransactionTypes(unittest.TestCase):
    def test_verify_canonical_fixtures(self):
        fixture_files = [f for f in os.listdir(FIXTURES_DIR) if f.endswith(".json")]
        self.assertGreaterEqual(len(fixture_files), 4, "Must have fixtures for all 4 types")

        for fpath in fixture_files:
            with open(os.path.join(FIXTURES_DIR, fpath), "r") as f:
                fix = json.load(f)
            res = verify_ethereum_tx(fix["raw_tx"], fix["claimed_hash"])
            self.assertEqual(res["verdict"], "PASS", f"Fixture {fpath} failed: {res['errors']}")
            self.assertTrue(res["valid_encoding"])
            self.assertTrue(res["semantic_valid"])
            self.assertTrue(res["hash_matches"])
            self.assertEqual(len(res["errors"]), 0)

class TestAdversarialMutations(unittest.TestCase):
    def setUp(self):
        # Load canonical Type 2 fixture as baseline
        with open(os.path.join(FIXTURES_DIR, "eip1559_001.json"), "r") as f:
            self.fixture = json.load(f)
        self.raw_bytes = bytes.fromhex(self.fixture["raw_tx"][2:])
        self.claimed_hash = self.fixture["claimed_hash"]

    def test_mutation_1_flip_raw_byte(self):
        """Mutation 1: Flip any byte in raw_tx -> Must FAIL (HASH_MISMATCH or MALFORMED)."""
        tampered = bytearray(self.raw_bytes)
        tampered[10] ^= 0xFF
        res = verify_ethereum_tx("0x" + tampered.hex(), self.claimed_hash)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("HASH_MISMATCH" in err or "MALFORMED" in err or "NON_CANONICAL" in err for err in res["errors"]))

    def test_mutation_2_tamper_claimed_hash(self):
        """Mutation 2: Tamper claimed_hash -> Must FAIL with HASH_MISMATCH."""
        bad_hash = "0x" + "00" * 32
        res = verify_ethereum_tx(self.fixture["raw_tx"], bad_hash)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertFalse(res["hash_matches"])
        self.assertTrue(any("HASH_MISMATCH" in err for err in res["errors"]))

    def test_mutation_3_trailing_bytes(self):
        """Mutation 3: Append extraneous trailing bytes -> Must FAIL with MALFORMED."""
        tampered = self.raw_bytes + b"\xde\xad\xbe\xef"
        res = verify_ethereum_tx("0x" + tampered.hex(), self.claimed_hash)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("MALFORMED" in err and "residual" in err for err in res["errors"]))

    def test_mutation_4_swap_envelope_type(self):
        """Mutation 4: Swap Type 0x02 to 0x03 -> Must FAIL (WRONG_ARITY or HASH_MISMATCH)."""
        tampered = bytearray(self.raw_bytes)
        tampered[0] = 0x03  # Swapped to Type 3
        res = verify_ethereum_tx("0x" + tampered.hex(), self.claimed_hash)
        self.assertEqual(res["verdict"], "FAIL")

    def test_mutation_5_truncate_payload(self):
        """Mutation 5: Truncate 5 bytes off the end -> Must FAIL with MALFORMED."""
        tampered = self.raw_bytes[:-5]
        res = verify_ethereum_tx("0x" + tampered.hex(), self.claimed_hash)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("MALFORMED" in err for err in res["errors"]))

    def test_mutation_6_substitute_with_nist_sha3(self):
        """Mutation 6: If an attacker claims the NIST SHA3 hash, it MUST NOT match."""
        nist_hash = "0x" + nist_sha3_256(self.raw_bytes).hex()
        res = verify_ethereum_tx(self.fixture["raw_tx"], nist_hash)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertFalse(res["hash_matches"])
        self.assertTrue(any("HASH_MISMATCH" in err for err in res["errors"]))

    def test_mutation_7_non_minimal_integer_leading_zero(self):
        """Mutation 7: Inject leading zero in integer -> Must FAIL with NON_CANONICAL."""
        addr = bytes.fromhex("3535353535353535353535353535353535353535")
        r = bytes.fromhex("11" * 32)
        s = bytes.fromhex("22" * 32)
        # Nonce with non-canonical leading zero: b'\x00\x09'
        non_canonical_nonce = b"\x00\x09"
        # Manually assemble RLP list containing the non-canonical nonce
        encoded_fields = [
            b"\x82\x00\x09", # 2-byte string with leading zero
            encode_canonical_rlp(20000000000),
            encode_canonical_rlp(21000),
            encode_canonical_rlp(addr),
            encode_canonical_rlp(1000),
            b"\x80",
            encode_canonical_rlp(37),
            encode_canonical_rlp(r),
            encode_canonical_rlp(s)
        ]
        payload = b"".join(encoded_fields)
        raw_tx = bytes([0xf7 + (len(payload).bit_length() + 7)//8]) + len(payload).to_bytes((len(payload).bit_length() + 7)//8, "big") + payload if len(payload) > 55 else bytes([0xc0 + len(payload)]) + payload
        res = verify_ethereum_tx("0x" + raw_tx.hex())
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("NON_CANONICAL" in err for err in res["errors"]))

    def test_unsupported_type_rejection(self):
        """Unrecognized type byte (e.g. 0x05) must return UNSUPPORTED_TYPE."""
        tampered = bytearray(self.raw_bytes)
        tampered[0] = 0x05
        res = verify_ethereum_tx("0x" + tampered.hex())
        self.assertEqual(res["verdict"], "UNSUPPORTED_TYPE")

if __name__ == "__main__":
    unittest.main(verbosity=2)
