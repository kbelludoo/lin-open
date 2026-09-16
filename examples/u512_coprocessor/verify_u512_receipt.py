#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent auditor for LNR1 u512 coprocessor receipts.
Zero LIN: Python stdlib only (json, hashlib, struct).
Recomputes every leaf, the merkle root, and q*d+r == a*b.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
U256M = (1 << 256) - 1


def leaf_hash(raw: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + raw).digest()


def merkle(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    if not nodes:
        raise ValueError("empty")
    while len(nodes) > 1:
        if len(nodes) & 1:
            nodes.append(nodes[-1])
        nxt = []
        for i in range(0, len(nodes), 2):
            nxt.append(hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest())
        nodes = nxt
    return nodes[0]


def u256_le(buf: bytes) -> int:
    return int.from_bytes(buf, "little")


def check_record(raw: bytes, rec: dict, digest: bytes) -> str | None:
    if len(raw) != 240:
        return f"len {len(raw)} != 240"
    if raw[0:4] != b"LNR1" or raw[4] != 1 or raw[5] != 1:
        return "bad header"
    if raw[8:40] != digest:
        return "image digest mismatch"
    a = u256_le(raw[48:80])
    b = u256_le(raw[80:112])
    d = u256_le(raw[112:144])
    q = u256_le(raw[144:176])
    r = u256_le(raw[176:208])
    status = struct.unpack_from("<q", raw, 208)[0]
    if a != int(rec["a"], 16) or b != int(rec["b"], 16) or d != int(rec["d"], 16):
        return "json/raw operand mismatch"
    n = a * b
    if d == 0:
        if status != -1:
            return "d=0 must be status -1"
        return None
    qq, rr = divmod(n, d)
    if qq > U256M:
        if status != -2:
            return "q overflow must be status -2"
        return None
    if status != 1:
        return f"expected status 1 got {status}"
    if q != qq or r != rr:
        return f"q/r mismatch raw=({q},{r}) py=({qq},{rr})"
    if q * d + r != n:
        return "identity failed"
    return None


def verify(path: Path, quiet: bool = False) -> int:
    ev = json.loads(path.read_text())
    records = ev["records"]
    digest = bytes.fromhex(ev["linbc1_sha256"])
    want_root = ev["lnr1_merkle_sha256"]
    leaves = []
    for rec in records:
        raw = bytes.fromhex(rec["raw_hex"])
        err = check_record(raw, rec, digest)
        if err:
            if not quiet:
                print(f"REJECT record {rec['id']}: {err}")
            return 1
        leaves.append(leaf_hash(raw))
    root = merkle(leaves).hex()
    if root != want_root:
        if not quiet:
            print(f"REJECT merkle {root} != {want_root}")
        return 1
    if not quiet:
        print(f"PASS: {len(records)} LNR1 records, merkle sha256:{root}")
        print("PASS: Python bigint remainder identity on every approved leaf")
        print("PASS: domain LIN:U512:LEAF:1 / LIN:U512:NODE:1")
        for row in ev.get("lcr2_slice") or []:
            raw = bytes.fromhex(row["raw_hex"])
            if len(raw) != 208 or raw[0:4] != b"LCR2":
                print(f"REJECT LCR2 {row.get('class')}")
                return 1
            ain = int.from_bytes(raw[56:88], "big")
            rin = int.from_bytes(raw[88:120], "big")
            rout = int.from_bytes(raw[120:152], "big")
            aout = int.from_bytes(raw[152:184], "big")
            fee = ain * 997
            ref = (fee * rout) // (rin * 1000 + fee)
            if aout != ref:
                print(f"REJECT LCR2 ref {row.get('class')}")
                return 1
            print(f"PASS: LCR2 {row['class']} steps={row['steps']} lin==ref "
                  f"onchain={'eq' if aout == row['onchain'] else 'neq'}")
    return 0


def tamper_must_fail(path: Path) -> int:
    ev = json.loads(path.read_text())
    raw = bytearray.fromhex(ev["records"][0]["raw_hex"])
    raw[48] ^= 1
    ev["records"][0]["raw_hex"] = raw.hex()
    tmp = path.with_suffix(".tampered.json")
    tmp.write_text(json.dumps(ev))
    rc = verify(tmp, quiet=True)
    tmp.unlink(missing_ok=True)
    if rc == 0:
        print("REJECT: tampered receipt was accepted")
        return 1
    print("PASS: 1-bit tamper rejected")
    return 0


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "examples/u512_coprocessor/u512_coprocessor_evidence.json"
    )
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 2
    print(f"auditor: {path} (no LIN binary)")
    if verify(path) != 0:
        return 1
    return tamper_must_fail(path)


if __name__ == "__main__":
    sys.exit(main())
