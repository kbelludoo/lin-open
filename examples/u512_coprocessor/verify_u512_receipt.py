#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent LNR1 auditor for the LIN u512 numeric coprocessor.

Stdlib only (hashlib, json, struct). Does not import or invoke LIN, gcc, or
the C11 oracle. Recomputes:
  * floor((a*b)/d) / 256x256->512 mul / 512-bit ge against Python int
  * remainder identity q*d+r == a*b on approved mulDiv
  * SHA-256(LIN:U512:LEAF:1 || 240-byte record) and the Merkle root

Usage:
  python3 examples/u512_coprocessor/verify_u512_receipt.py \
    examples/u512_coprocessor/u512_coprocessor_evidence.json
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
REC_LEN = 240
MASK256 = (1 << 256) - 1
MASK64 = (1 << 64) - 1


def u256_hex(n: int) -> str:
    return f"{n & MASK256:064x}"


def u512_hex(n: int) -> str:
    return f"{n & ((1 << 512) - 1):0128x}"


def pack_u256_be(n: int) -> bytes:
    return (n & MASK256).to_bytes(32, "big")


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(a * b, d)
    if q > MASK256:
        return -2, 0, 0
    return 1, q, r


def pack_record(
    image: bytes,
    vec_id: int,
    op: int,
    a: int,
    b: int,
    d: int,
    q: int,
    r: int,
    steps: int,
    status: int,
) -> bytes:
    raw = bytearray(REC_LEN)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = 1
    struct.pack_into("<H", raw, 6, op)
    raw[8:40] = image
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, vec_id)
    raw[56:88] = pack_u256_be(a)
    raw[88:120] = pack_u256_be(b)
    raw[120:152] = pack_u256_be(d)
    raw[152:184] = pack_u256_be(q)
    raw[184:216] = pack_u256_be(r)
    struct.pack_into("<Q", raw, 216, steps & MASK64)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def leaf_hash(rec: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + rec).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    if not nodes:
        return hashlib.sha256(DOM_NODE).digest()
    while len(nodes) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
            nxt.append(hashlib.sha256(DOM_NODE + left + right).digest())
        nodes = nxt
    return nodes[0]


def verify_receipt(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    img = bytes.fromhex(data["image_sha256"])
    leaves: list[bytes] = []
    for vec in data["vectors"]:
        a, b, d = int(vec["a"], 16), int(vec["b"], 16), int(vec["d"], 16)
        q, r = int(vec["q"], 16), int(vec["r"], 16)
        status, op = int(vec["status"]), int(vec["op"])
        if op == 0:
            st, pq, pr = py_muldiv(a, b, d)
            if (st, pq, pr) != (status, q, r):
                print(f"FAIL math muldiv vec {vec['id']}: py={(st, pq, pr)} rec={(status, q, r)}")
                return 1
            if status == 1 and (q * d + r != a * b or r >= d or q > MASK256):
                print(f"FAIL remainder identity vec {vec['id']}")
                return 1
        elif op == 1:
            if a * b != (r << 256) + q or status != 1:
                print(f"FAIL math mul vec {vec['id']}")
                return 1
        elif op == 2:
            x = (b << 256) + a
            y = (q << 256) + d
            if status != int(x >= y):
                print(f"FAIL math ge vec {vec['id']}")
                return 1
        rec = pack_record(img, int(vec["id"]), op, a, b, d, q, r, int(vec["steps"]), status)
        if leaf_hash(rec).hex() != vec["leaf"]:
            print(f"FAIL leaf vec {vec['id']}")
            return 1
        leaves.append(leaf_hash(rec))
    root = merkle_root(leaves).hex()
    if root != data["merkle_root"]:
        print(f"FAIL merkle {root} != {data['merkle_root']}")
        return 1
    v0 = data["vectors"][0]
    tampered = pack_record(
        img, int(v0["id"]), int(v0["op"]), int(v0["a"], 16), int(v0["b"], 16),
        int(v0["d"], 16), int(v0["q"], 16) ^ 1, int(v0["r"], 16),
        int(v0["steps"]), int(v0["status"]),
    )
    tleaves = [leaf_hash(tampered)] + leaves[1:]
    if merkle_root(tleaves).hex() == root:
        print("FAIL tamper root unchanged")
        return 1
    print(f"PASS verify-receipt vectors={len(leaves)} root=sha256:{root}")
    print("auditor used hashlib + Python int only (no LIN, no C11).")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_u512_receipt.py <u512_coprocessor_evidence.json>", file=sys.stderr)
        return 2
    return verify_receipt(Path(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
