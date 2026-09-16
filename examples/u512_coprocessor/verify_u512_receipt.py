#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent auditor for LNR1 u512 coprocessor receipts.

No LIN binary, no C oracle: Python stdlib hashlib + int only.
Recomputes SHA-256(LIN:U512:LEAF:1 || record) / NODE domain Merkle root,
then checks the arithmetic identity the record claims.

  python3 examples/u512_coprocessor/verify_u512_receipt.py \\
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
MAGIC = b"LNR1"
REC = 240
U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
OP_MUL, OP_GE, OP_DIV, OP_MULDIV = 1, 2, 3, 4


def u256_le(buf: bytes) -> int:
    return int.from_bytes(buf, "little")


def parent(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(DOM_NODE + l + r).digest()


def merkle(leaves: list[bytes]) -> bytes:
    if not leaves:
        return b"\x00" * 32
    nodes = list(leaves)
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nxt = []
        for i in range(0, len(nodes), 2):
            nxt.append(parent(nodes[i], nodes[i + 1]))
        nodes = nxt
    return nodes[0]


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    n = a * b
    q, r = divmod(n, d)
    if q >= (1 << 256):
        return -2, 0, 0
    return 1, q, r


def check_record(raw: bytes, img: bytes) -> str | None:
    if len(raw) != REC:
        return f"len {len(raw)}"
    if raw[0:4] != MAGIC or raw[4] != 1 or raw[5] != 1 or raw[6:8] != b"\x00\x00":
        return "header"
    if raw[8:40] != img:
        return "image_digest"
    if raw[232:240] != b"\x00" * 8:
        return "reserved"
    op = struct.unpack_from("<Q", raw, 48)[0]
    a = u256_le(raw[56:88])
    b = u256_le(raw[88:120])
    d = u256_le(raw[120:152])
    q = u256_le(raw[152:184])
    r = u256_le(raw[184:216])
    status = struct.unpack_from("<q", raw, 224)[0]
    if a > U256 or b > U256 or d > U256 or q > U256 or r > U256:
        return "range"
    if op == OP_MUL:
        if status != 1 or d != 0:
            return "mul status"
        if (q + (r << 256)) != a * b:
            return "mul product"
        return None
    if op == OP_GE:
        if status != 1 or r not in (0, 1):
            return "ge status"
        left = a + (d << 256)
        right = b + (q << 256)
        if int(left >= right) != r:
            return "ge identity"
        return None
    if op == OP_DIV:
        n = a + (b << 256)
        if d == 0:
            return None if status == -1 else "div0"
        qq, rr = divmod(n, d)
        if qq >= (1 << 256):
            return None if status == -2 else "div ov"
        if status != 1 or q != qq or r != rr or q * d + r != n or r >= d:
            return "div identity"
        return None
    if op == OP_MULDIV:
        st, qq, rr = py_muldiv(a, b, d)
        if status != st:
            return f"muldiv status {status}!={st}"
        if st == 1 and (q != qq or r != rr or q * d + r != a * b or r >= d):
            return "muldiv identity"
        if st != 1 and (q != 0 or r != 0):
            return "fail-closed leak"
        return None
    return f"op {op}"


def verify(path: Path, quiet: bool = False) -> int:
    data = json.loads(path.read_text())
    img_hex = data.get("image_loader_digest") or data.get("lnr1", {}).get("image_loader_digest")
    if not img_hex:
        if not quiet:
            print("FAIL: missing image_loader_digest")
        return 1
    img = bytes.fromhex(img_hex)
    if len(img) != 32:
        if not quiet:
            print("FAIL: image digest size")
        return 1
    recs = data.get("records") or data.get("lnr1", {}).get("records")
    if not recs:
        if not quiet:
            print("FAIL: no records")
        return 1
    leaves = []
    for i, rec in enumerate(recs):
        raw = bytes.fromhex(rec["raw_hex"] if isinstance(rec, dict) else rec)
        err = check_record(raw, img)
        if err:
            if not quiet:
                print(f"FAIL record {i}: {err}")
            return 1
        leaves.append(hashlib.sha256(DOM_LEAF + raw).digest())
    root = merkle(leaves).hex()
    claimed = (data.get("lnr1") or data).get("merkle_root")
    if claimed != root:
        if not quiet:
            print(f"FAIL merkle {claimed} != {root}")
        return 1
    if not quiet:
        print(f"PASS: {len(recs)} LNR1 records, merkle={root}")
    return 0


def selftest(path: Path) -> int:
    if verify(path) != 0:
        return 1
    data = json.loads(path.read_text())
    recs = data.get("records") or data["lnr1"]["records"]
    raw = bytearray(bytes.fromhex(recs[0]["raw_hex"] if isinstance(recs[0], dict) else recs[0]))
    raw[152] ^= 1
    recs[0] = {"raw_hex": raw.hex()} if isinstance(recs[0], dict) else raw.hex()
    tmp = path.with_suffix(".tamper.json")
    tmp.write_text(json.dumps(data))
    rc = verify(tmp, quiet=True)
    tmp.unlink(missing_ok=True)
    if rc == 0:
        print("FAIL: tampered q was accepted")
        return 1
    print("PASS: tampered quotient rejected")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_receipt.py <evidence.json> [--self-test]")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"FAIL: {path} missing")
        return 1
    if "--self-test" in sys.argv:
        return selftest(path)
    return verify(path)


if __name__ == "__main__":
    sys.exit(main())
