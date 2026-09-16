#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.7: LIP1 inclusion + all LCR2 E2E leaves; Java still compiled here."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from prove_u512_ge import ge_batch_lines
from prove_u512_lib import (
    DOM_LEAF, DOM_NODE, GE_LEAF, GE_NODE, LCR_LEAF, LCR_NODE, RI_LEAF, RI_NODE, ROOT,
    run, sha256_file,
)

JAVA_SRC = ROOT / "test" / "oracles" / "u512_java_oracle.java"
JAVA_DIR = Path("/tmp/u512java")
JAVA_CLASS = "U512JavaOracle"
VERIFY_INC = ROOT / "examples" / "u512_coprocessor" / "verify_u512_inclusion.py"
VERIFY_INC_JS = ROOT / "examples" / "u512_coprocessor" / "verify_u512_inclusion.js"

TREES = {
    "LNR1": (DOM_LEAF, DOM_NODE, 240, 1),
    "LCR2": (LCR_LEAF, LCR_NODE, 208, 2),
    "LCR2_FULL": (LCR_LEAF, LCR_NODE, 208, 3),
    "LGE1": (GE_LEAF, GE_NODE, 208, 4),
    "LRI1": (RI_LEAF, RI_NODE, 240, 5),
}


def compile_java() -> tuple[bool, str]:
    JAVA_DIR.mkdir(exist_ok=True)
    p = run(["javac", "-d", str(JAVA_DIR), str(JAVA_SRC)], timeout=90)
    cls = JAVA_DIR / f"{JAVA_CLASS}.class"
    return p.returncode == 0 and cls.exists(), (p.stderr or "")[-300:]


def java_cmd() -> list[str]:
    return ["java", "-cp", str(JAVA_DIR), JAVA_CLASS]


def java_selftest() -> tuple[bool, str]:
    p = run(java_cmd() + ["--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def _java_batch(lines: str, expect: list[tuple[int, int, int]]) -> tuple[bool, int, str]:
    p = run(java_cmd() + ["--batch"], inp=lines, timeout=90)
    rows = [ln.split() for ln in p.stdout.splitlines() if ln]
    ok = p.returncode == 0 and len(rows) == len(expect)
    if ok:
        for (stt, q, r), row in zip(expect, rows):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                ok = False
                break
    return ok, len(expect), (p.stderr or "").strip()


def java_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run(java_cmd() + ["--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            if int(got.split()[0]) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def run_java_oracle(lines: str, expect: list[tuple[int, int, int]]) -> dict:
    cc, err = compile_java()
    st, stout = java_selftest() if cc else (False, "no class")
    ok, n, berr = _java_batch(lines, expect) if cc else (False, 0, "no class")
    ge_ok, ge_err = java_ge_batch() if cc else (False, "no class")
    return {
        "compile": cc, "compile_err": err,
        "selftest": st, "selftest_out": stout,
        "batch": ok, "n": n, "batch_err": berr,
        "ge": ge_ok, "ge_err": ge_err,
        "src": sha256_file(JAVA_SRC),
    }


def recs_of(blob: Path, sz: int) -> list[bytes]:
    b = blob.read_bytes()
    return [b[i:i + sz] for i in range(0, len(b), sz)]


def inclusion_proof(recs: list[bytes], leaf_d: bytes, node_d: bytes, index: int):
    layer = [hashlib.sha256(leaf_d + r).digest() for r in recs]
    siblings, sides = [], []
    i = index
    while len(layer) > 1:
        if i % 2 == 0:
            sides.append(0)
            siblings.append(layer[i + 1] if i + 1 < len(layer) else layer[i])
        else:
            sides.append(1)
            siblings.append(layer[i - 1])
        nxt = []
        for j in range(0, len(layer), 2):
            L = layer[j]
            R = layer[j + 1] if j + 1 < len(layer) else L
            nxt.append(hashlib.sha256(node_d + L + R).digest())
        layer = nxt
        i //= 2
    return siblings, sides, layer[0]


def verify_inclusion(rec: bytes, leaf_d: bytes, node_d: bytes,
                     siblings: list[bytes], sides: list[int], root: bytes) -> bool:
    h = hashlib.sha256(leaf_d + rec).digest()
    for sib, side in zip(siblings, sides):
        h = hashlib.sha256(node_d + (h + sib if side == 0 else sib + h)).digest()
    return h == root


def pack_lip1(tree_id: int, index: int, leaf_h: bytes, root: bytes,
              siblings: list[bytes], sides: list[int]) -> bytes:
    raw = bytearray(80 + 36 * len(siblings))
    raw[0:4] = b"LIP1"
    raw[4] = 1
    raw[5] = tree_id
    struct.pack_into("<I", raw, 8, index)
    struct.pack_into("<I", raw, 12, len(siblings))
    raw[16:48] = leaf_h
    raw[48:80] = root
    off = 80
    for sib, side in zip(siblings, sides):
        raw[off] = side & 1
        raw[off + 4:off + 36] = sib
        off += 36
    return bytes(raw)


def make_proof(tree: str, name: str, index: int, recs: list[bytes]) -> dict:
    leaf_d, node_d, _sz, tree_id = TREES[tree]
    rec = recs[index]
    sibs, sides, root = inclusion_proof(recs, leaf_d, node_d, index)
    ok = verify_inclusion(rec, leaf_d, node_d, sibs, sides, root)
    tamp = bytearray(sibs[0]) if sibs else bytearray(hashlib.sha256(leaf_d + rec).digest())
    tamp[0] ^= 1
    tamp_sibs = [bytes(tamp)] + sibs[1:] if sibs else [bytes(tamp)]
    tamp_ok = (not sibs) or (not verify_inclusion(rec, leaf_d, node_d, tamp_sibs, sides, root))
    return {
        "tree": tree, "name": name, "index": index, "tree_id": tree_id,
        "leaf_domain": leaf_d.decode(), "node_domain": node_d.decode(),
        "leaf_hex": rec.hex(), "leaf_sha256": hashlib.sha256(leaf_d + rec).hexdigest(),
        "siblings": [s.hex() for s in sibs], "sides": sides, "root": root.hex(),
        "ok": ok and tamp_ok,
    }


def make_lip1(lnr1: list[bytes], lnr1_root: str, lcr2: list[bytes], lcr2_root: str,
              full_blob: Path, ge_blob: Path, ri_blob: Path, full_root: str,
              ge_root: str, ri_root: str, aud: Path, lcr_leaves: list[dict],
              full_leaves: list[dict], ge_leaves: list[dict],
              ri_leaves: list[dict], lnr1_leaves: list[dict]) -> dict:
    full_recs = recs_of(full_blob, 208)
    ge_recs = recs_of(ge_blob, 208)
    ri_recs = recs_of(ri_blob, 240)
    proofs = []
    for i, leaf in enumerate(ri_leaves):
        proofs.append(make_proof("LRI1", leaf.get("name") or f"ri{i}", i, ri_recs))
    for i, leaf in enumerate(ge_leaves):
        proofs.append(make_proof("LGE1", leaf.get("name") or f"ge{i}", i, ge_recs))
    proofs.append(make_proof("LNR1", "max_sq", 2, lnr1))
    for i, leaf in enumerate(lcr_leaves):
        proofs.append(make_proof("LCR2", f"{leaf.get('class')}_{i}", i, lcr2))
    ph_i = next(i for i, L in enumerate(full_leaves) if L.get("class") == "PHANTOM_APPROVE")
    proofs.append(make_proof("LCR2_FULL", "PHANTOM_APPROVE", ph_i, full_recs))
    ok = all(p["ok"] for p in proofs)
    names = {p["name"] for p in proofs}
    n_ex = sum(1 for p in proofs if p["name"].startswith("EXACT_INPUT_"))
    n_ov = sum(1 for p in proofs if p["name"].startswith("OVERPAID_INPUT_"))
    n_z = sum(1 for p in proofs if p["name"].startswith("GUARD_ZERO_"))
    n_ovf = sum(1 for p in proofs if p["name"].startswith("GUARD_OVERFLOW_"))
    need = {"phantom_997_rout_1997", "wrap_borrow_2_x_2_255_div_umax", "two255_x2_div3",
            "max_sq", "PHANTOM_APPROVE", "boundary_2_256_ge_umax"}
    ok = ok and need <= names and n_ex >= 3 and n_ov >= 3 and n_z >= 1 and n_ovf >= 1
    for p, root in (("LNR1", lnr1_root), ("LCR2", lcr2_root), ("LCR2_FULL", full_root),
                    ("LGE1", ge_root), ("LRI1", ri_root)):
        for pr in proofs:
            if pr["tree"] == p and pr["root"] != root:
                ok = False
    ph = next(p for p in proofs if p["name"] == "phantom_997_rout_1997")
    leaf_d, node_d, _sz, tid = TREES["LRI1"]
    rec = bytes.fromhex(ph["leaf_hex"])
    sibs = [bytes.fromhex(s) for s in ph["siblings"]]
    root_b = bytes.fromhex(ph["root"])
    leaf_h = hashlib.sha256(leaf_d + rec).digest()
    blob = Path("/tmp/u512_lip1_phantom.bin")
    blob.write_bytes(pack_lip1(tid, ph["index"], leaf_h, root_b, sibs, ph["sides"]))
    c = run([str(aud), "--lip1", str(blob)])
    c_ok = c.returncode == 0 and "LIP1_PASS" in c.stdout and ph["root"] in c.stdout
    tamp = bytearray(blob.read_bytes())
    tamp[80 + 4] ^= 1
    tpath = Path("/tmp/u512_lip1_tamper.bin")
    tpath.write_bytes(bytes(tamp))
    t = run([str(aud), "--lip1", str(tpath)])
    t_ok = t.returncode != 0
    ex = next(p for p in proofs if p["name"].startswith("EXACT_INPUT_"))
    leaf_d2, node_d2, _sz2, tid2 = TREES["LCR2"]
    rec2 = bytes.fromhex(ex["leaf_hex"])
    sibs2 = [bytes.fromhex(s) for s in ex["siblings"]]
    root2 = bytes.fromhex(ex["root"])
    leaf_h2 = hashlib.sha256(leaf_d2 + rec2).digest()
    blob_ex = Path("/tmp/u512_lip1_lcr2_exact.bin")
    blob_ex.write_bytes(pack_lip1(tid2, ex["index"], leaf_h2, root2, sibs2, ex["sides"]))
    c_ex = run([str(aud), "--lip1", str(blob_ex)])
    c_ex_ok = c_ex.returncode == 0 and "LIP1_PASS" in c_ex.stdout and ex["root"] in c_ex.stdout
    tamp2 = bytearray(blob_ex.read_bytes())
    tamp2[80 + 4] ^= 1
    tpath2 = Path("/tmp/u512_lip1_lcr2_tamper.bin")
    tpath2.write_bytes(bytes(tamp2))
    t2 = run([str(aud), "--lip1", str(tpath2)])
    t2_ok = t2.returncode != 0
    return {
        "ok": ok, "c11": c_ok and t_ok, "c11_lcr2": c_ex_ok and t2_ok,
        "detail": f"n={len(proofs)} lcr2={n_ex}+{n_ov}+{n_z}+{n_ovf} names={sorted(need & names)}",
        "c11_detail": (c.stdout or "")[:160],
        "c11_lcr2_detail": (c_ex.stdout or "")[:160],
        "proofs": [{k: v for k, v in p.items() if k != "ok"} for p in proofs],
        "n": len(proofs), "blob": blob, "blob_lcr2": blob_ex,
    }


def java_check_tuples(lines: str, expect: list, match: bool):
    java = run_java_oracle(lines, expect)
    return java, [
        ("java_bigint_compile", java["compile"], java["compile_err"]),
        ("java_bigint_selftest", java["selftest"], java["selftest_out"]),
        ("java_python_c11_full_range", java["batch"] and match, f"n={java['n']} {java['batch_err']}"),
        ("java_ge512", java["ge"], java["ge_err"]),
    ]


def inclusion_auditor_tuples(evid: Path):
    from prove_u512_lib import node_bin
    import sys
    ip = run([sys.executable, str(VERIFY_INC), str(evid)], timeout=30)
    ij = run([node_bin(), str(VERIFY_INC_JS), str(evid)], timeout=30)
    return [
        ("standalone_inclusion_py", ip.returncode == 0 and "lip1_match" in ip.stdout
         and "lcr2_inclusion" in ip.stdout, ip.stdout.strip()[:200]),
        ("standalone_inclusion_js", ij.returncode == 0 and "lip1_match" in ij.stdout
         and "lcr2_inclusion" in ij.stdout, ij.stdout.strip()[:200]),
    ]

