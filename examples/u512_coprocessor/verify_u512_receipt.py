#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN auditor for the u512 coprocessor receipt (schema 1.15).

Recomputes LNR1, LCR2, LCR2-full, LGE1, and LRI1 (remainder identity
q*d+r==n over the published 512-bit product) from published leaves.
Does not run LinVM.

  python3 examples/u512_coprocessor/verify_u512_receipt.py \\
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
LCR_LEAF = b"LIN:LEAF:1"
LCR_NODE = b"LIN:NODE:1"
GE_LEAF = b"LIN:U512:GE:LEAF:1"
GE_NODE = b"LIN:U512:GE:NODE:1"
RI_LEAF = b"LIN:U512:RI:LEAF:1"
RI_NODE = b"LIN:U512:RI:NODE:1"
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


def lcr2(img: bytes, run_id: int, tx: int, ain: int, rin: int, rout: int,
         aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def lge1(src_d: bytes, run_id: int, vid: int, a: int, b: int, ge: int, steps: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LGE1"
    raw[4] = 1
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(a & UMAX)
    raw[88:120] = be32(a >> 256)
    raw[120:152] = be32(b & UMAX)
    raw[152:184] = be32(b >> 256)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<Q", raw, 192, ge)
    return bytes(raw)


def lri1(src_d: bytes, run_id: int, vid: int, n: int, d: int, q: int, r: int,
         steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LRI1"
    raw[4] = 1
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(n & UMAX)
    raw[88:120] = be32(n >> 256)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle(recs: list[bytes], leaf_d: bytes, node_d: bytes) -> bytes:
    nodes = [hashlib.sha256(leaf_d + r).digest() for r in recs]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            L = nodes[i]
            R = nodes[i + 1] if i + 1 < len(nodes) else L
            nxt.append(hashlib.sha256(node_d + L + R).digest())
        nodes = nxt
    return nodes[0]


def parse_int(v) -> int:
    if isinstance(v, int):
        return v
    return int(v, 0)


def ref_amount_out(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > UMAX or den > UMAX or num > UMAX:
        return -2, 0
    return 1, num // den


def ref_amount_out_full(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    den = rin * 1000 + fee
    if fee > UMAX or den > UMAX:
        return -2, 0
    q = (fee * rout) // den
    if q > UMAX:
        return -2, 0
    return 1, q


def fail(msg: str) -> int:
    print("FAIL", msg)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_receipt.py <evidence.json> [--self-test]")
        return 2
    ev = json.loads(Path(sys.argv[1]).read_text())
    if ev.get("schema") != "LIN_U512_COPROCESSOR_EVIDENCE_1.15":
        return fail("schema")
    if ev.get("class") != "EXPERIMENTAL":
        return fail("class must stay EXPERIMENTAL")
    if ev.get("lnr1_bytes") != 240 or ev.get("lcr2_bytes") != 208 or ev.get("lge1_bytes") != 208:
        return fail("record sizes")
    if ev.get("lri1_bytes") != 240:
        return fail("lri1 size")
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
    root = merkle(recs, DOM_LEAF, DOM_NODE).hex()
    if root != ev.get("lnr1_merkle"):
        return fail(f"campaign merkle {root} != {ev.get('lnr1_merkle')}")
    tamp = bytearray(recs[0])
    tamp[56 + 31] ^= 1
    t_root = merkle([bytes(tamp)] + recs[1:], DOM_LEAF, DOM_NODE).hex()
    if t_root == root:
        return fail("tamper silent")

    img = bytes.fromhex(ev["pins"]["u256_linbc1"])
    run_id = int(ev.get("lcr2_run_id") or 2)
    lcr_leaves = ev.get("lcr2_leaves") or []
    if len(lcr_leaves) < 8:
        return fail(f"need >=8 LCR2 leaves (3 EXACT + 3 OVERPAID + 2 guards), got {len(lcr_leaves)}")
    n_ex = n_ov = n_z = n_p = 0
    lcr_recs = []
    for leaf in lcr_leaves:
        cls = leaf["class"]
        ain, rin, rout = parse_int(leaf["ain"]), parse_int(leaf["rin"]), parse_int(leaf["rout"])
        aout = parse_int(leaf["aout"])
        cop, ref_p, onch = parse_int(leaf["coprocessor"]), parse_int(leaf["ref"]), parse_int(leaf["onchain"])
        status, steps = int(leaf["status"]), int(leaf["steps"])
        tx = int(leaf.get("tx") or 0)
        if steps == 0:
            return fail(f"LCR2 {cls} steps=0")
        rst, ref = ref_amount_out(ain, rin, rout)
        if cls == "EXACT_INPUT":
            if status != 1 or rst != 1 or aout != ref or aout != onch or aout != cop:
                return fail(f"EXACT mismatch lin={aout} ref={ref} onchain={onch} cop={cop}")
            n_ex += 1
        elif cls == "OVERPAID_INPUT":
            if status != 1 or rst != 1 or aout != ref or aout != cop or aout == onch:
                return fail(f"OVERPAID mismatch lin={aout} ref={ref} onchain={onch}")
            n_ov += 1
        elif cls == "GUARD_ZERO":
            if status != -1 or rst != -1 or ain != 0:
                return fail("GUARD_ZERO")
            n_z += 1
        elif cls == "GUARD_OVERFLOW":
            if status != -2 or rst != -2:
                return fail("GUARD_OVERFLOW")
            n_p += 1
        else:
            return fail(f"unknown LCR2 class {cls}")
        lcr_recs.append(lcr2(img, run_id, tx, ain, rin, rout, aout, steps, status))
    if n_ex < 3 or n_ov < 3 or n_z < 1 or n_p < 1:
        return fail(f"LCR2 counts exact={n_ex} over={n_ov} z={n_z} ov={n_p}")
    lcr_root = merkle(lcr_recs, LCR_LEAF, LCR_NODE).hex()
    if lcr_root != ev.get("lcr2_merkle"):
        return fail(f"lcr2 merkle {lcr_root} != {ev.get('lcr2_merkle')}")

    img_f = bytes.fromhex(ev["pins"]["u512_linbc1"])
    run_f = int(ev.get("lcr2_full_run_id") or 3)
    full_leaves = ev.get("lcr2_full_leaves") or []
    if len(full_leaves) < 9:
        return fail(f"need >=9 LCR2-full leaves, got {len(full_leaves)}")
    n_ex = n_ov = n_z = n_ph = n_fee = 0
    full_recs = []
    for leaf in full_leaves:
        cls = leaf["class"]
        ain, rin, rout = parse_int(leaf["ain"]), parse_int(leaf["rin"]), parse_int(leaf["rout"])
        aout = parse_int(leaf["aout"])
        cop, onch = parse_int(leaf["coprocessor"]), parse_int(leaf["onchain"])
        status, steps = int(leaf["status"]), int(leaf["steps"])
        tx = int(leaf.get("tx") or 0)
        if steps == 0:
            return fail(f"LCR2-full {cls} steps=0")
        rst_s, ref_s = ref_amount_out(ain, rin, rout)
        rst_f, ref_f = ref_amount_out_full(ain, rin, rout)
        if cls == "EXACT_INPUT":
            if status != 1 or rst_f != 1 or aout != ref_f or aout != onch or aout != cop or ref_s != ref_f:
                return fail(f"FULL EXACT lin={aout} full={ref_f} onchain={onch}")
            n_ex += 1
        elif cls == "OVERPAID_INPUT":
            if status != 1 or rst_f != 1 or aout != ref_f or aout != cop or aout == onch:
                return fail(f"FULL OVERPAID lin={aout} full={ref_f} onchain={onch}")
            n_ov += 1
        elif cls == "PHANTOM_APPROVE":
            if status != 1 or rst_f != 1 or rst_s != -2 or aout != ref_f or aout != cop:
                return fail("PHANTOM_APPROVE")
            n_ph += 1
        elif cls == "GUARD_ZERO":
            if status != -1 or rst_f != -1 or ain != 0:
                return fail("FULL GUARD_ZERO")
            n_z += 1
        elif cls == "GUARD_FEE_OVERFLOW":
            if status != -2 or rst_f != -2 or ain != UMAX:
                return fail("GUARD_FEE_OVERFLOW")
            n_fee += 1
        else:
            return fail(f"unknown LCR2-full class {cls}")
        full_recs.append(lcr2(img_f, run_f, tx, ain, rin, rout, aout, steps, status))
    if n_ex < 3 or n_ov < 3 or n_z < 1 or n_ph < 1 or n_fee < 1:
        return fail(f"LCR2-full counts exact={n_ex} over={n_ov} z={n_z} ph={n_ph} fee={n_fee}")
    full_root = merkle(full_recs, LCR_LEAF, LCR_NODE).hex()
    if full_root != ev.get("lcr2_full_merkle"):
        return fail(f"lcr2_full merkle {full_root} != {ev.get('lcr2_full_merkle')}")

    ge_leaves = ev.get("lge1_leaves") or []
    if len(ge_leaves) != 8:
        return fail(f"need 8 LGE1 leaves, got {len(ge_leaves)}")
    if ev.get("lge1_domains", {}).get("leaf") != "LIN:U512:GE:LEAF:1":
        return fail("lge1 domain")
    run_g = int(ev.get("lge1_run_id") or 4)
    ge_recs = []
    saw_ge = {"boundary_2_256_ge_umax": False, "maxsq_ge_2_511": False, "max512_ge_1": False}
    for i, leaf in enumerate(ge_leaves):
        a, b = parse_int(leaf["a"]), parse_int(leaf["b"])
        ge, steps = int(leaf["ge"]), int(leaf["steps"])
        name = leaf.get("name") or ""
        if steps == 0:
            return fail(f"LGE1 {name} steps=0")
        want = 1 if a >= b else 0
        if ge != want:
            return fail(f"LGE1 {name} ge={ge} want={want}")
        if name in saw_ge:
            saw_ge[name] = True
        ge_recs.append(lge1(src_d, run_g, i, a, b, ge, steps))
    missing_ge = [k for k, v in saw_ge.items() if not v]
    if missing_ge:
        return fail(f"LGE1 required missing: {missing_ge}")
    ge_root = merkle(ge_recs, GE_LEAF, GE_NODE).hex()
    if ge_root != ev.get("lge1_merkle"):
        return fail(f"lge1 merkle {ge_root} != {ev.get('lge1_merkle')}")

    ri_leaves = ev.get("lri1_leaves") or []
    if len(ri_leaves) != 8:
        return fail(f"need 8 LRI1 leaves, got {len(ri_leaves)}")
    if ev.get("lri1_domains", {}).get("leaf") != "LIN:U512:RI:LEAF:1":
        return fail("lri1 domain")
    run_r = int(ev.get("lri1_run_id") or 5)
    ri_recs = []
    saw_ri = {"small_7x9_div2": False, "two255_x2_div3": False,
              "phantom_997_rout_1997": False, "wrap_borrow_2_x_2_255_div_umax": False}
    for i, leaf in enumerate(ri_leaves):
        a, b, d = parse_int(leaf["a"]), parse_int(leaf["b"]), parse_int(leaf["d"])
        n, q, r = parse_int(leaf["n"]), parse_int(leaf["q"]), parse_int(leaf["r"])
        status, steps = int(leaf["status"]), int(leaf["steps"])
        name = leaf.get("name") or ""
        if steps == 0:
            return fail(f"LRI1 {name} steps=0")
        if n != a * b:
            return fail(f"LRI1 {name} n!=a*b")
        if status != 1 or q * d + r != n or r >= d or q > UMAX:
            return fail(f"LRI1 {name} identity")
        if name in saw_ri:
            saw_ri[name] = True
        ri_recs.append(lri1(src_d, run_r, i, n, d, q, r, steps, status))
    missing_ri = [k for k, v in saw_ri.items() if not v]
    if missing_ri:
        return fail(f"LRI1 required missing: {missing_ri}")
    ri_root = merkle(ri_recs, RI_LEAF, RI_NODE).hex()
    if ri_root != ev.get("lri1_merkle"):
        return fail(f"lri1 merkle {ri_root} != {ev.get('lri1_merkle')}")

    print("PASS standalone auditor")
    print("merkle_match", root)
    print("lcr2_match", lcr_root)
    print("lcr2_full_match", full_root)
    print("lge1_match", ge_root)
    print("lri1_match", ri_root)
    print("tamper_rejected", t_root != root)
    print("fullmath", fm)
    print("leaves", len(leaves))
    print("lcr2_leaves", len(lcr_leaves))
    print("lcr2_full_leaves", len(full_leaves))
    print("lge1_leaves", len(ge_leaves))
    print("lri1_leaves", len(ri_leaves))
    return 0


if __name__ == "__main__":
    sys.exit(main())
