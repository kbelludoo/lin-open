#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External auditable proof: LIN numeric coprocessor with a receipt.
No Zig. 256x256->512 mul, 512/256 div q*d+r==n, 512-bit ge.
Oracles: Python int, C11 16-bit, C11 __int128, C11 radix-2^32, rustc radix-2^64,
Python radix-2^8, Knuth Algorithm D (normalized long division), FullMath CRT +
Newton inverse, Karatsuba + Barrett, Node BigInt, OpenSSL BN, Go math/big, Java
BigInteger, GNU MP mpz, Perl Math::BigInt::Calc, POSIX GNU bc. LNR1+LCR2+LCR2-full
+LGE1+LRI1 + LIP1 inclusion (all LCR2 and LCR2-full). EXPERIMENTAL FullMath-width
algorithm off-chain, not the EVM mulmod opcode, not a pool, not the 2000/157 campaign.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from prove_u512_fullwidth import (
    NODE_ORACLE, VERIFY_JS, collect_lcr2_full, node_batch, node_selftest,
)
from prove_u512_ge import (
    BN_BIN, BN_SRC, bn_ge_batch, bn_selftest, collect_lge1, compile_bn, node_ge_batch, oracle_batch,
)
from prove_u512_gmp import gmp_check_tuples, gmp_lcr2_bind
from prove_u512_identity import collect_lri1, run_go_oracle
from prove_u512_inclusion import (
    VERIFY_INC, VERIFY_INC_JS, VERIFY_INC_PL, inclusion_auditor_tuples, java_check_tuples, make_lip1,
)
from prove_u512_lib import (
    C0, DOM_LEAF, DOM_NODE, LCR_LEAF, LCR_NODE, LIN, OP, PIN_FM, ROOT, U256, U512A, UMAX,
    from_words, lcr2, lcr2_dict, leaf_dict, lin, lnr1, merkle, node_bin, node_root,
    openssl_sha256, py_muldiv, ref_amount_out, run, sha256_file, vectors, words,
)
from prove_u512_bc import bc_check_tuples, bc_lcr2_bind, bc_lcr2_full_bind, bc_lri1_identity
from prove_u512_perl import perl_check_tuples, perl_lcr2_bind, perl_lcr2_full_bind
from prove_u512_radix32 import r32_check_tuples, r32_lcr2_bind, r32_lcr2_full_bind
from prove_u512_rust64 import (
    R64_LIMBS, R64_SRC, r64_check_tuples, r64_lcr2_bind, r64_lcr2_full_bind, r64_lri1_identity,
)
from prove_u512_radix8 import (
    r8_check_tuples, r8_lcr2_bind, r8_lcr2_full_bind, r8_lri1_identity,
)
from prove_u512_knuth_d import (
    kd_check_tuples, kd_lcr2_bind, kd_lcr2_full_bind, kd_lri1_identity,
)
from prove_u512_crt import (
    crt_check_tuples, crt_lcr2_bind, crt_lcr2_full_bind, crt_lri1_identity,
)
from prove_u512_karatsuba import (
    ks_check_tuples, ks_lcr2_bind, ks_lcr2_full_bind, ks_lri1_identity,
)

ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
AUD_SRC = ROOT / "test" / "oracles" / "verify_u512_receipt.c"
SHA_C = ROOT / "transpile" / "c" / "lin_c" / "lin_sha256.c"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
MN = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
EVID = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
VERIFY_BC = ROOT / "examples" / "u512_coprocessor" / "verify_u512_bc_identity.py"
VERIFY_R64 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_rust64.rs"
VERIFY_R8 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_radix8.py"
VERIFY_KD = ROOT / "examples" / "u512_coprocessor" / "verify_u512_knuth_d.py"
VERIFY_CRT = ROOT / "examples" / "u512_coprocessor" / "verify_u512_crt.py"
VERIFY_KS = ROOT / "examples" / "u512_coprocessor" / "verify_u512_karatsuba.py"
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
    ns_ok, ns_out = node_selftest()
    ok("node_bigint_selftest", ns_ok, ns_out)
    n_ok, n_n, n_err = node_batch("".join(lines), expect)
    ok("node_python_c11_full_range", n_ok and match, f"n={n_n} {n_err}")
    bn_cc, bn_cc_err = compile_bn()
    ok("openssl_bn_compile", bn_cc, bn_cc_err)
    bn_st, bn_st_out = bn_selftest()
    ok("openssl_bn_selftest", bn_st, bn_st_out)
    bn_ok, bn_n, bn_err = oracle_batch(BN_BIN, "".join(lines), expect)
    ok("openssl_bn_python_c11_full_range", bn_ok and match, f"n={bn_n} {bn_err}")
    go = run_go_oracle("".join(lines), expect)
    ok("go_math_big_compile", go["compile"], go["compile_err"])
    ok("go_math_big_selftest", go["selftest"], go["selftest_out"])
    ok("go_python_c11_full_range", go["batch"] and match, f"n={go['n']} {go['batch_err']}")
    ok("go_ge512", go["ge"], go["ge_err"])
    java, jrows = java_check_tuples("".join(lines), expect, match)
    for row in jrows:
        ok(*row)
    gmp, grows = gmp_check_tuples("".join(lines), expect, match)
    for row in grows:
        ok(*row)
    perl, prows = perl_check_tuples("".join(lines), expect, match)
    for row in prows:
        ok(*row)
    r32, rrows = r32_check_tuples("".join(lines), expect, match)
    for row in rrows:
        ok(*row)
    r64, r64rows = r64_check_tuples("".join(lines), expect, match)
    for row in r64rows:
        ok(*row)
    r8, r8rows = r8_check_tuples("".join(lines), expect, match)
    for row in r8rows:
        ok(*row)
    kd, kdrows = kd_check_tuples("".join(lines), expect, match)
    for row in kdrows:
        ok(*row)
    crt, crtrows = crt_check_tuples("".join(lines), expect, match)
    for row in crtrows:
        ok(*row)
    ks, ksrows = ks_check_tuples("".join(lines), expect, match)
    for row in ksrows:
        ok(*row)
    bc, brows = bc_check_tuples("".join(lines), expect, match)
    for row in brows:
        ok(*row)

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
    bn_ge_ok, bn_ge_err = bn_ge_batch()
    ok("openssl_bn_ge512", bn_ge_ok, bn_ge_err)
    node_ge_ok, node_ge_err = node_ge_batch()
    ok("node_ge512", node_ge_ok, node_ge_err)

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
    lcr_recs, e2e_rows, e2e_detail, lcr_leaves = [], [], [], []
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
        lcr_leaves.append(lcr2_dict(rec["class"], rec.get("log_index", 1), ain, rin, rout_v,
                                    got, s_w0, st_lin, cq, ref, rec["amount_out"]))
        if cst == 1:
            leaves.append(leaf_dict("MULDIV", fee, rout_v, den, cq, cr, 1, cs))
    g_st, s_g1 = lin("settle_u256_word", 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, -1, src=U256)
    g_ov, s_g2 = lin("settle_u256_word", 1, 0, 0, 0, 1, 0, 0, 0, *rw, -1, src=U256)
    lcr_recs.append(lcr2(img_d, 2, 0, 0, 1, 1, 0, s_g1, g_st))
    lcr_recs.append(lcr2(img_d, 2, 0xFFFFFFFF, 1, 1, rout, 0, s_g2, g_ov))
    rst_z, ref_z = ref_amount_out(0, 1, 1)
    rst_p, ref_p = ref_amount_out(1, 1, rout)
    lcr_leaves.append(lcr2_dict("GUARD_ZERO", 0, 0, 1, 1, 0, s_g1, g_st, 0, ref_z, 0))
    lcr_leaves.append(lcr2_dict("GUARD_OVERFLOW", 0xFFFFFFFF, 1, 1, rout, 0, s_g2, g_ov, 0, ref_p, 0))
    ok("lcr2_exact_overpaid_steps", e2e_ok and g_st == -1 and g_ov == -2 and len(exacts) == 3 and len(overs) == 3
       and rst_z == -1 and rst_p == -2,
       " | ".join(e2e_detail) + f" guards={g_st}/{g_ov} steps={s_g1}/{s_g2}")
    ok("lcr2_coprocessor_eq_settler", e2e_ok, "mulDiv(fee,rout,den)==settle_u256==ref when width fits")
    gmp_e2e, gmp_e2e_d = gmp_lcr2_bind(lcr_leaves)
    ok("gmp_lcr2_exact_overpaid", gmp_e2e, gmp_e2e_d)
    perl_e2e, perl_e2e_d = perl_lcr2_bind(lcr_leaves)
    ok("perl_lcr2_exact_overpaid", perl_e2e, perl_e2e_d)
    r32_e2e, r32_e2e_d = r32_lcr2_bind(lcr_leaves)
    ok("radix32_lcr2_exact_overpaid", r32_e2e, r32_e2e_d)
    r64_e2e, r64_e2e_d = r64_lcr2_bind(lcr_leaves)
    ok("rust64_lcr2_exact_overpaid", r64_e2e, r64_e2e_d)
    r8_e2e, r8_e2e_d = r8_lcr2_bind(lcr_leaves)
    ok("radix8_lcr2_exact_overpaid", r8_e2e, r8_e2e_d)
    kd_e2e, kd_e2e_d = kd_lcr2_bind(lcr_leaves)
    ok("knuth_d_lcr2_exact_overpaid", kd_e2e, kd_e2e_d)
    crt_e2e, crt_e2e_d = crt_lcr2_bind(lcr_leaves)
    ok("crt_lcr2_exact_overpaid", crt_e2e, crt_e2e_d)
    ks_e2e, ks_e2e_d = ks_lcr2_bind(lcr_leaves)
    ok("karatsuba_lcr2_exact_overpaid", ks_e2e, ks_e2e_d)
    bc_e2e, bc_e2e_d = bc_lcr2_bind(lcr_leaves)
    ok("posix_bc_lcr2_exact_overpaid", bc_e2e, bc_e2e_d)
    lcr_root = merkle(lcr_recs, LCR_LEAF, LCR_NODE).hex()
    lcr_blob = Path("/tmp/u512_lcr2.bin")
    lcr_blob.write_bytes(b"".join(lcr_recs))
    c_lcr = run([str(aud), "--lcr2-root", str(lcr_blob)]).stdout.strip()
    ok("lcr2_merkle_recompute", len(lcr_root) == 64 and c_lcr == lcr_root,
       f"sha256:{lcr_root} c11={c_lcr}")
    ok("image_encode", im.returncode == 0 and img_p.exists(), sha256_file(img_p)[:16] if img_p.exists() else "")

    full = collect_lcr2_full(exacts, overs, rout)
    full_blob = full["blob"]
    c_full = run([str(aud), "--lcr2-root", str(full_blob)]).stdout.strip()
    ok("lcr2_full_settle_u512", full["ok"], full["detail"])
    ok("lcr2_full_merkle_recompute", len(full["root"]) == 64 and c_full == full["root"],
       f"sha256:{full['root']} c11={c_full}")
    perl_full, perl_full_d = perl_lcr2_full_bind(full["leaves"])
    ok("perl_lcr2_full_exact_overpaid_phantom", perl_full, perl_full_d)
    r32_full, r32_full_d = r32_lcr2_full_bind(full["leaves"])
    ok("radix32_lcr2_full_exact_overpaid_phantom", r32_full, r32_full_d)
    r64_full, r64_full_d = r64_lcr2_full_bind(full["leaves"])
    ok("rust64_lcr2_full_exact_overpaid_phantom", r64_full, r64_full_d)
    r8_full, r8_full_d = r8_lcr2_full_bind(full["leaves"])
    ok("radix8_lcr2_full_exact_overpaid_phantom", r8_full, r8_full_d)
    kd_full, kd_full_d = kd_lcr2_full_bind(full["leaves"])
    ok("knuth_d_lcr2_full_exact_overpaid_phantom", kd_full, kd_full_d)
    crt_full, crt_full_d = crt_lcr2_full_bind(full["leaves"])
    ok("crt_lcr2_full_exact_overpaid_phantom", crt_full, crt_full_d)
    ks_full, ks_full_d = ks_lcr2_full_bind(full["leaves"])
    ok("karatsuba_lcr2_full_exact_overpaid_phantom", ks_full, ks_full_d)
    bc_full, bc_full_d = bc_lcr2_full_bind(full["leaves"])
    ok("posix_bc_lcr2_full_exact_overpaid_phantom", bc_full, bc_full_d)

    ge = collect_lge1()
    c_ge = run([str(aud), "--lge1-root", str(ge["blob"])]).stdout.strip()
    ok("lge1_ge_512_published", ge["ok"], ge["detail"])
    ok("lge1_merkle_recompute", len(ge["root"]) == 64 and c_ge == ge["root"],
       f"sha256:{ge['root']} c11={c_ge}")

    ri = collect_lri1(rout)
    c_ri = run([str(aud), "--lri1-root", str(ri["blob"])]).stdout.strip()
    ok("lri1_remainder_identity_published", ri["ok"], ri["detail"])
    ok("lri1_merkle_recompute", len(ri["root"]) == 64 and c_ri == ri["root"],
       f"sha256:{ri['root']} c11={c_ri}")
    bc_ri, bc_ri_d = bc_lri1_identity(ri["leaves"])
    ok("posix_bc_lri1_remainder_identity", bc_ri, bc_ri_d)
    r64_ri, r64_ri_d = r64_lri1_identity(ri["leaves"])
    ok("rust64_lri1_remainder_identity", r64_ri, r64_ri_d)
    r8_ri, r8_ri_d = r8_lri1_identity(ri["leaves"])
    ok("radix8_lri1_remainder_identity", r8_ri, r8_ri_d)
    kd_ri, kd_ri_d = kd_lri1_identity(ri["leaves"])
    ok("knuth_d_lri1_remainder_identity", kd_ri, kd_ri_d)
    crt_ri, crt_ri_d = crt_lri1_identity(ri["leaves"])
    ok("crt_lri1_remainder_identity", crt_ri, crt_ri_d)
    ks_ri, ks_ri_d = ks_lri1_identity(ri["leaves"])
    ok("karatsuba_lri1_remainder_identity", ks_ri, ks_ri_d)

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
    lip = make_lip1(recs, py_root, lcr_recs, lcr_root, full["blob"], ge["blob"], ri["blob"],
                    full["root"], ge["root"], ri["root"], aud, lcr_leaves, full["leaves"],
                    ge["leaves"], ri["leaves"], leaves)
    ok("lip1_inclusion_paths", lip["ok"], lip["detail"])
    ok("lip1_c11_phantom_receipt", lip["c11"], lip["c11_detail"])
    ok("lip1_c11_lcr2_exact_receipt", lip["c11_lcr2"], lip.get("c11_lcr2_detail", ""))
    ok("lip1_c11_lcr2_full_phantom_receipt", lip["c11_full"], lip.get("c11_full_detail", ""))

    EVID.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.14",
        "class": "EXPERIMENTAL",
        "product": "numeric coprocessor with auditable receipt",
        "domains": {"leaf": "LIN:U512:LEAF:1", "node": "LIN:U512:NODE:1"},
        "lnr1_bytes": 240,
        "lnr1_merkle": py_root,
        "lcr2_bytes": 208,
        "lcr2_run_id": 2,
        "lcr2_domains": {"leaf": "LIN:LEAF:1", "node": "LIN:NODE:1"},
        "lcr2_merkle": lcr_root,
        "lcr2_full_run_id": 3,
        "lcr2_full_merkle": full["root"],
        "lge1_bytes": 208,
        "lge1_run_id": 4,
        "lge1_domains": {"leaf": "LIN:U512:GE:LEAF:1", "node": "LIN:U512:GE:NODE:1"},
        "lge1_merkle": ge["root"],
        "lri1_bytes": 240,
        "lri1_run_id": 5,
        "lri1_domains": {"leaf": "LIN:U512:RI:LEAF:1", "node": "LIN:U512:RI:NODE:1"},
        "lri1_merkle": ri["root"],
        "lip1_proofs": lip["proofs"],
        "audit": "zero-LIN Python/Node/Perl recompute five merkles; LIP1 inclusion verifies one leaf without the campaign; packed LCR2 binds to ref_amount_out; packed LCR2-full binds to ref_amount_out_full; POSIX GNU bc checks LRI1 q*d+r==n; C11 radix-2^32, rustc radix-2^64, and Python radix-2^8 schoolbooks agree on carry; Knuth Algorithm D (normalized long division, not restoring) agrees on q*d+r==n; FullMath CRT reconstructs the 512-bit product and Newton inverse divides without restoring; Karatsuba 128-bit split reconstructs n==a*b and Barrett (mu=floor(2^512/d), q=(n*mu)>>512, 512-bit ge corrections) divides without restoring n; rustc-only auditor recomputes LRI1 Merkle + LCR2 bind; radix-2^8, Knuth-D, CRT, and Karatsuba/Barrett auditors recompute identity + OpenSSL dgst LRI1 Merkle",
        "pins": {
            "lin_src": sha256_file(LIN),
            "oracle_c": sha256_file(ORACLE_SRC),
            "oracle_js": sha256_file(NODE_ORACLE),
            "oracle_bn": sha256_file(BN_SRC),
            "oracle_go": go["src"],
            "oracle_java": java["src"],
            "oracle_gmp": gmp["src"],
            "oracle_perl": perl["src"],
            "oracle_radix32": r32["src"],
            "oracle_rust64": r64["src"],
            "oracle_rust64_limbs": r64["limbs"],
            "oracle_radix8": r8["src"],
            "oracle_knuth_d": kd["src"],
            "oracle_crt": crt["src"],
            "oracle_karatsuba": ks["src"],
            "oracle_bc": bc["src"],
            "auditor_c": sha256_file(AUD_SRC),
            "harness": sha256_file(Path(__file__)),
            "lib": sha256_file(ROOT / "test" / "prove_u512_lib.py"),
            "fullwidth": sha256_file(ROOT / "test" / "prove_u512_fullwidth.py"),
            "ge": sha256_file(ROOT / "test" / "prove_u512_ge.py"),
            "identity": sha256_file(ROOT / "test" / "prove_u512_identity.py"),
            "inclusion": sha256_file(ROOT / "test" / "prove_u512_inclusion.py"),
            "gmp_py": sha256_file(ROOT / "test" / "prove_u512_gmp.py"),
            "perl_py": sha256_file(ROOT / "test" / "prove_u512_perl.py"),
            "radix32_py": sha256_file(ROOT / "test" / "prove_u512_radix32.py"),
            "rust64_py": sha256_file(ROOT / "test" / "prove_u512_rust64.py"),
            "radix8_py": sha256_file(ROOT / "test" / "prove_u512_radix8.py"),
            "knuth_d_py": sha256_file(ROOT / "test" / "prove_u512_knuth_d.py"),
            "crt_py": sha256_file(ROOT / "test" / "prove_u512_crt.py"),
            "karatsuba_py": sha256_file(ROOT / "test" / "prove_u512_karatsuba.py"),
            "bc_py": sha256_file(ROOT / "test" / "prove_u512_bc.py"),
            "verifier_bc": sha256_file(VERIFY_BC),
            "verifier_rust64": sha256_file(VERIFY_R64),
            "verifier_radix8": sha256_file(VERIFY_R8),
            "verifier_knuth_d": sha256_file(VERIFY_KD),
            "verifier_crt": sha256_file(VERIFY_CRT),
            "verifier_karatsuba": sha256_file(VERIFY_KS),
            "fullmath_sol": sha256_file(FULLMATH),
            "u256_linbc1": sha256_file(img_p) if img_p.exists() else "",
            "u512_linbc1": full["img"],
            "verifier_js": sha256_file(VERIFY_JS),
            "verifier_inc_py": sha256_file(VERIFY_INC),
            "verifier_inc_js": sha256_file(VERIFY_INC_JS),
            "verifier_inc_pl": sha256_file(VERIFY_INC_PL),
        },
        "measured": {
            "self_gate_steps": s_gate,
            "mul_7x9_steps": s_mul,
            "muldiv_7x9_div2_steps": s_md,
            "two_255_x2_div3_steps": s255,
            "phantom_coprocessor_steps": s_ph,
            "phantom_u256_status": u2,
            "phantom_u512_swap_steps": full["phantom_steps"],
            "phantom_u512_swap_q": hex(full["phantom_q"]),
            "c11_batch_n": len(expect),
            "node_batch_n": n_n,
            "openssl_bn_batch_n": bn_n,
            "go_batch_n": go["n"],
            "java_batch_n": java["n"],
            "gmp_batch_n": gmp["n"],
            "perl_batch_n": perl["n"],
            "radix32_batch_n": r32["n"],
            "rust64_batch_n": r64["n"],
            "radix8_batch_n": r8["n"],
            "knuth_d_batch_n": kd["n"],
            "crt_batch_n": crt["n"],
            "karatsuba_batch_n": ks["n"],
            "posix_bc_batch_n": bc["n"],
            "published_leaves": len(leaves),
            "published_lcr2_leaves": len(lcr_leaves),
            "published_lcr2_full_leaves": len(full["leaves"]),
            "published_lge1_leaves": len(ge["leaves"]),
            "published_lri1_leaves": len(ri["leaves"]),
            "published_lip1_proofs": lip["n"],
            "lcr2": e2e_rows,
            "lcr2_full": full["rows"],
        },
        "leaves": leaves,
        "lcr2_leaves": lcr_leaves,
        "lcr2_full_leaves": full["leaves"],
        "lge1_leaves": ge["leaves"],
        "lri1_leaves": ri["leaves"],
        "not_claimed": [
            "EVM mulmod opcode / solc FullMath.sol on-chain",
            "deployed pool",
            "full 2000/157 campaign",
            "that 512 proof closes the SafeMath-width u256 settler by itself",
        ],
    }
    EVID.write_text(json.dumps(evidence, indent=2) + "\n")
    vr = run([sys.executable, str(VERIFY), str(EVID), "--self-test"], timeout=30)
    ok("standalone_receipt_verifier", vr.returncode == 0 and "PASS" in vr.stdout
       and "merkle_match" in vr.stdout and "lcr2_full_match" in vr.stdout
       and "lge1_match" in vr.stdout and "lri1_match" in vr.stdout, vr.stdout.strip()[:240])
    js = run([node_bin(), str(VERIFY_JS), str(EVID)], timeout=30)
    ok("standalone_node_verifier", js.returncode == 0 and "PASS" in js.stdout
       and "lcr2_full_match" in js.stdout and "lge1_match" in js.stdout
       and "lri1_match" in js.stdout, js.stdout.strip()[:240])
    for row in inclusion_auditor_tuples(EVID):
        ok(*row)
    bcv = run([sys.executable, str(VERIFY_BC), str(EVID)], timeout=30)
    ok("standalone_posix_bc_identity", bcv.returncode == 0 and "PASS" in bcv.stdout
       and "lri1_bc_identity" in bcv.stdout, bcv.stdout.strip()[:200])
    r64c = run(["rustc", "--edition", "2021", "-O", "-C", "debuginfo=0",
                "-o", "/tmp/verify_u512_rust64", str(VERIFY_R64)], timeout=90)
    ok("rust64_auditor_compile", r64c.returncode == 0, (r64c.stderr or "")[-200:])
    r64v = run(["/tmp/verify_u512_rust64", str(EVID)], timeout=30)
    ok("standalone_rust64_verifier", r64v.returncode == 0 and "PASS" in r64v.stdout
       and "lri1_match" in r64v.stdout and "lcr2_rust64_bind" in r64v.stdout
       and "lcr2_full_phantom" in r64v.stdout, r64v.stdout.strip()[:240])
    r8v = run([sys.executable, str(VERIFY_R8), str(EVID)], timeout=30)
    ok("standalone_radix8_verifier", r8v.returncode == 0 and "PASS" in r8v.stdout
       and "lri1_match" in r8v.stdout and "lcr2_radix8_bind" in r8v.stdout
       and "lcr2_full_phantom" in r8v.stdout, r8v.stdout.strip()[:240])
    kdv = run([sys.executable, str(VERIFY_KD), str(EVID)], timeout=30)
    ok("standalone_knuth_d_verifier", kdv.returncode == 0 and "PASS" in kdv.stdout
       and "lri1_match" in kdv.stdout and "lcr2_knuth_d_bind" in kdv.stdout
       and "lcr2_full_phantom" in kdv.stdout, kdv.stdout.strip()[:240])
    crtv = run([sys.executable, str(VERIFY_CRT), str(EVID)], timeout=60)
    ok("standalone_crt_verifier", crtv.returncode == 0 and "PASS" in crtv.stdout
       and "lri1_match" in crtv.stdout and "lcr2_crt_bind" in crtv.stdout
       and "lcr2_full_phantom" in crtv.stdout, crtv.stdout.strip()[:240])
    ksv = run([sys.executable, str(VERIFY_KS), str(EVID)], timeout=60)
    ok("standalone_karatsuba_verifier", ksv.returncode == 0 and "PASS" in ksv.stdout
       and "lri1_match" in ksv.stdout and "lcr2_karatsuba_bind" in ksv.stdout
       and "lcr2_full_phantom" in ksv.stdout, ksv.stdout.strip()[:240])

    npass = sum(1 for _, c, _ in CHECKS if c)
    print(f"\n{npass}/{len(CHECKS)} PASS")
    print("lnr1", py_root, "lcr2", lcr_root, "full", full["root"], "lge1", ge["root"], "lri1", ri["root"], "lip1", lip["n"])
    print("self_gate_steps", s_gate, "class EXPERIMENTAL Karatsuba+Barrett auditor not EVM mulmod not a pool")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
