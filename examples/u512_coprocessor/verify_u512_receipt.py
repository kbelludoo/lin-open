#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent LNR1 verifier — no LIN runtime.

Recomputes SHA-256 Merkle over 240-byte LNR1 records with domains
LIN:U512:LEAF:1 / LIN:U512:NODE:1 and checks the uint256 remainder identity
q*d + r == a*b (Python int) when status==1.

This is tamper-evidence plus a math identity. It is not zk and not
computational soundness of LinVM execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
MAGIC = b"LNR1"
REC = 240
U256 = (1 << 256) - 1


def be32(b: bytes) -> int:
    return int.from_bytes(b, "big")


def leaf_hash(rec: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + rec).digest()


def parent_hash(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(DOM_NODE + l + r).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    cur = list(leaves)
    if not cur:
        return hashlib.sha256(b"").digest()
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(parent_hash(l, r))
        cur = nxt
    return cur[0]


def parse_record(raw: bytes) -> dict:
    if len(raw) != REC:
        raise ValueError("bad_len")
    if raw[0:4] != MAGIC or raw[4] != 1 or raw[5] != 1 or raw[6:8] != b"\x00\x00":
        raise ValueError("bad_header")
    steps, status, flags = struct.unpack_from("<QqQ", raw, 216)
    return {
        "image_digest": raw[8:40].hex(),
        "run_id": struct.unpack_from("<Q", raw, 40)[0],
        "leaf_id": struct.unpack_from("<Q", raw, 48)[0],
        "a": be32(raw[56:88]),
        "b": be32(raw[88:120]),
        "d": be32(raw[120:152]),
        "q": be32(raw[152:184]),
        "r": be32(raw[184:216]),
        "steps": steps,
        "status": status,
        "flags": flags,
    }


def identity_ok(rec: dict) -> bool:
    a, b, d, q, r, st = rec["a"], rec["b"], rec["d"], rec["q"], rec["r"], rec["status"]
    n = a * b
    if st == -1:
        return d == 0
    if st == -2:
        return d != 0 and (n // d) > U256
    if st != 1:
        return False
    if d == 0 or q > U256 or r >= d:
        return False
    return q * d + r == n and n // d == q and n % d == r


def verify_bundle(data: dict) -> dict:
    recs = data.get("records")
    root_hex = data.get("merkle_root_sha256")
    img = data.get("image_loader_digest")
    if not isinstance(recs, list) or not recs:
        return {"valid": False, "reason": "NO_RECORDS"}
    if not isinstance(root_hex, str) or len(root_hex) != 64:
        return {"valid": False, "reason": "BAD_ROOT"}
    leaves = []
    for i, row in enumerate(recs):
        raw = bytes.fromhex(row["raw_record_hex"])
        parsed = parse_record(raw)
        if img and parsed["image_digest"] != img:
            return {"valid": False, "reason": "BAD_IMAGE_DIGEST", "leaf": i}
        if row.get("leaf_hash_hex") != leaf_hash(raw).hex():
            return {"valid": False, "reason": "BAD_LEAF_HASH", "leaf": i}
        if not identity_ok(parsed):
            return {"valid": False, "reason": "BAD_IDENTITY", "leaf": i}
        if row.get("status") != parsed["status"]:
            return {"valid": False, "reason": "BAD_STATUS_FIELD", "leaf": i}
        leaves.append(leaf_hash(raw))
    got = merkle_root(leaves).hex()
    if got != root_hex:
        return {"valid": False, "reason": "BAD_ROOT", "computed": got, "declared": root_hex}
    return {"valid": True, "reason": "OK", "leaves": len(leaves), "merkle_root_sha256": got}


def _demo_record(leaf_id: int, a: int, b: int, d: int, img: bytes) -> bytes:
    n = a * b
    if d == 0:
        st, q, r = -1, 0, 0
    else:
        q, r = divmod(n, d)
        if q > U256:
            st, q, r = -2, 0, 0
        else:
            st = 1
    raw = bytearray(REC)
    raw[0:4] = MAGIC
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, leaf_id)
    raw[56:88] = a.to_bytes(32, "big")
    raw[88:120] = b.to_bytes(32, "big")
    raw[120:152] = d.to_bytes(32, "big")
    raw[152:184] = q.to_bytes(32, "big")
    raw[184:216] = r.to_bytes(32, "big")
    struct.pack_into("<Q", raw, 216, 978287)
    struct.pack_into("<q", raw, 224, st)
    struct.pack_into("<Q", raw, 232, 0)
    return bytes(raw)


def self_test() -> int:
    img = bytes(32)
    r0 = _demo_record(1, 7, 9, 2, img)
    r1 = _demo_record(2, 1 << 255, 2, 3, img)
    leaves = [leaf_hash(r0), leaf_hash(r1)]
    root = merkle_root(leaves).hex()
    bundle = {
        "image_loader_digest": img.hex(),
        "merkle_root_sha256": root,
        "records": [
            {"raw_record_hex": r0.hex(), "leaf_hash_hex": leaves[0].hex(), "status": 1},
            {"raw_record_hex": r1.hex(), "leaf_hash_hex": leaves[1].hex(), "status": 1},
        ],
    }
    ok = verify_bundle(bundle)
    if not ok["valid"]:
        print("SELFTEST FAIL clean bundle", ok)
        return 1
    tampered = bytearray(r0)
    tampered[56] ^= 1
    bad = {
        "image_loader_digest": img.hex(),
        "merkle_root_sha256": root,
        "records": [
            {"raw_record_hex": bytes(tampered).hex(), "leaf_hash_hex": leaf_hash(bytes(tampered)).hex(), "status": 1},
            {"raw_record_hex": r1.hex(), "leaf_hash_hex": leaves[1].hex(), "status": 1},
        ],
    }
    # identity of tampered a=... should fail, or if leaf_hash is consistent, merkle root fails
    bad_v = verify_bundle(bad)
    if bad_v["valid"]:
        print("SELFTEST FAIL 1-bit leaf tamper was ACCEPTED")
        return 1
    print("SELFTEST PASS LNR1 identity + 1-bit leaf tamper REJECT reason=" + bad_v["reason"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", nargs="?", help="evidence JSON with LNR1 records")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    rc = 0
    if args.self_test:
        rc = self_test()
        if rc != 0:
            return rc
    if args.bundle:
        data = json.loads(Path(args.bundle).read_text())
        # allow nested key
        bundle = data.get("lnr1") if "lnr1" in data else data
        v = verify_bundle(bundle)
        print(json.dumps(v, indent=2, sort_keys=True))
        if not v["valid"]:
            return 1
    elif not args.self_test:
        print("usage: verify_u512_receipt.py [--self-test] [bundle.json]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
