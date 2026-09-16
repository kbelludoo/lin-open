#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN auditor for the u512 coprocessor receipt.

Recomputes LNR1 domain-separated SHA-256 (Python hashlib only) from every
published leaf, requires the campaign merkle to match, checks remainder
identity on MULDIV leaves, and pins FullMath.sol *width*. Does not run LinVM.

  python3 examples/u512_coprocessor/verify_u512_receipt.py \
      examples/u512_coprocessor/u512_coprocessor_evidence.json --self-test
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
PIN_FM = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"
ROOT = Path(__file__).resolve().parents[2]
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
UMAX = (1 << 256) - 1
OP = {"MUL": 1, "MULDIV": 2}


def be32(x: int) -> bytes:
    return int(x).to_bytes(32, "big")


def lnr1(src_d: bytes, run_id: int, vid: int, op: int, a: int, b: int, d: int,
         q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = op
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(a)
    raw[88:120] = be32(b)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle(recs: list[bytes]) -> bytes:
    nodes = [hashlib.sha256(DOM_LEAF + r).digest() for r in recs]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            L = nodes[i]
            R = nodes[i + 1] if i + 1 < len(nodes) else L
            nxt.append(hashlib.sha256(DOM_NODE + L + R).digest())
        nodes = nxt
    return nodes[0]


def parse_int(v) -> int:
    if isinstance(v, int):
        return v
    return int(v, 0)


def fail(msg: str) -> int:
    print("FAIL", msg)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_receipt.py <evidence.json> [--self-test]")
        return 2
    ev = json.loads(Path(sys.argv[1]).read_text())
    if ev.get("schema") not in ("LIN_U512_COPROCESSOR_EVIDENCE_1.0", "LIN_U512_COPROCESSOR_EVIDENCE_1.1"):
        return fail("schema")
    if ev.get("class") != "EXPERIMENTAL":
        return fail("class must stay EXPERIMENTAL")
    if ev.get("lnr1_bytes") != 240:
        return fail("lnr1_bytes")
    if ev.get("domains", {}).get("leaf") != "LIN:U512:LEAF:1":
        return fail("domain")
    fm = hashlib.sha256(FULLMATH.read_bytes()).hexdigest()
    if fm != PIN_FM or ev.get("pins", {}).get("fullmath_sol") != PIN_FM:
        return fail(f"fullmath pin {fm}")
    leaves = ev.get("leaves") or []
    if len(leaves) < 8:
        return fail(f"need >=8 published leaves, got {len(leaves)}")
    src_d = bytes.fromhex(ev["pins"]["lin_src"])
    recs = []
    saw = {"mul_7x9": False, "md_7x9_2": False, "max_sq": False, "two255": False,
           "d0": False, "qov": False, "gao": False, "phantom": False}
    for i, leaf in enumerate(leaves):
        op = leaf.get("op", "MULDIV")
        if op not in OP:
            return fail(f"op {op}")
        a, b, d = parse_int(leaf["a"]), parse_int(leaf["b"]), parse_int(leaf["d"])
        q, r = parse_int(leaf["q"]), parse_int(leaf["r"])
        status, steps = int(leaf["status"]), int(leaf.get("steps") or 0)
        rec = lnr1(src_d, 1, i, OP[op], a, b, d, q, r, steps, status)
        if rec[0:4] != b"LNR1" or len(rec) != 240:
            return fail("record layout")
        recs.append(rec)
        if steps == 0:
            return fail(f"leaf {i} steps=0 (receipt must carry LIN steps)")
        if op == "MULDIV" and status == 1:
            if q * d + r != a * b or r >= d or q > UMAX:
                return fail(f"remainder identity leaf {i}")
        if op == "MUL" and status == 1:
            if q + (r << 256) != a * b:
                return fail(f"mul product leaf {i}")
        if op == "MUL" and a == 7 and b == 9 and q == 63:
            saw["mul_7x9"] = True
        if op == "MULDIV" and a == 7 and b == 9 and d == 2 and q == 31 and r == 1:
            saw["md_7x9_2"] = True
        if op == "MUL" and a == UMAX and b == UMAX and q == 1 and r == UMAX - 1:
            saw["max_sq"] = True
        if op == "MULDIV" and a == (1 << 255) and b == 2 and d == 3 and r == 1:
            saw["two255"] = True
        if op == "MULDIV" and d == 0 and status == -1:
            saw["d0"] = True
        if op == "MULDIV" and a == (1 << 255) and b == 2 and d == 1 and status == -2:
            saw["qov"] = True
        if op == "MULDIV" and a == 997000 and b == 20000 and q == 1813:
            saw["gao"] = True
        if op == "MULDIV" and a == 997 and d == 1997 and status == 1:
            saw["phantom"] = True
    missing = [k for k, v in saw.items() if not v]
    if missing:
        return fail(f"required leaves missing: {missing}")
    root = merkle(recs).hex()
    if root != ev.get("lnr1_merkle"):
        return fail(f"campaign merkle {root} != {ev.get('lnr1_merkle')}")
    tamp = bytearray(recs[0])
    tamp[56 + 31] ^= 1
    t_root = merkle([bytes(tamp)] + recs[1:]).hex()
    if t_root == root:
        return fail("tamper silent")
    print("PASS standalone auditor")
    print("merkle_match", root)
    print("tamper_rejected", t_root != root)
    print("fullmath", fm)
    print("leaves", len(leaves))
    print("lcr2_merkle", ev.get("lcr2_merkle"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
