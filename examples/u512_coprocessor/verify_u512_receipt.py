#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN auditor for the u512 coprocessor receipt.

Recomputes LNR1 domain-separated SHA-256 (Python hashlib only) from the
evidence JSON, checks the 240-byte layout, rejects a 1-bit tamper, and
verifies the FullMath.sol *width* pin. Does not execute LinVM.

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


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_receipt.py <evidence.json> [--self-test]")
        return 2
    path = Path(sys.argv[1])
    ev = json.loads(path.read_text())
    if ev.get("schema") != "LIN_U512_COPROCESSOR_EVIDENCE_1.0":
        print("FAIL schema")
        return 1
    if ev.get("class") != "EXPERIMENTAL":
        print("FAIL class must stay EXPERIMENTAL")
        return 1
    if ev.get("lnr1_bytes") != 240:
        print("FAIL lnr1_bytes")
        return 1
    if ev.get("domains", {}).get("leaf") != "LIN:U512:LEAF:1":
        print("FAIL domain")
        return 1
    fm = hashlib.sha256(FULLMATH.read_bytes()).hexdigest()
    if fm != PIN_FM or ev.get("pins", {}).get("fullmath_sol") != PIN_FM:
        print("FAIL fullmath pin", fm)
        return 1
    leaves = ev.get("leaves") or []
    if not leaves:
        print("FAIL no leaves")
        return 1
    src_hex = ev["pins"]["lin_src"]
    src_d = bytes.fromhex(src_hex)
    recs = []
    for i, leaf in enumerate(leaves):
        recs.append(lnr1(
            src_d, 1, i, 2,
            parse_int(leaf["a"]), parse_int(leaf["b"]), parse_int(leaf["d"]),
            parse_int(leaf["q"]), parse_int(leaf["r"]),
            int(leaf.get("steps") or 0), int(leaf["status"]),
        ))
        if recs[-1][0:4] != b"LNR1" or len(recs[-1]) != 240:
            print("FAIL record layout")
            return 1
    root = merkle(recs).hex()
    tamp = bytearray(recs[0])
    tamp[56 + 31] ^= 1
    t_root = merkle([bytes(tamp)] + recs[1:]).hex()
    if t_root == root:
        print("FAIL tamper silent")
        return 1
    # Spot leaf is independently recomputable; the campaign merkle in
    # lnr1_merkle covers 65 records built by the harness and is not
    # reconstructed here (would require the full vector dump).
    q = parse_int(leaves[0]["q"])
    r = parse_int(leaves[0]["r"])
    a = parse_int(leaves[0]["a"])
    b = parse_int(leaves[0]["b"])
    d = parse_int(leaves[0]["d"])
    if leaves[0]["status"] == 1 and q * d + r != a * b:
        print("FAIL remainder identity on evidence leaf")
        return 1
    print("PASS standalone auditor")
    print("spot_merkle", root)
    print("tamper_rejected", t_root != root)
    print("fullmath", fm)
    print("lnr1_campaign_merkle", ev.get("lnr1_merkle"))
    print("lcr2_merkle", ev.get("lcr2_merkle"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
