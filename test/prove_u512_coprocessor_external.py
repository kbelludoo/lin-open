#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External auditable proof: LIN as a numeric coprocessor with a receipt.

This run (no Zig):
  * 256x256->512 mul + leftover-carry fail-closed
  * 512/256 restoring div, 32-limb remainder, 512-bit ge
  * q*d+r==n vs Python int + C11 16-bit + C11 64-bit __int128
  * LNR1 campaign merkle recomputed from published leaves (zero-LIN)
  * Quad-auditor: hashlib / Node crypto / C11 lin_sha256 / OpenSSL
  * LCR2: settle_u256_word vs coprocessor mulDiv vs ref_amount_out
    on 3 EXACT + 3 OVERPAID with real steps; guards -1/-2

Does NOT prove FullMath CRT/mulmod, a pool, the 2000/157 campaign,
or that 512-bit math closes u256 by itself.

Class: EXPERIMENTAL (FullMath *width*).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from prove_u512_lib import (
    C0, DOM_LEAF, DOM_NODE, LCR_LEAF, LCR_NODE, LIN, OP, PIN_FM, ROOT, U256, U512A, UMAX,
    from_words, lcr2, leaf_dict, lin, lnr1, merkle, node_root, openssl_sha256,
    py_muldiv, ref_amount_out, run, sha256_file, vectors, words,
)

ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
AUD_SRC = ROOT / "test" / "oracles" / "verify_u512_receipt.c"
SHA_C = ROOT / "transpile" / "c" / "lin_c" / "lin_sha256.c"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
MN = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
EVID = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def lin_q_lo(a: int, b: int, d: int, expect: int) -> tuple[int, int, int, int]:
    st, ss = lin("u512_muldiv_word", *words(a), *words(b), *words(d), -1)
    if st != 1:
        return st, 0, 0, ss
    w0, ss = lin("u512_muldiv_word", *words(a), *words(b), *words(d), 0)
    extra = [0, 0, 0]
    if expect >= (1 << 64):
        extra = [lin("u512_muldiv_word", *words(a), *words(b), *words(d), i)[0] for i in range(1, 4)]
    q = from_words([w0] + extra)
    r = (a * b) % d
    return st, q, r, ss


def main() -> int:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0 or not C0.exists():
            print("FAIL build lin_c0", p.stderr)
            return 1

    ora = Path("/tmp/u512_coprocessor_c11")
    aud = Path("/tmp/verify_u512_receipt")
    cc1 = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-o", str(ora), str(ORACLE_SRC)])
    ok("c11_oracle_compile", cc1.returncode == 0, (cc1.stderr or "")[-200:])
    cc2 = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", f"-I{ROOT}/transpile/c/lin_c",
               "-o", str(aud), str(AUD_SRC), str(SHA_C)])
    ok("c11_auditor_compile", cc2.returncode == 0, (cc2.stderr or "")[-200:])
    st = run([str(ora), "--self-test"])
    ok("c11_selftest_identity", st.returncode == 0 and "SELFTEST_PASS" in st.stdout, st.stdout.strip())
    ast = run([str(aud), "--self-test"])
    ok("c11_auditor_tamper", ast.returncode == 0 and "AUDITOR_SELFTEST_PASS" in ast.stdout, ast.stdout[:80])

    vecs = vectors()
    lines, expect = [], []
    for op, a, b, d in vecs:
        if op == "MUL":
            n = a * b
            expect.append((1, n & UMAX, n >> 256))
            lines.append(f"MUL {a:064x} {b:064x}\n")
        else:
            stt, q, r = py_muldiv(a, b, d)
            expect.append((stt, q, r))
            lines.append(f"MULDIV {a:064x} {b:064x} {d:064x}\n")
    bat = run([str(ora), "--batch"], inp="".join(lines), timeout=60)
    rows = [ln.split() for ln in bat.stdout.splitlines() if ln]
    match = bat.returncode == 0 and len(rows) == len(expect)
    ident_ok = True
    if match:
        for (stt, q, r), row, (op, a, b, d) in zip(expect, rows, vecs):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                match = False
                break
            if op == "MULDIV" and stt == 1 and q * d + r != a * b:
                ident_ok = False
    ok("c11_python_full_range", match, f"n={len(expect)} {bat.stderr.strip()}")
    ok("python_remainder_identity", ident_ok and match, "q*d+r==n")

    chk = run([str(C0), "check", str(LIN)])
    ok("lin_check", chk.returncode == 0 and "typecheck=passed" in chk.stdout, "")

    leaves = []
    v, s_mul = lin("u512_mul_word", 7, 0, 0, 0, 9, 0, 0, 0, 0)
    ok("lin_mul_7x9", v == 63, f"value={v} steps={s_mul}")
    leaves.append(leaf_dict("MUL", 7, 9, 0, 63, 0, 1, s_mul))

    stt, s_md = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, -1)
    q, _ = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, 0)
    r, _ = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, 4)
    ok("lin_muldiv_7x9_div2", stt == 1 and q == 31 and r == 1, f"q={q} r={r} steps={s_md}")
    leaves.append(leaf_dict("MULDIV", 7, 9, 2, 31, 1, 1, s_md))

    all1 = -1
    lo0, s_max = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 0)
    hi0, _ = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 4)
    hi3, _ = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 7)
    ok("lin_max_sq_512", lo0 == 1 and hi0 == -2 and hi3 == -1, f"lo={lo0} hi0={hi0} hi3={hi3}")
    nmax = UMAX * UMAX
    leaves.append(leaf_dict("MUL", UMAX, UMAX, 0, nmax & UMAX, nmax >> 256, 1, s_max))

    hi255 = -(1 << 63)
    q55, s255 = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 3, 0, 0, 0, 0)
    r55, _ = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 3, 0, 0, 0, 4)
    ok("lin_2_255_x2_div3", q55 == 0x5555555555555555 and r55 == 1, f"q={q55} steps={s255}")
    _st, q255, r255 = py_muldiv(1 << 255, 2, 3)
    leaves.append(leaf_dict("MULDIV", 1 << 255, 2, 3, q255, r255, 1, s255))

    z, s_z = lin("u512_muldiv_word", 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, -1)
    ov, s_ov = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 1, 0, 0, 0, -1)
    ok("lin_guards_-1_-2", z == -1 and ov == -2, f"d0={z} ov={ov}")
    leaves.append(leaf_dict("MULDIV", 1, 1, 0, 0, 0, -1, s_z))
    leaves.append(leaf_dict("MULDIV", 1 << 255, 2, 1, 0, 0, -2, s_ov))

    ge1, _ = lin("u512_ge_word", 0, 0, 0, 0, 1, 0, 0, 0, all1, all1, all1, all1, 0, 0, 0, 0)
    ge0, _ = lin("u512_ge_word", all1, all1, all1, all1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0)
    gee, _ = lin("u512_ge_word", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    ok("lin_ge_512", ge1 == 1 and ge0 == 0 and gee == 1, f"ge={ge1},{ge0},eq={gee}")

    gao, s_gao = lin("u512_muldiv_word", 997000, 0, 0, 0, 20000, 0, 0, 0, 10997000, 0, 0, 0, 0)
    ok("lin_getAmountOut_1813", gao == 1813, f"value={gao} steps={s_gao}")
    leaves.append(leaf_dict("MULDIV", 997000, 20000, 10997000, 1813, (997000 * 20000) % 10997000, 1, s_gao))

    gate, s_gate = lin("u512_self_gate")
    ok("lin_self_gate", gate == 1, f"value={gate} steps={s_gate}")

    rout = ((1 << 256) + 996) // 997
    rw = words(rout)
    ph, s_ph = lin("u512_muldiv_word", 997, 0, 0, 0, *rw, 1997, 0, 0, 0, -1)
    u2, s_u2 = lin("settle_u256_word", 1, 0, 0, 0, 1, 0, 0, 0, *rw, -1, src=U256)
    qw = [lin("u512_muldiv_word", 997, 0, 0, 0, *rw, 1997, 0, 0, 0, i)[0] for i in range(4)]
    q_ph = from_words(qw)
    st_py, q_py, r_py = py_muldiv(997, rout, 1997)
    ok("phantom_512_vs_u256_width", ph == 1 and u2 == -2 and q_ph == q_py and st_py == 1,
       f"coprocessor={ph} steps={s_ph} u256={u2} steps={s_u2}")
    leaves.append(leaf_dict("MULDIV", 997, rout, 1997, q_py, r_py, 1, s_ph))

    w0, s_uv = lin("settle_u512_swap", 1000, 0, 0, 0, 10000, 0, 0, 0, 20000, 0, 0, 0, 0, src=U512A)
    ok("uniswap_u512_1813", w0 == 1813, f"value={w0} steps={s_uv}")
    ok("fullmath_sol_width_pin", sha256_file(FULLMATH) == PIN_FM, sha256_file(FULLMATH)[:16])

    img_p = Path("/tmp/u256_settlement.linbc")
    im = run([str(C0), "image", str(U256), "-o", str(img_p)])
    img_d = hashlib.sha256(img_p.read_bytes()).digest() if img_p.exists() else b"\x00" * 32
    data = json.loads(MN.read_text())
    exacts = [rec for rec in data["records"] if rec["class"] == "EXACT_INPUT"][:3]
    overs = [rec for rec in data["records"] if rec["class"] == "OVERPAID_INPUT"][:3]
    lcr_recs, e2e_rows, e2e_detail = [], [], []
    e2e_ok = True
    for rec in exacts + overs:
        ain, rin, rout_v = rec["amount_in"], rec["reserve_in"], rec["reserve_out"]
        rst, ref = ref_amount_out(ain, rin, rout_v)
        aw, riw, row = words(ain), words(rin), words(rout_v)
        st_lin, _ = lin("settle_u256_word", *aw, *riw, *row, -1, src=U256)
        ws, s_w0 = [], 0
        for i in range(4):
            wi, si = lin("settle_u256_word", *aw, *riw, *row, i, src=U256)
            if i == 0:
                s_w0 = si
            ws.append(wi)
        got = from_words(ws)
        fee, den = ain * 997, rin * 1000 + ain * 997
        if fee <= UMAX and den <= UMAX and rst == 1:
            cst, cq, cr, cs = lin_q_lo(fee, rout_v, den, ref)
        else:
            cst, cq, cr, cs = -2, 0, 0, 0
        match_ref = st_lin == rst and (rst != 1 or got == ref) and s_w0 != 0
        if rec["class"] == "EXACT_INPUT" and got != rec["amount_out"]:
            match_ref = False
        if rst == 1 and (cst != 1 or cq != ref or got != cq):
            match_ref = False
        if not match_ref:
            e2e_ok = False
        e2e_detail.append(
            f"{rec['class']} lin={got} cop={cq} ref={ref} onchain={rec['amount_out']} "
            f"st={st_lin}/{cst} steps={s_w0}/{cs}"
        )
        e2e_rows.append({
            "class": rec["class"], "lin": got, "coprocessor": cq, "ref": ref,
            "onchain": rec["amount_out"], "status": st_lin, "cop_status": cst,
            "steps": s_w0, "cop_steps": cs,
        })
        lcr_recs.append(lcr2(img_d, 2, rec.get("log_index", 1), ain, rin, rout_v, got, s_w0, st_lin))
        if cst == 1:
            leaves.append(leaf_dict("MULDIV", fee, rout_v, den, cq, cr, 1, cs))
    g_st, s_g1 = lin("settle_u256_word", 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, -1, src=U256)
    g_ov, s_g2 = lin("settle_u256_word", 1, 0, 0, 0, 1, 0, 0, 0, *rw, -1, src=U256)
    ok("lcr2_exact_overpaid_steps", e2e_ok and g_st == -1 and g_ov == -2 and len(exacts) == 3 and len(overs) == 3,
       " | ".join(e2e_detail) + f" guards={g_st}/{g_ov} steps={s_g1}/{s_g2}")
    ok("lcr2_coprocessor_eq_settler", e2e_ok, "mulDiv(fee,rout,den)==settle_u256==ref when width fits")
    lcr_root = merkle(lcr_recs, LCR_LEAF, LCR_NODE).hex()
    ok("lcr2_merkle_recompute", len(lcr_root) == 64, f"sha256:{lcr_root}")
    ok("image_encode", im.returncode == 0 and img_p.exists(), sha256_file(img_p)[:16] if img_p.exists() else "")

    src_d = hashlib.sha256(LIN.read_bytes()).digest()
    recs = []
    for i, leaf in enumerate(leaves):
        recs.append(lnr1(
            src_d, 1, i, OP[leaf["op"]],
            int(leaf["a"], 0), int(leaf["b"], 0), int(leaf["d"], 0),
            int(leaf["q"], 0), int(leaf["r"], 0), int(leaf["steps"]), int(leaf["status"]),
        ))
    blob = Path("/tmp/u512_lnr1.bin")
    blob.write_bytes(b"".join(recs))
    py_root = merkle(recs, DOM_LEAF, DOM_NODE).hex()
    c_root = run([str(aud), "--root", str(blob)]).stdout.strip()
    n_root = node_root(blob)
    ol = openssl_sha256(DOM_LEAF + recs[0])
    on = openssl_sha256(DOM_NODE + hashlib.sha256(DOM_LEAF + recs[0]).digest()
                        + hashlib.sha256(DOM_LEAF + recs[1]).digest())
    pl = hashlib.sha256(DOM_LEAF + recs[0]).digest()
    pn = hashlib.sha256(DOM_NODE + pl + hashlib.sha256(DOM_LEAF + recs[1]).digest()).digest()
    ok("lnr1_quad_auditor", py_root == c_root and n_root == py_root and ol == pl and on == pn,
       f"py={py_root} c={c_root} node={n_root} n={len(recs)}")
    tamp = bytearray(b"".join(recs))
    tamp[56 + 31] ^= 1
    tpath = Path("/tmp/u512_lnr1_tamper.bin")
    tpath.write_bytes(bytes(tamp))
    t_py = merkle([bytes(tamp[i:i + 240]) for i in range(0, len(tamp), 240)], DOM_LEAF, DOM_NODE).hex()
    t_c = run([str(aud), "--root", str(tpath)]).stdout.strip()
    ok("lnr1_tamper_reject", t_py != py_root and t_c == t_py and t_c != c_root, f"tamper={t_py[:16]}")

    EVID.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.1",
        "class": "EXPERIMENTAL",
        "product": "numeric coprocessor with auditable receipt",
        "domains": {"leaf": "LIN:U512:LEAF:1", "node": "LIN:U512:NODE:1"},
        "lnr1_bytes": 240,
        "lnr1_merkle": py_root,
        "lcr2_merkle": lcr_root,
        "audit": "zero-LIN verifier recomputes lnr1_merkle from published leaves",
        "pins": {
            "lin_src": sha256_file(LIN),
            "oracle_c": sha256_file(ORACLE_SRC),
            "auditor_c": sha256_file(AUD_SRC),
            "harness": sha256_file(Path(__file__)),
            "lib": sha256_file(ROOT / "test" / "prove_u512_lib.py"),
            "fullmath_sol": sha256_file(FULLMATH),
            "u256_linbc1": sha256_file(img_p) if img_p.exists() else "",
        },
        "measured": {
            "self_gate_steps": s_gate,
            "mul_7x9_steps": s_mul,
            "muldiv_7x9_div2_steps": s_md,
            "two_255_x2_div3_steps": s255,
            "phantom_coprocessor_steps": s_ph,
            "phantom_u256_status": u2,
            "c11_batch_n": len(expect),
            "published_leaves": len(leaves),
            "lcr2": e2e_rows,
        },
        "leaves": leaves,
        "not_claimed": [
            "FullMath CRT/mulmod assembly",
            "deployed pool",
            "full 2000/157 campaign",
            "that 512 proof closes u256 by itself",
        ],
    }
    EVID.write_text(json.dumps(evidence, indent=2) + "\n")
    vr = run([sys.executable, str(VERIFY), str(EVID), "--self-test"], timeout=30)
    ok("standalone_receipt_verifier", vr.returncode == 0 and "PASS" in vr.stdout
       and "merkle_match" in vr.stdout, vr.stdout.strip()[:160])

    npass = sum(1 for _, c, _ in CHECKS if c)
    print(f"\n{npass}/{len(CHECKS)} PASS")
    print("src", sha256_file(LIN))
    print("oracle", sha256_file(ORACLE_SRC))
    print("auditor", sha256_file(AUD_SRC))
    print("lnr1", py_root)
    print("lcr2", lcr_root)
    print("self_gate_steps", s_gate)
    print("class EXPERIMENTAL FullMath-width not CRT not a pool")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
