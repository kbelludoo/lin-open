#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E slice: settle_u256_word vs Python ref_amount_out on EXACT/OVERPAID,
fail-closed guards -1/-2, real LinVM steps bound into LCR2 (208 B).

Honest scope: 4 LCR2 leaves (B=4). Does not replace the 157/2000 campaign.
512-bit coprocessor proof is separate (test/prove_u512_coprocessor_external.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples" / "defi_settlement_proof" / "sdk"))
from verify_u256_client import verify_u256_block_bundle  # noqa: E402

C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
CORE = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
COPROC = ROOT / "src" / "lin_u512_coprocessor.lin"
JSON_IN = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
OUT = ROOT / "examples" / "u512_coprocessor" / "u256_lcr2_e2e_evidence.json"
M64 = (1 << 64) - 1
U256 = (1 << 256) - 1
DOM_LEAF = b"LIN:LEAF:1"


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def i64(w):
    w &= M64
    return w - (1 << 64) if w >= (1 << 63) else w


def words(x):
    return [i64((x >> (64 * i)) & M64) for i in range(4)]


def from_words(ws):
    out = 0
    for i, w in enumerate(ws):
        out |= (w & M64) << (64 * i)
    return out


def ref_amount_out(a_in, r_in, r_out):
    fee = a_in * 997
    return (fee * r_out) // (r_in * 1000 + fee)


def lin_run(img, fn, args, timeout=180):
    p = run([str(C0), "run", str(img), fn, *[str(a) for a in args]], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    m = re.search(r"value=(-?\d+)\s+steps=(\d+)", p.stdout)
    if not m:
        raise RuntimeError(p.stdout)
    return int(m.group(1)), int(m.group(2))


def settle(img, a, r_in, r_out):
    args = words(a) + words(r_in) + words(r_out)
    st, steps = lin_run(img, "settle_u256_word", args + [-1])
    if st != 1:
        return st, None, steps
    ws = []
    tot = steps
    for i in range(4):
        v, s = lin_run(img, "settle_u256_word", args + [i])
        ws.append(v)
        tot += s
    return 1, from_words(ws), tot


def be32(x):
    return (x & U256).to_bytes(32, "big")


def pack_lcr2(img_d, run_id, tx_id, ain, rin, rout, aout, steps, status):
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img_d
    struct.pack_into("<QQ", raw, 40, run_id, tx_id)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Qq", raw, 184, steps, status)
    return bytes(raw)


def first_of(recs, cls):
    for r in recs:
        if r.get("class") == cls:
            return r
    raise SystemExit(f"no {cls} in dataset")


def main() -> int:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0:
            print(p.stderr)
            return 2
    img_path = Path("/tmp/u256_settle_e2e.linbc")
    p = run([str(C0), "image", str(CORE), "-o", str(img_path)])
    if p.returncode != 0:
        print(p.stdout, p.stderr)
        return 1
    blob = img_path.read_bytes()
    digest = hashlib.sha256(b"linbc1:img:" + blob[:-32]).digest()
    if digest != blob[-32:]:
        print("self-hash mismatch")
        return 1
    data = json.loads(JSON_IN.read_text())
    recs = data["records"]
    exact = first_of(recs, "EXACT_INPUT")
    over = first_of(recs, "OVERPAID_INPUT")
    phantom_rout = ((1 << 256) + 996) // 997

    cases = [
        ("EXACT_INPUT", exact["amount_in"], exact["reserve_in"], exact["reserve_out"],
         exact["amount_out"], exact["get_amount_out"]),
        ("OVERPAID_INPUT", over["amount_in"], over["reserve_in"], over["reserve_out"],
         over["amount_out"], over["get_amount_out"]),
        ("GUARD_ZERO", 0, exact["reserve_in"], exact["reserve_out"], None, None),
        ("PHANTOM_SAFE_MATH", 1, 1, phantom_rout, None, None),
    ]
    txs = []
    notes = []
    for i, (cls, ain, rin, rout, onchain, gout) in enumerate(cases, start=1):
        st, out, steps = settle(img_path, ain, rin, rout)
        ref = None if ain == 0 or rin == 0 or rout == 0 else ref_amount_out(ain, rin, rout)
        if cls == "EXACT_INPUT":
            if st != 1 or out != ref or out != onchain or out != gout:
                print(f"FAIL EXACT lin={out} ref={ref} onchain={onchain}")
                return 1
        elif cls == "OVERPAID_INPUT":
            if st != 1 or out != ref or out != gout:
                print(f"FAIL OVERPAID lin={out} ref={ref} get={gout} onchain={onchain}")
                return 1
        elif cls == "GUARD_ZERO":
            if st != -1:
                print(f"FAIL zero guard {st}")
                return 1
        elif cls == "PHANTOM_SAFE_MATH":
            if st != -2:
                print(f"FAIL phantom expected -2 got {st}")
                return 1
            cop_img = Path("/tmp/u512_cop_e2e.linbc")
            q = run([str(C0), "image", str(COPROC), "-o", str(cop_img)])
            if q.returncode != 0:
                print(q.stdout)
                return 1
            md = words(997) + words(phantom_rout) + words(1997) + [-1]
            cst, cstp = lin_run(cop_img, "u512_muldiv_word", md, timeout=300)
            notes.append({
                "phantom_settler_status": st,
                "phantom_coprocessor_status": cst,
                "phantom_coprocessor_steps": cstp,
                "phantom_ref": ref,
            })
            if cst != 1:
                print(f"FAIL phantom coprocessor {cst} (settler -2 is expected; coprocessor must APPROVE)")
                return 1
        raw = pack_lcr2(digest, 1, 3000 + i, ain, rin, rout, out or 0, steps, st)
        leaf = hashlib.sha256(DOM_LEAF + raw).digest()
        txs.append({
            "class": cls,
            "run_id": 1,
            "tx_id": 3000 + i,
            "amount_in_hex": be32(ain).hex(),
            "reserve_in_hex": be32(rin).hex(),
            "reserve_out_hex": be32(rout).hex(),
            "amount_out_hex": be32(out or 0).hex(),
            "steps": steps,
            "status_code": st,
            "raw_record_hex": raw.hex(),
            "leaf_hash_hex": leaf.hex(),
            "lin_out": None if out is None else str(out),
            "ref_out": None if ref is None else str(ref),
            "onchain_out": None if onchain is None else str(onchain),
            "tx_hash": exact["tx_hash"] if cls == "EXACT_INPUT" else (over["tx_hash"] if cls == "OVERPAID_INPUT" else None),
        })
        print(f"  {cls:20s} status={st:2d} steps={steps} lin={out} ref={ref}")

    n0 = hashlib.sha256(b"LIN:NODE:1" + bytes.fromhex(txs[0]["leaf_hash_hex"]) + bytes.fromhex(txs[1]["leaf_hash_hex"])).digest()
    n1 = hashlib.sha256(b"LIN:NODE:1" + bytes.fromhex(txs[2]["leaf_hash_hex"]) + bytes.fromhex(txs[3]["leaf_hash_hex"])).digest()
    root = hashlib.sha256(b"LIN:NODE:1" + n0 + n1).hexdigest()
    bundle = {
        "schema": "LIN_U256_LCR2_E2E_SLICE_1.0",
        "image_loader_digest": digest.hex(),
        "merkle_root_sha256": root,
        "transactions": txs,
        "notes": notes,
        "not_claimed": [
            "full unfiltered 157-swap campaign",
            "settle_u256_word equals FullMath (phantom still -2; 512 coprocessor approves)",
        ],
    }
    vr = verify_u256_block_bundle(bundle, digest.hex())
    bundle["auditor"] = vr
    OUT.write_text(json.dumps(bundle, indent=2) + "\n")
    print(f"  LCR2 root {root} auditor={vr.get('valid')}")
    return 0 if vr.get("valid") else 1


if __name__ == "__main__":
    sys.exit(main())
