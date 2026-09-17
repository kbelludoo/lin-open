#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.3 helpers: Node BigInt consensus + FullMath-width LCR2 from settle_u512_swap."""
from __future__ import annotations

import hashlib
from pathlib import Path

from prove_u512_lib import (
    C0, LCR_LEAF, LCR_NODE, ROOT, U512A, UMAX,
    lcr2, lcr2_dict, merkle, node_bin, ref_amount_out, ref_amount_out_full,
    run, sha256_file, settle_u512,
)

NODE_ORACLE = ROOT / "test" / "oracles" / "u512_node_oracle.js"
VERIFY_JS = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.js"


def node_selftest() -> tuple[bool, str]:
    node = node_bin()
    p = run([node, str(NODE_ORACLE), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def node_batch(lines: str, expect: list[tuple[int, int, int]]) -> tuple[bool, int, str]:
    node = node_bin()
    p = run([node, str(NODE_ORACLE), "--batch"], inp=lines, timeout=60)
    rows = [ln.split() for ln in p.stdout.splitlines() if ln]
    ok = p.returncode == 0 and len(rows) == len(expect)
    if ok:
        for (stt, q, r), row in zip(expect, rows):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                ok = False
                break
    return ok, len(expect), (p.stderr or "").strip()


def collect_lcr2_full(exacts: list[dict], overs: list[dict],
                      rout_phantom: int) -> dict:
    img_p = Path("/tmp/u512_uniswap.linbc")
    im = run([str(C0), "image", str(U512A), "-o", str(img_p)])
    img_h = hashlib.sha256(img_p.read_bytes()).digest() if img_p.exists() else b"\x00" * 32
    recs, leaves, rows, detail = [], [], [], []
    e2e_ok = im.returncode == 0 and img_p.exists()
    for rec in exacts + overs:
        ain, rin, rout_v = rec["amount_in"], rec["reserve_in"], rec["reserve_out"]
        rst_s, ref_s = ref_amount_out(ain, rin, rout_v)
        rst_f, ref_f = ref_amount_out_full(ain, rin, rout_v)
        nwords = 4 if ref_f >= (1 << 64) else 1
        st, got, steps = settle_u512(ain, rin, rout_v, nwords=nwords)
        match = st == rst_f == 1 and got == ref_f and rst_s == 1 and ref_s == ref_f and steps != 0
        if rec["class"] == "EXACT_INPUT" and got != rec["amount_out"]:
            match = False
        if rec["class"] == "OVERPAID_INPUT" and got == rec["amount_out"]:
            match = False
        if not match:
            e2e_ok = False
        detail.append(f"{rec['class']} u512={got} full={ref_f} safe={ref_s} onchain={rec['amount_out']} steps={steps}")
        rows.append({"class": rec["class"], "lin": got, "ref_full": ref_f, "ref_safe": ref_s,
                     "onchain": rec["amount_out"], "status": st, "steps": steps})
        recs.append(lcr2(img_h, 3, rec.get("log_index", 1), ain, rin, rout_v, got, steps, st))
        leaves.append(lcr2_dict(rec["class"], rec.get("log_index", 1), ain, rin, rout_v,
                                got, steps, st, got, ref_f, rec["amount_out"]))

    st_ph, q_ph, s_ph = settle_u512(1, 1, rout_phantom, nwords=4)
    rst_sf, _ = ref_amount_out(1, 1, rout_phantom)
    rst_ff, ref_ff = ref_amount_out_full(1, 1, rout_phantom)
    ph_ok = st_ph == 1 and rst_sf == -2 and rst_ff == 1 and q_ph == ref_ff and s_ph != 0
    if not ph_ok:
        e2e_ok = False
    detail.append(f"PHANTOM_APPROVE u512={q_ph} full={ref_ff} safe_st={rst_sf} steps={s_ph}")
    recs.append(lcr2(img_h, 3, 0xFFFFFFFE, 1, 1, rout_phantom, q_ph, s_ph, st_ph))
    leaves.append(lcr2_dict("PHANTOM_APPROVE", 0xFFFFFFFE, 1, 1, rout_phantom,
                            q_ph, s_ph, st_ph, q_ph, ref_ff, 0))
    rows.append({"class": "PHANTOM_APPROVE", "lin": q_ph, "ref_full": ref_ff,
                 "ref_safe": rst_sf, "onchain": 0, "status": st_ph, "steps": s_ph})

    st_z, _, s_z = settle_u512(0, 1, 1, nwords=1)
    recs.append(lcr2(img_h, 3, 0, 0, 1, 1, 0, s_z, st_z))
    leaves.append(lcr2_dict("GUARD_ZERO", 0, 0, 1, 1, 0, s_z, st_z, 0, 0, 0))
    st_fee, _, s_fee = settle_u512(UMAX, 1, 1, nwords=1)
    recs.append(lcr2(img_h, 3, 0xFFFFFFFD, UMAX, 1, 1, 0, s_fee, st_fee))
    rst_fee, _ = ref_amount_out_full(UMAX, 1, 1)
    leaves.append(lcr2_dict("GUARD_FEE_OVERFLOW", 0xFFFFFFFD, UMAX, 1, 1, 0, s_fee, st_fee, 0, 0, 0))
    guards_ok = st_z == -1 and st_fee == -2 and rst_fee == -2 and s_z != 0 and s_fee != 0
    if not guards_ok:
        e2e_ok = False
    detail.append(f"guards z={st_z}/{s_z} fee={st_fee}/{s_fee}")
    root = merkle(recs, LCR_LEAF, LCR_NODE).hex()
    blob = Path("/tmp/u512_lcr2_full.bin")
    blob.write_bytes(b"".join(recs))
    return {
        "ok": e2e_ok and ph_ok and guards_ok,
        "root": root,
        "blob": blob,
        "leaves": leaves,
        "rows": rows,
        "detail": " | ".join(detail),
        "img": sha256_file(img_p) if img_p.exists() else "",
        "phantom_steps": s_ph,
        "phantom_q": q_ph,
    }
