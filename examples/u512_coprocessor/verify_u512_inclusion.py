#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN LIP1 auditor: verify a Merkle inclusion receipt without LinVM
and without the rest of the campaign. Schema 1.6.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

UMAX = (1 << 256) - 1


def fail(msg: str) -> int:
    print("FAIL", msg)
    return 1


def walk(leaf_hex: str, leaf_d: str, node_d: str, siblings: list[str],
         sides: list[int], root: str, leaf_sha: str) -> bool:
    rec = bytes.fromhex(leaf_hex)
    ld, nd = leaf_d.encode(), node_d.encode()
    h = hashlib.sha256(ld + rec).digest()
    if h.hex() != leaf_sha:
        return False
    for sib_hex, side in zip(siblings, sides):
        sib = bytes.fromhex(sib_hex)
        payload = h + sib if int(side) == 0 else sib + h
        h = hashlib.sha256(nd + payload).digest()
    return h.hex() == root


def parse_int(v) -> int:
    return v if isinstance(v, int) else int(v, 0)


def lri1_fields(leaf_hex: str) -> tuple[int, int, int, int] | None:
    rec = bytes.fromhex(leaf_hex)
    if len(rec) != 240 or rec[0:4] != b"LRI1":
        return None
    n = int.from_bytes(rec[56:88], "big") + (int.from_bytes(rec[88:120], "big") << 256)
    d = int.from_bytes(rec[120:152], "big")
    q = int.from_bytes(rec[152:184], "big")
    r = int.from_bytes(rec[184:216], "big")
    return n, d, q, r


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_inclusion.py <evidence.json>")
        return 2
    ev = json.loads(Path(sys.argv[1]).read_text())
    if ev.get("schema") != "LIN_U512_COPROCESSOR_EVIDENCE_1.6":
        return fail("schema")
    proofs = ev.get("lip1_proofs") or []
    if len(proofs) < 8:
        return fail(f"need >=8 LIP1 proofs, got {len(proofs)}")
    roots = {
        "LNR1": ev.get("lnr1_merkle"),
        "LCR2": ev.get("lcr2_merkle"),
        "LCR2_FULL": ev.get("lcr2_full_merkle"),
        "LGE1": ev.get("lge1_merkle"),
        "LRI1": ev.get("lri1_merkle"),
    }
    saw = set()
    n_ri = 0
    ri_by = {L.get("name"): L for L in (ev.get("lri1_leaves") or [])}
    for p in proofs:
        tree, name = p.get("tree"), p.get("name")
        if not walk(p["leaf_hex"], p["leaf_domain"], p["node_domain"],
                    p["siblings"], p["sides"], p["root"], p["leaf_sha256"]):
            return fail(f"path {tree}/{name}")
        if p["root"] != roots.get(tree):
            return fail(f"root {tree}/{name}")
        if tree == "LRI1":
            fld = lri1_fields(p["leaf_hex"])
            st = ri_by.get(name)
            if not fld or not st:
                return fail(f"LRI1 bind {name}")
            n, d, q, r = fld
            a, b = parse_int(st["a"]), parse_int(st["b"])
            if n != a * b or n != parse_int(st["n"]) or d != parse_int(st["d"]):
                return fail(f"LRI1 n {name}")
            if q * d + r != n or r >= d or q > UMAX:
                return fail(f"LRI1 identity {name}")
            n_ri += 1
        tamp = list(p["siblings"])
        if tamp:
            b = bytearray(bytes.fromhex(tamp[0]))
            b[0] ^= 1
            tamp[0] = bytes(b).hex()
            if walk(p["leaf_hex"], p["leaf_domain"], p["node_domain"],
                    tamp, p["sides"], p["root"], p["leaf_sha256"]):
                return fail(f"tamper silent {name}")
        saw.add(name)
    need = {"phantom_997_rout_1997", "wrap_borrow_2_x_2_255_div_umax",
            "two255_x2_div3", "max_sq", "GUARD_OVERFLOW", "PHANTOM_APPROVE"}
    missing = [k for k in need if k not in saw]
    if missing:
        return fail(f"required proofs missing: {missing}")
    if n_ri < 8:
        return fail(f"need 8 LRI1 inclusion proofs, got {n_ri}")
    print("PASS inclusion auditor")
    print("lip1_match", len(proofs))
    print("lri1_inclusion", n_ri)
    print("tamper_rejected", True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
