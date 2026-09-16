#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent auditor for LNR1 u512 coprocessor receipts.

Zero LIN, zero gcc: Python stdlib only (hashlib, json, struct).
Recomputes mul/div/ge with Python int and the Merkle tree with
domain-separated SHA-256. Does not attest VM step counts — those
require re-running the LIN image.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
REC_LEN = 240


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    n = a * b
    q, r = divmod(n, d)
    if q > U256:
        return -2, 0, 0
    return 1, q, r


def py_div(n: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(n, d)
    if q > U256:
        return -2, 0, 0
    return 1, q, r


def be32(x: int) -> bytes:
    return (x & U256).to_bytes(32, "big")


def merkle(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    if not nodes:
        return hashlib.sha256(DOM_NODE).digest()
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nxt = []
        for i in range(0, len(nodes), 2):
            nxt.append(hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest())
        nodes = nxt
    return nodes[0]


def unpack_lnr1(raw: bytes) -> dict:
    if len(raw) != REC_LEN:
        raise ValueError(f"len {len(raw)}")
    if raw[0:4] != b"LNR1" or raw[4] != 1 or raw[5] != 1 or raw[6:8] != b"\x00\x00":
        raise ValueError("header")
    op, status = struct.unpack_from("<ii", raw, 48)
    vec_id = struct.unpack_from("<Q", raw, 40)[0]
    steps = struct.unpack_from("<Q", raw, 216)[0]
    return {
        "image": raw[8:40].hex(),
        "vec_id": vec_id,
        "op": op,
        "status": status,
        "a": int.from_bytes(raw[56:88], "big"),
        "b": int.from_bytes(raw[88:120], "big"),
        "d": int.from_bytes(raw[120:152], "big"),
        "q": int.from_bytes(raw[152:184], "big"),
        "r": int.from_bytes(raw[184:216], "big"),
        "steps": steps,
        "pad": raw[224:240],
    }


def verify_file(path: Path) -> dict:
    data = json.loads(path.read_text())
    img = data["loader_digest"]
    recs = data["records"]
    leaves = []
    failures = []
    for i, rec in enumerate(recs):
        raw = bytes.fromhex(rec["raw_hex"])
        u = unpack_lnr1(raw)
        if u["image"] != img:
            failures.append((i, "image"))
        if rec.get("op") != u["op"] or rec.get("status") != u["status"]:
            failures.append((i, "json-mismatch"))
        leaf = hashlib.sha256(DOM_LEAF + raw).digest()
        if rec.get("leaf_hex") != leaf.hex():
            failures.append((i, "leaf"))
        leaves.append(leaf)
        op, a, b, d, q, r, st = u["op"], u["a"], u["b"], u["d"], u["q"], u["r"], u["status"]
        if op == 0:  # mul: q=prod_lo, r=prod_hi
            prod = a * b
            exp_lo, exp_hi = prod & U256, prod >> 256
            if st != 1 or q != exp_lo or r != exp_hi:
                failures.append((i, "mul-math"))
        elif op == 1:  # ge on 512-bit values packed as a||b vs d||q? see harness
            # a,b are low/high of left; d,q low/high of right; status=ge
            left = a + (b << 256)
            right = d + (q << 256)
            if st not in (0, 1) or st != int(left >= right) or r != 0:
                failures.append((i, "ge-math"))
        elif op == 2:
            est, eq, er = py_div(a + (b << 256), d)  # n in a||b, d in d
            if (st, q, r) != (est, eq if est == 1 else 0, er if est == 1 else 0) and not (
                st == est and est != 1
            ):
                failures.append((i, "div-math"))
            if est == 1 and (eq * d + er) != (a + (b << 256)):
                failures.append((i, "div-identity"))
        elif op == 3:
            est, eq, er = py_muldiv(a, b, d)
            if st != est:
                failures.append((i, "muldiv-status"))
            elif est == 1:
                if q != eq or r != er:
                    failures.append((i, "muldiv-math"))
                if eq * d + er != a * b:
                    failures.append((i, "muldiv-identity"))
            elif q != 0 or r != 0:
                # harness zeros q,r on fail-closed
                if rec.get("zero_on_reject", True) and (q or r):
                    failures.append((i, "muldiv-reject-payload"))
        else:
            failures.append((i, "bad-op"))
        if u["pad"] != b"\x00" * 16:
            failures.append((i, "pad"))
    root = merkle(leaves).hex()
    if root != data.get("merkle_root"):
        failures.append((-1, f"root {root} != {data.get('merkle_root')}"))
    return {
        "valid": not failures,
        "records": len(recs),
        "merkle_root": root,
        "failures": failures[:12],
        "math": "python-int",
        "steps": "recorded-only-rerun-lin-to-confirm",
    }


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/u512_coprocessor/u512_coprocessor_evidence.json")
    r = verify_file(path)
    print(json.dumps(r, indent=2))
    return 0 if r["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
