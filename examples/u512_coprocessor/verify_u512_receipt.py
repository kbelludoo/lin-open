#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent auditor: no LIN binary. Python stdlib only.

Verifies LNR1 240-byte coprocessor records and LCR2 208-byte settlement
records against Python int and SHA-256 Merkle roots in the evidence JSON.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
OP_MUL, OP_GE, OP_DIV, OP_MULDIV, OP_AMM = 1, 2, 3, 4, 5


def be32(b: bytes) -> int:
    return int.from_bytes(b, "big")


def merkle(records: list[bytes], leaf_dom: bytes, node_dom: bytes) -> bytes:
    cur = [hashlib.sha256(leaf_dom + x).digest() for x in records]
    if not cur:
        raise ValueError("empty")
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(hashlib.sha256(node_dom + l + r).digest())
        cur = nxt
    return cur[0]


def check_lnr1(rec: bytes, img: bytes) -> str | None:
    if len(rec) != 240 or rec[0:4] != b"LNR1" or rec[4] != 1 or rec[5] != 1:
        return "bad LNR1 header"
    if rec[8:40] != img:
        return "LNR1 image digest mismatch"
    op = struct.unpack_from("<Q", rec, 56)[0]
    a = be32(rec[64:96])
    b = be32(rec[96:128])
    d = be32(rec[128:160])
    q = be32(rec[160:192])
    r = be32(rec[192:224])
    steps = struct.unpack_from("<Q", rec, 224)[0]
    status = struct.unpack_from("<q", rec, 232)[0]
    if steps == 0:
        return "LNR1 steps=0 (not a VM receipt)"
    if op == OP_MUL:
        if q + (r << 256) != a * b:
            return f"mul identity fail a={a} b={b}"
    elif op == OP_GE:
        left = a + (b << 256)
        right = d + (q << 256)
        if status not in (0, 1) or status != (1 if left >= right else 0):
            return f"ge mismatch {left} vs {right} status={status}"
    elif op == OP_DIV:
        n = a + (b << 256)
        if d == 0:
            if status != -1:
                return "div d=0 expected -1"
        elif n // d > U256:
            if status != -2:
                return "div q overflow expected -2"
        elif status != 1 or q * d + r != n or r >= d:
            return f"div remainder fail q*d+r={q*d+r} n={n}"
    elif op == OP_MULDIV:
        if d == 0:
            if status != -1:
                return "muldiv d=0 expected -1"
        elif (a * b) // d > U256:
            if status != -2:
                return "muldiv q overflow expected -2"
        elif status != 1 or q * d + r != a * b or r >= d:
            return f"muldiv remainder fail"
    elif op == OP_AMM:
        if a == 0 or b == 0 or d == 0:
            if status != -1:
                return "amm zero expected -1"
        else:
            fee = a * 997
            den = b * 1000 + fee
            if fee > U256 or den > U256:
                if status != -2:
                    return "amm 256 overflow expected -2"
            else:
                exp = (fee * d) // den
                if status != 1 or q != exp:
                    return f"amm q={q} exp={exp}"
    else:
        return f"unknown op {op}"
    return None


def check_lcr2(rec: bytes, img: bytes) -> str | None:
    if len(rec) != 208 or rec[0:4] != b"LCR2" or rec[4] != 1 or rec[5] != 1:
        return "bad LCR2 header"
    if rec[8:40] != img:
        return "LCR2 image digest mismatch"
    ain = be32(rec[56:88])
    rin = be32(rec[88:120])
    rout = be32(rec[120:152])
    aout = be32(rec[152:184])
    steps = struct.unpack_from("<Q", rec, 184)[0]
    status = struct.unpack_from("<q", rec, 192)[0]
    if steps == 0:
        return "LCR2 steps=0 (legacy oracle receipts are not this campaign)"
    if ain == 0 or rin == 0 or rout == 0:
        return None if status == -1 else "LCR2 zero input"
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > U256 or num > U256 or den > U256:
        return None if status == -2 else "LCR2 expected SafeMath -2"
    exp = num // den
    if status != 1 or aout != exp:
        return f"LCR2 aout={aout} exp={exp}"
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_receipt.py <evidence.json>", file=sys.stderr)
        return 2
    ev_path = Path(sys.argv[1])
    ev = json.loads(ev_path.read_text())
    base = ev_path.parent
    lnr1_path = base / "u512_lnr1.bin"
    lcr2_path = base / "u256_lcr2_e2e.bin"
    img = bytes.fromhex(ev["img_sha256"])
    u256_img = bytes.fromhex(ev["u256_img_sha256"])
    blob = lnr1_path.read_bytes()
    if len(blob) % 240 != 0:
        print("FAIL: LNR1 blob length", file=sys.stderr)
        return 1
    recs = [blob[i:i + 240] for i in range(0, len(blob), 240)]
    if len(recs) != ev["lnr1_count"]:
        print("FAIL: LNR1 count", file=sys.stderr)
        return 1
    leaf = ev["domains"]["lnr1_leaf"].encode()
    node = ev["domains"]["lnr1_node"].encode()
    root = merkle(recs, leaf, node)
    if root.hex() != ev["lnr1_merkle"]:
        print("FAIL: LNR1 merkle", file=sys.stderr)
        return 1
    for i, rec in enumerate(recs):
        err = check_lnr1(rec, img)
        if err:
            print(f"FAIL: LNR1[{i}] {err}", file=sys.stderr)
            return 1
    tampered = bytearray(recs[0])
    tampered[64] ^= 1
    t_root = merkle([bytes(tampered)] + recs[1:], leaf, node)
    if t_root == root:
        print("FAIL: tamper did not change LNR1 root", file=sys.stderr)
        return 1
    l2 = lcr2_path.read_bytes()
    if len(l2) % 208 != 0 or len(l2) == 0:
        print("FAIL: LCR2 blob", file=sys.stderr)
        return 1
    l2recs = [l2[i:i + 208] for i in range(0, len(l2), 208)]
    l2root = merkle(l2recs, ev["domains"]["lcr2_leaf"].encode(), ev["domains"]["lcr2_node"].encode())
    if l2root.hex() != ev["lcr2_merkle"]:
        print("FAIL: LCR2 merkle", file=sys.stderr)
        return 1
    for i, rec in enumerate(l2recs):
        err = check_lcr2(rec, u256_img)
        if err:
            print(f"FAIL: LCR2[{i}] {err}", file=sys.stderr)
            return 1
    if ev.get("verdict") != "PASS":
        print("FAIL: evidence verdict is not PASS", file=sys.stderr)
        return 1
    print("PASS: LNR1", len(recs), "root", root.hex())
    print("PASS: LCR2", len(l2recs), "root", l2root.hex())
    print("PASS: tamper changes LNR1 root")
    print("PASS: independent Python bigint matches every record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
