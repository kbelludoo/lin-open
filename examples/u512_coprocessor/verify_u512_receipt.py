#!/usr/bin/env python3
"""Independent auditor for LNR1 u512 coprocessor receipts. Python stdlib only."""
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
        nodes = [hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest()
                 for i in range(0, len(nodes), 2)]
    return nodes[0]


def check_record(raw: bytes, rec: dict, digest: bytes) -> str | None:
    if len(raw) != 240:
        return f"len {len(raw)} != 240"
    if raw[0:4] != b"LNR1" or raw[4] != 1 or raw[5] != 1:
        return "bad header"
    if raw[8:40] != digest:
        return "image digest mismatch"
    a = int.from_bytes(raw[48:80], "little")
    b = int.from_bytes(raw[80:112], "little")
    d = int.from_bytes(raw[112:144], "little")
    q = int.from_bytes(raw[144:176], "little")
    r = int.from_bytes(raw[176:208], "little")
    status = struct.unpack_from("<q", raw, 208)[0]
    if a != int(rec["a"], 16) or b != int(rec["b"], 16) or d != int(rec["d"], 16):
        return "json/raw operand mismatch"
    n = a * b
    if d == 0:
        return None if status == -1 else "d=0 must be status -1"
    qq, rr = divmod(n, d)
    if qq > U256M:
        return None if status == -2 else "q overflow must be status -2"
    if status != 1:
        return f"expected status 1 got {status}"
    if q != qq or r != rr or q * d + r != n:
        return "q/r/identity mismatch"
    return None


def verify(path: Path, quiet: bool = False) -> int:
    ev = json.loads(path.read_text())
    digest = bytes.fromhex(ev["linbc1_sha256"])
    want_root = ev["lnr1_merkle_sha256"]
    leaves = []
    for rec in ev["records"]:
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
        print(f"PASS: {len(ev['records'])} LNR1 records, merkle sha256:{root}")
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
            ref = (ain * 997 * rout) // (rin * 1000 + ain * 997)
            if aout != ref:
                print(f"REJECT LCR2 ref {row.get('class')}")
                return 1
            print(f"PASS: LCR2 {row['class']} steps={row['steps']} lin==ref "
                  f"onchain={'eq' if aout == row['onchain'] else 'neq'}")
        ph = ev.get("phantom_amm") or {}
        if ph:
            ain, rin = int(ph["amount_in"]), int(ph["reserve_in"])
            rout = int(ph["reserve_out"], 16)
            if ain * 997 * rout < (1 << 256):
                print("REJECT phantom AMM product fits in 256 bits")
                return 1
            ref = (ain * 997 * rout) // (rin * 1000 + ain * 997)
            if int(ph["ref"], 16) != ref or ph.get("coprocessor_status") != 1 or ph.get("u256_status") != -2:
                print("REJECT phantom AMM contrast")
                return 1
            print("PASS: phantom AMM product >= 2^256; coprocessor APPROVES; settle_u256_word ^-2")
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
