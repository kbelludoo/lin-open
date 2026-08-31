#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent LIN compute-receipt verifier (Python 3, standard library only).

Zero-trust: this verifier does NOT use the LIN compiler/runtime. It recomputes
the receipt Merkle root with hashlib (NIST FIPS 180-4 SHA-256) and compares it
against the claimed root, so any auditor can validate a LIN receipt on any
machine that has Python 3.

Open receipt format (LIN_COMPUTE_RECEIPT_1.0):
    leaf[0:32]  = SHA-256(source code)                  ("artifact")
    leaf[32:40] = output  (i64, little-endian)
    leaf[40:48] = steps   (u64, little-endian)
    leaf[48:56] = sp_at_ret (u64, little-endian)
    leaf[56:64] = input   (i64, little-endian)
    merkle_root = SHA-256(leaf)

Accepts both the JSON export and the native RULEL format.
Optional: pass --source "<code>" to also verify that the artifact hash is the
SHA-256 of the given source code (the receipt itself only carries the hash).

Usage:
    python3 verify_receipt.py receipt.json
    python3 verify_receipt.py receipt.rulel
    python3 verify_receipt.py receipt.json --source "return x * x;"
Exit code: 0 = PASS, 1 = FAIL.
"""

import argparse
import hashlib
import json
import struct
import sys

SCHEMA = "LIN_COMPUTE_RECEIPT_1.0"
FIELD_NAMES = {"artifact", "input", "output", "steps", "sp_at_ret", "merkle_root"}


class ReceiptError(ValueError):
    pass


def strip_sha256(hex_str: str) -> str:
    return hex_str[7:] if hex_str.startswith("sha256:") else hex_str


def parse_json(txt: str):
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as e:
        raise ReceiptError(f"not valid JSON: {e}")
    if not isinstance(data, dict):
        raise ReceiptError("JSON root must be an object")
    missing = sorted(FIELD_NAMES - set(data))
    if missing:
        raise ReceiptError(f"missing field(s): {', '.join(missing)}")
    try:
        return {
            "artifact": str(data["artifact"]),
            "input": str(data["input"]),
            "output": str(data["output"]),
            "steps": int(data["steps"]),
            "sp_at_ret": int(data["sp_at_ret"]),
            "merkle_root": str(data["merkle_root"]),
        }
    except (TypeError, ValueError) as e:
        raise ReceiptError(f"field type error: {e}")


def parse_rulel(txt: str):
    def val(tag: str):
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith(tag):
                return line[len(tag):].strip().strip('"')
        return None

    a, i, o, s, p, m = val(".a="), val(".i="), val(".o="), val(".s="), val(".p="), val(".m=")
    if None in (a, i, o, s, p, m):
        raise ReceiptError("missing RULEL field(s) (.a/.i/.o/.s/.p/.m)")
    try:
        return {"artifact": a, "input": i, "output": o,
                "steps": int(s), "sp_at_ret": int(p), "merkle_root": m}
    except ValueError as e:
        raise ReceiptError(f"field type error: {e}")


def build_leaf(fields: dict) -> bytes:
    try:
        art_hex = strip_sha256(fields["artifact"])
        if len(art_hex) != 64:
            raise ReceiptError("artifact must be a 32-byte SHA-256 hex digest (64 hex chars)")
        art = bytes.fromhex(art_hex)
        if len(art) != 32:
            raise ReceiptError("artifact must be 32 bytes")
        output = int(fields["output"])
        steps = int(fields["steps"])
        sp = int(fields["sp_at_ret"])
        inp = int(fields["input"])
        if not -(2**63) <= output < 2**63:
            raise ReceiptError("output out of i64 range")
        if not 0 <= steps < 2**64:
            raise ReceiptError("steps out of u64 range")
        if not 0 <= sp < 2**64:
            raise ReceiptError("sp_at_ret out of u64 range")
        if not -(2**63) <= inp < 2**63:
            raise ReceiptError("input out of i64 range")
    except ValueError as e:
        raise ReceiptError(f"artifact is not valid hex: {e}")

    leaf = bytearray(64)
    leaf[0:32] = art
    struct.pack_into("<q", leaf, 32, output)
    struct.pack_into("<Q", leaf, 40, steps)
    struct.pack_into("<Q", leaf, 48, sp)
    struct.pack_into("<q", leaf, 56, inp)
    return bytes(leaf)


def verify_file(path: str, source: str | None) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    fields = parse_json(txt) if txt.lstrip().startswith("{") else parse_rulel(txt)
    claimed = strip_sha256(fields["merkle_root"])

    computed = hashlib.sha256(build_leaf(fields)).hexdigest()

    print("=" * 72)
    print("   INDEPENDENT LIN RECEIPT VERIFIER (Python 3 stdlib)")
    print("=" * 72)
    print(f"  Artifact     : sha256:{strip_sha256(fields['artifact'])}")
    print(f"  Input        : {fields['input']}")
    print(f"  Output       : {fields['output']}")
    print(f"  Steps        : {fields['steps']}")
    print(f"  SP at ret    : {fields['sp_at_ret']}")
    print(f"  Merkle (file): sha256:{claimed}")
    print(f"  Merkle (calc): sha256:{computed}")

    artifact_ok = True
    if source is not None:
        src_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        artifact_ok = src_hash == strip_sha256(fields["artifact"])
        print(f"  Source check : {'PASS (artifact matches --source)' if artifact_ok else 'FAIL (artifact != SHA-256(--source))'}")

    ok = computed == claimed and artifact_ok
    if ok:
        print(f"  [PASS] Receipt validated by an independent open-source verifier "
              f"(sha256:{computed})")
    else:
        print(f"  [FAIL] Receipt forged or tampered! "
              f"calculated={computed}, claimed={claimed}")
    print("=" * 72)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent LIN receipt verifier (stdlib only)")
    ap.add_argument("receipt", help="path to receipt.json or receipt.rulel")
    ap.add_argument("--source", default=None,
                    help="optional source code; verifies the artifact hash matches it")
    args = ap.parse_args()
    try:
        ok = verify_file(args.receipt, args.source)
    except (ReceiptError, OSError) as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
