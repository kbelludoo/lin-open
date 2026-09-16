#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent LNR1/LCR2 verifier — no LIN runtime.

Recomputes SHA-256 Merkle over 240-byte LNR1 records with domains
LIN:U512:LEAF:1 / LIN:U512:NODE:1 and checks q*d + r == a*b (Python int)
when status==1. LCR2 (208-byte) uses LIN:LEAF:1 / LIN:NODE:1, requires
steps!=0, and checks amount_out == (ain*997*rout)//(rin*1000+ain*997).

Tamper-evidence plus a math identity. Not zk, not computational soundness.
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
DOM_LCR2_LEAF = b"LIN:LEAF:1"
DOM_LCR2_NODE = b"LIN:NODE:1"
MAGIC = b"LNR1"
LCR2_MAGIC = b"LCR2"
REC = 240
LCR2_REC = 208
U256 = (1 << 256) - 1


def leaf_hash(rec: bytes, dom: bytes = DOM_LEAF) -> bytes:
    return hashlib.sha256(dom + rec).digest()


def parent_hash(l: bytes, r: bytes, dom: bytes = DOM_NODE) -> bytes:
    return hashlib.sha256(dom + l + r).digest()


def merkle_root(leaves: list[bytes], node: bytes = DOM_NODE) -> bytes:
    cur = list(leaves)
    if not cur:
        return hashlib.sha256(b"").digest()
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            left = cur[i]
            right = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(parent_hash(left, right, node))
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
        "a": int.from_bytes(raw[56:88], "big"),
        "b": int.from_bytes(raw[88:120], "big"),
        "d": int.from_bytes(raw[120:152], "big"),
        "q": int.from_bytes(raw[152:184], "big"),
        "r": int.from_bytes(raw[184:216], "big"),
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
        if row.get("leaf_hash_hex") and row.get("leaf_hash_hex") != leaf_hash(raw).hex():
            return {"valid": False, "reason": "BAD_LEAF_HASH", "leaf": i}
        if not identity_ok(parsed):
            return {"valid": False, "reason": "BAD_IDENTITY", "leaf": i}
        if row.get("status") is not None and row.get("status") != parsed["status"]:
            return {"valid": False, "reason": "BAD_STATUS_FIELD", "leaf": i}
        leaves.append(leaf_hash(raw))
    got = merkle_root(leaves).hex()
    if got != root_hex:
        return {"valid": False, "reason": "BAD_ROOT", "computed": got, "declared": root_hex}
    return {"valid": True, "reason": "OK", "leaves": len(leaves), "merkle_root_sha256": got}


def parse_lcr2(raw: bytes) -> dict:
    if len(raw) != LCR2_REC:
        raise ValueError("bad_lcr2_len")
    if raw[0:4] != LCR2_MAGIC or raw[4] != 1 or raw[5] != 1:
        raise ValueError("bad_lcr2_header")
    steps, status = struct.unpack_from("<Qq", raw, 184)
    return {
        "image_digest": raw[8:40].hex(),
        "amount_in": int.from_bytes(raw[56:88], "big"),
        "reserve_in": int.from_bytes(raw[88:120], "big"),
        "reserve_out": int.from_bytes(raw[120:152], "big"),
        "amount_out": int.from_bytes(raw[152:184], "big"),
        "steps": steps,
        "status": status,
    }


def ref_amount_out(ain: int, rin: int, rout: int) -> int:
    fee = ain * 997
    return (fee * rout) // (rin * 1000 + fee)


def verify_lcr2_bundle(data: dict) -> dict:
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
        parsed = parse_lcr2(raw)
        if parsed["steps"] == 0:
            return {"valid": False, "reason": "STEPS_ZERO", "leaf": i}
        if img and parsed["image_digest"] != img:
            return {"valid": False, "reason": "BAD_IMAGE_DIGEST", "leaf": i}
        if parsed["status"] == 1:
            ref = ref_amount_out(parsed["amount_in"], parsed["reserve_in"], parsed["reserve_out"])
            if parsed["amount_out"] != ref:
                return {"valid": False, "reason": "BAD_AMOUNT_OUT", "leaf": i}
        leaves.append(leaf_hash(raw, DOM_LCR2_LEAF))
    got = merkle_root(leaves, DOM_LCR2_NODE).hex()
    if got != root_hex:
        return {"valid": False, "reason": "BAD_ROOT", "computed": got}
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
            {
                "raw_record_hex": bytes(tampered).hex(),
                "leaf_hash_hex": leaf_hash(bytes(tampered)).hex(),
                "status": 1,
            },
            {"raw_record_hex": r1.hex(), "leaf_hash_hex": leaves[1].hex(), "status": 1},
        ],
    }
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
    ap.add_argument("--lcr2", action="store_true", help="verify lcr2_e2e in the same JSON")
    args = ap.parse_args()
    rc = 0
    if args.self_test:
        rc = self_test()
        if rc != 0:
            return rc
    if args.bundle:
        data = json.loads(Path(args.bundle).read_text())
        bundle = data.get("lnr1") if "lnr1" in data else data
        v = verify_bundle(bundle)
        print(json.dumps(v, indent=2, sort_keys=True))
        if not v["valid"]:
            return 1
        if args.lcr2 or "lcr2_e2e" in data:
            lv = verify_lcr2_bundle(data["lcr2_e2e"] if "lcr2_e2e" in data else data)
            print(json.dumps({"lcr2": lv}, indent=2, sort_keys=True))
            if not lv["valid"]:
                return 1
    elif not args.self_test:
        print("usage: verify_u512_receipt.py [--self-test] [--lcr2] [bundle.json]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
