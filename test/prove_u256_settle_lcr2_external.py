#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end settle_u256_word vs Python ref_amount_out, with real LCR2 steps.

Proves:
  * EXACT_INPUT and OVERPAID_INPUT: LIN amount_out == floor(997*ain*rout / (rin*1000+997*ain))
  * OVERPAID: that value may differ from the on-chain amount_out (router overpay) — reported, not hidden
  * guards: zero inputs -> -1; 256-bit overflow of fee or numerator -> -2
  * LCR2 208-byte records bind image digest, inputs, LIN output, status, and VM steps > 0

Does not prove: FullMath 512-bit getAmountOut (u256 engine fail-closes high 256 of the product).
Auditor: --verify-receipt (hashlib + Python int; steps>0 checked, step replay needs lin_bc1_run).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
DATA = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u256_settle_lcr2_evidence.json"
IMG = ROOT / "examples" / "u512_coprocessor" / "u256_settlement_engine.linbc"

U256 = (1 << 256) - 1
M64 = (1 << 64) - 1
DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
RECORD = 208


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def ref_amount_out(a_in: int, r_in: int, r_out: int) -> tuple[int, int]:
    if a_in == 0 or r_in == 0 or r_out == 0:
        return -1, 0
    fee = a_in * 997
    den = r_in * 1000 + fee
    num = fee * r_out
    if fee > U256 or den > U256 or num > U256:
        return -2, 0
    return 1, num // den


def words(x: int) -> list[int]:
    ws = [(x >> (64 * i)) & M64 for i in range(4)]
    return [w - (1 << 64) if w >= (1 << 63) else w for w in ws]


def be32(x: int) -> bytes:
    return (x & U256).to_bytes(32, "big")


def pack_lcr2(digest: bytes, run_id: int, tx_id: int, ain, rin, rout, aout, steps, status) -> bytes:
    raw = bytearray(RECORD)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = digest
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx_id)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def merkle_root(recs: list[bytes]) -> str:
    nodes = [hashlib.sha256(DOM_LEAF + r).digest() for r in recs]
    while len(nodes) > 1:
        if len(nodes) & 1:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest()
                 for i in range(0, len(nodes), 2)]
    return nodes[0].hex()


def verify_receipt(path: Path) -> int:
    ev = json.loads(path.read_text())
    recs = [bytes.fromhex(h) for h in ev["lcr2"]["records_hex"]]
    for raw, meta in zip(recs, ev["lcr2"]["meta"]):
        if raw[0:4] != b"LCR2" or len(raw) != RECORD:
            print("FAIL schema")
            return 1
        steps = struct.unpack_from("<Q", raw, 184)[0]
        status = struct.unpack_from("<q", raw, 192)[0]
        ain = int.from_bytes(raw[56:88], "big")
        rin = int.from_bytes(raw[88:120], "big")
        rout = int.from_bytes(raw[120:152], "big")
        aout = int.from_bytes(raw[152:184], "big")
        st, ref = ref_amount_out(ain, rin, rout)
        if status != st or steps == 0:
            print("FAIL status/steps", meta, status, st, steps)
            return 1
        if st == 1 and aout != ref:
            print("FAIL aout", meta, aout, ref)
            return 1
        if st != 1 and aout != 0:
            print("FAIL rejected aout", meta)
            return 1
    root = merkle_root(recs)
    if root != ev["lcr2"]["root"]:
        print("FAIL merkle", root)
        return 1
    print("PASS: %d LCR2 records with real steps, root=%s" % (len(recs), root))
    return 0


class Eng:
    def __init__(self):
        IMG.parent.mkdir(parents=True, exist_ok=True)
        p = run([str(C0), "image", str(CORE), "-o", str(IMG)])
        if p.returncode != 0:
            raise RuntimeError(p.stdout + p.stderr)
        v = run([str(RUN), str(IMG), "--verify"])
        self.digest = bytes.fromhex(re.search(r'img_sha256="([0-9a-f]+)"', v.stdout).group(1))

    def call(self, args, idx):
        p = run([str(RUN), str(IMG), "settle_u256_word", *map(str, args), str(idx)])
        if p.returncode != 0 or 'EVALUATED' not in p.stdout:
            raise RuntimeError(p.stdout + p.stderr)
        return int(re.search(r"result=(-?\d+)", p.stdout).group(1)), int(re.search(r"steps=(\d+)", p.stdout).group(1))

    def settle(self, ain, rin, rout):
        args = words(ain) + words(rin) + words(rout)
        st, steps = self.call(args, -1)
        if st != 1:
            return st, 0, steps
        out = 0
        for i in range(4):
            w, s = self.call(args, i)
            steps += s
            out |= (w & M64) << (64 * i)
        return 1, out, steps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-receipt", default=None)
    ap.add_argument("--exact", type=int, default=8)
    args = ap.parse_args()
    if args.verify_receipt:
        return verify_receipt(Path(args.verify_receipt))

    if not C0.exists() or not RUN.exists():
        run(["make", "-C", str(ROOT / "transpile/c"), "c0", "bin/lin_bc1_run"], timeout=180)

    data = json.loads(DATA.read_text())
    recs = data["records"]
    exact = [r for r in recs if r["class"] == "EXACT_INPUT"][: args.exact]
    over = [r for r in recs if r["class"] == "OVERPAID_INPUT"]
    eng = Eng()
    per = Counter()
    records = []
    meta = []
    bad = []
    tx_id = 1

    def one(tag, ain, rin, rout, onchain=None):
        nonlocal tx_id
        st_ref, ref = ref_amount_out(ain, rin, rout)
        st, out, steps = eng.settle(ain, rin, rout)
        per[tag + ":n"] += 1
        if st != st_ref:
            bad.append((tag, "status", st, st_ref))
        elif st == 1 and out != ref:
            bad.append((tag, "aout", out, ref))
        else:
            per[tag + ":ok"] += 1
        if tag == "EXACT" and st == 1 and onchain is not None and out == onchain:
            per["EXACT:lin==onchain"] += 1
        if tag == "OVERPAID" and st == 1 and onchain is not None and out != onchain:
            per["OVERPAID:lin!=onchain"] += 1
        records.append(pack_lcr2(eng.digest, 1, tx_id, ain, rin, rout, out if st == 1 else 0, steps, st))
        meta.append({"tag": tag, "tx_id": tx_id, "steps": steps, "status": st})
        tx_id += 1

    for r in exact:
        one("EXACT", r["amount_in"], r["reserve_in"], r["reserve_out"], r["amount_out"])
    for r in over:
        one("OVERPAID", r["amount_in"], r["reserve_in"], r["reserve_out"], r["amount_out"])

    guards = [
        ("zero_ain", 0, 10**12, 10**21, -1),
        ("zero_rin", 10**6, 0, 10**21, -1),
        ("zero_rout", 10**6, 10**12, 0, -1),
        ("fee_ov", U256, 10**12, 10**21, -2),
        ("num_ov", U256 // 1000, 10**12, U256 // 2, -2),
    ]
    for name, a, ri, ro, want in guards:
        st, out, steps = eng.settle(a, ri, ro)
        if st != want or steps == 0:
            bad.append(("guard", name, st, want, steps))
        else:
            per["GUARD:ok"] += 1
        records.append(pack_lcr2(eng.digest, 1, tx_id, a, ri, ro, 0, steps, st))
        meta.append({"tag": "GUARD:" + name, "tx_id": tx_id, "steps": steps, "status": st})
        tx_id += 1

    # Contrast: coprocessor would approve phantom; u256 settlement overflow is a different formula.
    root = merkle_root(records)
    claims = [
        {"id": "EXACT-REF", "status": "PASS" if per["EXACT:ok"] == per["EXACT:n"] == per["EXACT:lin==onchain"] and per["EXACT:n"] else "FAIL",
         "note": "%d/%d lin==ref; lin==onchain %d/%d" % (
             per["EXACT:ok"], per["EXACT:n"], per["EXACT:lin==onchain"], per["EXACT:n"])},
        {"id": "OVERPAID-REF", "status": "PASS" if per["OVERPAID:ok"] == per["OVERPAID:n"] and per["OVERPAID:n"] else "FAIL",
         "note": "%d/%d lin==ref; lin!=onchain %d (expected for OVERPAID)" % (
             per["OVERPAID:ok"], per["OVERPAID:n"], per["OVERPAID:lin!=onchain"])},
        {"id": "GUARDS", "status": "PASS" if per["GUARD:ok"] == 5 else "FAIL",
         "note": "zero -> -1; fee/numerator 256 overflow -> -2"},
        {"id": "LCR2-STEPS", "status": "PASS" if all(m["steps"] > 0 for m in meta) else "FAIL",
         "note": "min_steps=%d" % min(m["steps"] for m in meta)},
    ]
    ev = {
        "schema": "LIN_U256_SETTLE_LCR2_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "dataset": str(DATA.relative_to(ROOT)),
        "filter_policy": data.get("filter_policy"),
        "image_sha256": eng.digest.hex(),
        "claims": claims,
        "counts": dict(per),
        "bad": [list(map(str, b)) for b in bad[:8]],
        "lcr2": {
            "record_bytes": RECORD,
            "domain_leaf": DOM_LEAF.decode(),
            "domain_node": DOM_NODE.decode(),
            "steps_bound": True,
            "count": len(records),
            "root": root,
            "records_hex": [r.hex() for r in records],
            "meta": meta,
        },
        "not_proved": [
            "FullMath 512-bit getAmountOut on settle_u256_word",
            "on-chain amount_out parity for OVERPAID_INPUT",
            "zk / computational soundness of Merkle",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(ev, indent=2) + "\n")
    vr = verify_receipt(EVIDENCE)
    claims.append({"id": "RECEIPT-AUDIT", "status": "PASS" if vr == 0 else "FAIL",
                   "note": "hashlib + ref_amount_out, no LIN"})
    ev["claims"] = claims
    EVIDENCE.write_text(json.dumps(ev, indent=2) + "\n")
    for c in claims:
        print("  [%s] %s  %s" % (c["status"], c["id"], c.get("note", "")))
    print("LCR2 root", root)
    if bad:
        print("bad", bad[:5])
    return 0 if not bad and vr == 0 and all(c["status"] == "PASS" for c in claims) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAIL exception:", e)
        sys.exit(1)
