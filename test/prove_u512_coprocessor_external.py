#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External auditable proof: LIN numeric coprocessor with a receipt.
No Zig. 256x256->512 mul, 512/256 div q*d+r==n, 512-bit ge.
Oracles: Python int, C11 16-bit, C11 __int128, C11 radix-2^32, rustc radix-2^64,
Python radix-2^8, Knuth Algorithm D (normalized long division), FullMath CRT +
Newton inverse, Karatsuba + Barrett, Toom-3 + Goldschmidt, NTT + SRT radix-4,
Comba + non-restoring, Toom-4 + Burnikel-Ziegler, FNT + SRT radix-8, Toom-5 + SRT radix-16, Toom-6 + SRT radix-32, Toom-7 + SRT radix-64, Toom-8 + SRT radix-128, Toom-9 + SRT radix-256, Toom-10 + SRT radix-512, RNS + Newton-Raphson, Schönhage–Strassen + SRT radix-1024, unbalanced Toom-3x7 + Barrett-768, unbalanced Toom-2x5 + SRT radix-2048, unbalanced Toom-2x7 + Barrett-1024, IEEE-754 FFT + Montgomery REDC, Solinas NTT + Granlund–Montgomery, Dekker double-double + Cook–Sieveking, IEEE-754 binary80 + Karp–Markstein, unbalanced Toom-2x9 + Svoboda–Tung, unbalanced Toom-2x11 + Barrett-1280, unbalanced Toom-2x13 + Barrett-1536, unbalanced Toom-2x15 + Barrett-1792, unbalanced Toom-2x17 + Barrett-2048, unbalanced Toom-2x19 + Barrett-2304, unbalanced Toom-2x21 + Barrett-2560, unbalanced Toom-2x23 + Barrett-2816, unbalanced Toom-2x25 + Barrett-3072, unbalanced Toom-2x27 + Barrett-3328, unbalanced Toom-2x29 + Barrett-3584, unbalanced Toom-2x31 + Barrett-3840, unbalanced Toom-2x33 + Barrett-4096, unbalanced Toom-2x35 + Barrett-4352, unbalanced Toom-2x37 + Barrett-4608, unbalanced Toom-2x39 + Barrett-4864, unbalanced Toom-2x41 + Barrett-5120, unbalanced Toom-2x43 + Barrett-5376, unbalanced Toom-2x45 + Barrett-5632, unbalanced Toom-2x47 + Barrett-5888, unbalanced Toom-2x49 + Barrett-6144, Node BigInt, OpenSSL BN, Go math/big, Java
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
from prove_u512_toom3 import (
    tg_check_tuples, tg_lcr2_bind, tg_lcr2_full_bind, tg_lri1_identity,
)
from prove_u512_ntt import (
    ntt_check_tuples, ntt_lcr2_bind, ntt_lcr2_full_bind, ntt_lri1_identity,
)
from prove_u512_comba import (
    comba_check_tuples, comba_lcr2_bind, comba_lcr2_full_bind, comba_lri1_identity,
)
from prove_u512_toom4 import (
    t4_check_tuples, t4_lcr2_bind, t4_lcr2_full_bind, t4_lri1_identity,
)
from prove_u512_fnt import (
    fnt_check_tuples, fnt_lcr2_bind, fnt_lcr2_full_bind, fnt_lri1_identity,
)
from prove_u512_toom5 import (
    t5_check_tuples, t5_lcr2_bind, t5_lcr2_full_bind, t5_lri1_identity,
)
from prove_u512_toom6 import (
    t6_check_tuples, t6_lcr2_bind, t6_lcr2_full_bind, t6_lri1_identity,
)
from prove_u512_toom7 import (
    t7_check_tuples, t7_lcr2_bind, t7_lcr2_full_bind, t7_lri1_identity,
)
from prove_u512_toom8 import (
    t8_check_tuples, t8_lcr2_bind, t8_lcr2_full_bind, t8_lri1_identity,
)
from prove_u512_toom9 import (
    t9_check_tuples, t9_lcr2_bind, t9_lcr2_full_bind, t9_lri1_identity,
)
from prove_u512_toom10 import (
    t10_check_tuples, t10_lcr2_bind, t10_lcr2_full_bind, t10_lri1_identity,
)
from prove_u512_rns import (
    rns_check_tuples, rns_lcr2_bind, rns_lcr2_full_bind, rns_lri1_identity,
)
from prove_u512_ss import (
    ss_check_tuples, ss_lcr2_bind, ss_lcr2_full_bind, ss_lri1_identity,
)
from prove_u512_toom37 import (
    t37_check_tuples, t37_lcr2_bind, t37_lcr2_full_bind, t37_lri1_identity,
)
from prove_u512_toom25 import (
    t25_check_tuples, t25_lcr2_bind, t25_lcr2_full_bind, t25_lri1_identity,
)
from prove_u512_toom27 import (
    t27_check_tuples, t27_lcr2_bind, t27_lcr2_full_bind, t27_lri1_identity,
)
from prove_u512_fft import (
    fft_check_tuples, fft_lcr2_bind, fft_lcr2_full_bind, fft_lri1_identity,
)
from prove_u512_solinas import (
    sol_check_tuples, sol_lcr2_bind, sol_lcr2_full_bind, sol_lri1_identity,
)
from prove_u512_cook import (
    cook_check_tuples, cook_lcr2_bind, cook_lcr2_full_bind, cook_lri1_identity,
)
from prove_u512_km import (
    km_check_tuples, km_lcr2_bind, km_lcr2_full_bind, km_lri1_identity,
)
from prove_u512_st import (
    st_check_tuples, st_lcr2_bind, st_lcr2_full_bind, st_lri1_identity,
)
from prove_u512_toom211 import (
    t211_check_tuples, t211_lcr2_bind, t211_lcr2_full_bind, t211_lri1_identity,
)
from prove_u512_toom213 import (
    t213_check_tuples, t213_lcr2_bind, t213_lcr2_full_bind, t213_lri1_identity,
)
from prove_u512_toom215 import (
    t215_check_tuples, t215_lcr2_bind, t215_lcr2_full_bind, t215_lri1_identity,
)
from prove_u512_toom217 import (
    t217_check_tuples, t217_lcr2_bind, t217_lcr2_full_bind, t217_lri1_identity,
)
from prove_u512_toom219 import (
    t219_check_tuples, t219_lcr2_bind, t219_lcr2_full_bind, t219_lri1_identity,
)
from prove_u512_toom221 import (
    t221_check_tuples, t221_lcr2_bind, t221_lcr2_full_bind, t221_lri1_identity,
)
from prove_u512_toom223 import (
    t223_check_tuples, t223_lcr2_bind, t223_lcr2_full_bind, t223_lri1_identity,
)
from prove_u512_toom225 import (
    t225_check_tuples, t225_lcr2_bind, t225_lcr2_full_bind, t225_lri1_identity,
)
from prove_u512_toom227 import (
    t227_check_tuples, t227_lcr2_bind, t227_lcr2_full_bind, t227_lri1_identity,
)
from prove_u512_toom229 import (
    t229_check_tuples, t229_lcr2_bind, t229_lcr2_full_bind, t229_lri1_identity,
)
from prove_u512_toom231 import (
    t231_check_tuples, t231_lcr2_bind, t231_lcr2_full_bind, t231_lri1_identity,
)
from prove_u512_toom233 import (
    t233_check_tuples, t233_lcr2_bind, t233_lcr2_full_bind, t233_lri1_identity,
)
from prove_u512_toom235 import (
    t235_check_tuples, t235_lcr2_bind, t235_lcr2_full_bind, t235_lri1_identity,
)
from prove_u512_toom237 import (
    t237_check_tuples, t237_lcr2_bind, t237_lcr2_full_bind, t237_lri1_identity,
)
from prove_u512_toom239 import (
    t239_check_tuples, t239_lcr2_bind, t239_lcr2_full_bind, t239_lri1_identity,
)
from prove_u512_toom241 import (
    t241_check_tuples, t241_lcr2_bind, t241_lcr2_full_bind, t241_lri1_identity,
)
from prove_u512_toom243 import (
    t243_check_tuples, t243_lcr2_bind, t243_lcr2_full_bind, t243_lri1_identity,
)
from prove_u512_toom245 import (
    t245_check_tuples, t245_lcr2_bind, t245_lcr2_full_bind, t245_lri1_identity,
)
from prove_u512_toom247 import (
    t247_check_tuples, t247_lcr2_bind, t247_lcr2_full_bind, t247_lri1_identity,
)
from prove_u512_toom249 import (
    t249_check_tuples, t249_lcr2_bind, t249_lcr2_full_bind, t249_lri1_identity,
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
VERIFY_TG = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom3.py"
VERIFY_NTT = ROOT / "examples" / "u512_coprocessor" / "verify_u512_ntt.py"
VERIFY_COMBA = ROOT / "examples" / "u512_coprocessor" / "verify_u512_comba.py"
VERIFY_T4 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom4.py"
VERIFY_FNT = ROOT / "examples" / "u512_coprocessor" / "verify_u512_fnt.py"
VERIFY_T5 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom5.py"
VERIFY_T6 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom6.py"
VERIFY_T7 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom7.py"
VERIFY_T8 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom8.py"
VERIFY_T9 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom9.py"
VERIFY_T10 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom10.py"
VERIFY_RNS = ROOT / "examples" / "u512_coprocessor" / "verify_u512_rns.py"
VERIFY_SS = ROOT / "examples" / "u512_coprocessor" / "verify_u512_ss.py"
VERIFY_T37 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom37.py"
VERIFY_T25 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom25.py"
VERIFY_T27 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom27.py"
VERIFY_FFT = ROOT / "examples" / "u512_coprocessor" / "verify_u512_fft.py"
VERIFY_SOL = ROOT / "examples" / "u512_coprocessor" / "verify_u512_solinas.py"
VERIFY_COOK = ROOT / "examples" / "u512_coprocessor" / "verify_u512_cook.py"
VERIFY_KM = ROOT / "examples" / "u512_coprocessor" / "verify_u512_km.py"
VERIFY_ST = ROOT / "examples" / "u512_coprocessor" / "verify_u512_st.py"
VERIFY_T211 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom211.py"
VERIFY_T213 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom213.py"
VERIFY_T215 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom215.py"
VERIFY_T217 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom217.py"
VERIFY_T219 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom219.py"
VERIFY_T221 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom221.py"
VERIFY_T223 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom223.py"
VERIFY_T225 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom225.py"
VERIFY_T227 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom227.py"
VERIFY_T229 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom229.py"
VERIFY_T231 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom231.py"
VERIFY_T233 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom233.py"
VERIFY_T235 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom235.py"
VERIFY_T237 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom237.py"
VERIFY_T239 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom239.py"
VERIFY_T241 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom241.py"
VERIFY_T243 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom243.py"
VERIFY_T245 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom245.py"
VERIFY_T247 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom247.py"
VERIFY_T249 = ROOT / "examples" / "u512_coprocessor" / "verify_u512_toom249.py"
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
    tg, trows = tg_check_tuples("".join(lines), expect, match)
    for row in trows:
        ok(*row)
    ntt, ntrows = ntt_check_tuples("".join(lines), expect, match)
    for row in ntrows:
        ok(*row)
    comba, crows = comba_check_tuples("".join(lines), expect, match)
    for row in crows:
        ok(*row)
    t4, t4rows = t4_check_tuples("".join(lines), expect, match)
    for row in t4rows:
        ok(*row)
    fnt, fntrows = fnt_check_tuples("".join(lines), expect, match)
    for row in fntrows:
        ok(*row)
    t5, t5rows = t5_check_tuples("".join(lines), expect, match)
    for row in t5rows:
        ok(*row)
    t6, t6rows = t6_check_tuples("".join(lines), expect, match)
    for row in t6rows:
        ok(*row)
    t7, t7rows = t7_check_tuples("".join(lines), expect, match)
    for row in t7rows:
        ok(*row)
    t8, t8rows = t8_check_tuples("".join(lines), expect, match)
    for row in t8rows:
        ok(*row)
    t9, t9rows = t9_check_tuples("".join(lines), expect, match)
    for row in t9rows:
        ok(*row)
    t10, t10rows = t10_check_tuples("".join(lines), expect, match)
    for row in t10rows:
        ok(*row)
    rns, rnsrows = rns_check_tuples("".join(lines), expect, match)
    for row in rnsrows:
        ok(*row)
    ss, ssrows = ss_check_tuples("".join(lines), expect, match)
    for row in ssrows:
        ok(*row)
    t37, t37rows = t37_check_tuples("".join(lines), expect, match)
    for row in t37rows:
        ok(*row)
    t25, t25rows = t25_check_tuples("".join(lines), expect, match)
    for row in t25rows:
        ok(*row)
    t27, t27rows = t27_check_tuples("".join(lines), expect, match)
    for row in t27rows:
        ok(*row)
    fft, fftrows = fft_check_tuples("".join(lines), expect, match)
    for row in fftrows:
        ok(*row)
    sol, solrows = sol_check_tuples("".join(lines), expect, match)
    for row in solrows:
        ok(*row)
    cook, cookrows = cook_check_tuples("".join(lines), expect, match)
    for row in cookrows:
        ok(*row)
    km, kmrows = km_check_tuples("".join(lines), expect, match)
    for row in kmrows:
        ok(*row)
    stw, strows = st_check_tuples("".join(lines), expect, match)
    for row in strows:
        ok(*row)
    t211, t211rows = t211_check_tuples("".join(lines), expect, match)
    for row in t211rows:
        ok(*row)
    t213, t213rows = t213_check_tuples("".join(lines), expect, match)
    for row in t213rows:
        ok(*row)
    t215, t215rows = t215_check_tuples("".join(lines), expect, match)
    for row in t215rows:
        ok(*row)
    t217, t217rows = t217_check_tuples("".join(lines), expect, match)
    for row in t217rows:
        ok(*row)
    t219, t219rows = t219_check_tuples("".join(lines), expect, match)
    for row in t219rows:
        ok(*row)
    t221, t221rows = t221_check_tuples("".join(lines), expect, match)
    for row in t221rows:
        ok(*row)
    t223, t223rows = t223_check_tuples("".join(lines), expect, match)
    for row in t223rows:
        ok(*row)
    t225, t225rows = t225_check_tuples("".join(lines), expect, match)
    for row in t225rows:
        ok(*row)
    t227, t227rows = t227_check_tuples("".join(lines), expect, match)
    for row in t227rows:
        ok(*row)
    t229, t229rows = t229_check_tuples("".join(lines), expect, match)
    for row in t229rows:
        ok(*row)
    t231, t231rows = t231_check_tuples("".join(lines), expect, match)
    for row in t231rows:
        ok(*row)
    t233, t233rows = t233_check_tuples("".join(lines), expect, match)
    for row in t233rows:
        ok(*row)
    t235, t235rows = t235_check_tuples("".join(lines), expect, match)
    for row in t235rows:
        ok(*row)
    t237, t237rows = t237_check_tuples("".join(lines), expect, match)
    for row in t237rows:
        ok(*row)
    t239, t239rows = t239_check_tuples("".join(lines), expect, match)
    for row in t239rows:
        ok(*row)
    t241, t241rows = t241_check_tuples("".join(lines), expect, match)
    for row in t241rows:
        ok(*row)
    t243, t243rows = t243_check_tuples("".join(lines), expect, match)
    for row in t243rows:
        ok(*row)
    t245, t245rows = t245_check_tuples("".join(lines), expect, match)
    for row in t245rows:
        ok(*row)
    t247, t247rows = t247_check_tuples("".join(lines), expect, match)
    for row in t247rows:
        ok(*row)
    t249, t249rows = t249_check_tuples("".join(lines), expect, match)
    for row in t249rows:
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
    tg_e2e, tg_e2e_d = tg_lcr2_bind(lcr_leaves)
    ok("toom3_lcr2_exact_overpaid", tg_e2e, tg_e2e_d)
    ntt_e2e, ntt_e2e_d = ntt_lcr2_bind(lcr_leaves)
    ok("ntt_lcr2_exact_overpaid", ntt_e2e, ntt_e2e_d)
    comba_e2e, comba_e2e_d = comba_lcr2_bind(lcr_leaves)
    ok("comba_lcr2_exact_overpaid", comba_e2e, comba_e2e_d)
    t4_e2e, t4_e2e_d = t4_lcr2_bind(lcr_leaves)
    ok("toom4_lcr2_exact_overpaid", t4_e2e, t4_e2e_d)
    fnt_e2e, fnt_e2e_d = fnt_lcr2_bind(lcr_leaves)
    ok("fnt_lcr2_exact_overpaid", fnt_e2e, fnt_e2e_d)
    t5_e2e, t5_e2e_d = t5_lcr2_bind(lcr_leaves)
    ok("toom5_lcr2_exact_overpaid", t5_e2e, t5_e2e_d)
    t6_e2e, t6_e2e_d = t6_lcr2_bind(lcr_leaves)
    ok("toom6_lcr2_exact_overpaid", t6_e2e, t6_e2e_d)
    t7_e2e, t7_e2e_d = t7_lcr2_bind(lcr_leaves)
    ok("toom7_lcr2_exact_overpaid", t7_e2e, t7_e2e_d)
    t8_e2e, t8_e2e_d = t8_lcr2_bind(lcr_leaves)
    ok("toom8_lcr2_exact_overpaid", t8_e2e, t8_e2e_d)
    t9_e2e, t9_e2e_d = t9_lcr2_bind(lcr_leaves)
    ok("toom9_lcr2_exact_overpaid", t9_e2e, t9_e2e_d)
    t10_e2e, t10_e2e_d = t10_lcr2_bind(lcr_leaves)
    ok("toom10_lcr2_exact_overpaid", t10_e2e, t10_e2e_d)
    rns_e2e, rns_e2e_d = rns_lcr2_bind(lcr_leaves)
    ok("rns_lcr2_exact_overpaid", rns_e2e, rns_e2e_d)
    ss_e2e, ss_e2e_d = ss_lcr2_bind(lcr_leaves)
    ok("ss_lcr2_exact_overpaid", ss_e2e, ss_e2e_d)
    t37_e2e, t37_e2e_d = t37_lcr2_bind(lcr_leaves)
    ok("toom37_lcr2_exact_overpaid", t37_e2e, t37_e2e_d)
    t25_e2e, t25_e2e_d = t25_lcr2_bind(lcr_leaves)
    ok("toom25_lcr2_exact_overpaid", t25_e2e, t25_e2e_d)
    t27_e2e, t27_e2e_d = t27_lcr2_bind(lcr_leaves)
    ok("toom27_lcr2_exact_overpaid", t27_e2e, t27_e2e_d)
    fft_e2e, fft_e2e_d = fft_lcr2_bind(lcr_leaves)
    ok("fft_lcr2_exact_overpaid", fft_e2e, fft_e2e_d)
    sol_e2e, sol_e2e_d = sol_lcr2_bind(lcr_leaves)
    ok("solinas_lcr2_exact_overpaid", sol_e2e, sol_e2e_d)
    cook_e2e, cook_e2e_d = cook_lcr2_bind(lcr_leaves)
    ok("cook_lcr2_exact_overpaid", cook_e2e, cook_e2e_d)
    km_e2e, km_e2e_d = km_lcr2_bind(lcr_leaves)
    ok("km_lcr2_exact_overpaid", km_e2e, km_e2e_d)
    st_e2e, st_e2e_d = st_lcr2_bind(lcr_leaves)
    ok("toom29_lcr2_exact_overpaid", st_e2e, st_e2e_d)
    t211_e2e, t211_e2e_d = t211_lcr2_bind(lcr_leaves)
    ok("toom211_lcr2_exact_overpaid", t211_e2e, t211_e2e_d)
    t213_e2e, t213_e2e_d = t213_lcr2_bind(lcr_leaves)
    ok("toom213_lcr2_exact_overpaid", t213_e2e, t213_e2e_d)
    t215_e2e, t215_e2e_d = t215_lcr2_bind(lcr_leaves)
    ok("toom215_lcr2_exact_overpaid", t215_e2e, t215_e2e_d)
    t217_e2e, t217_e2e_d = t217_lcr2_bind(lcr_leaves)
    ok("toom217_lcr2_exact_overpaid", t217_e2e, t217_e2e_d)
    t219_e2e, t219_e2e_d = t219_lcr2_bind(lcr_leaves)
    ok("toom219_lcr2_exact_overpaid", t219_e2e, t219_e2e_d)
    t221_e2e, t221_e2e_d = t221_lcr2_bind(lcr_leaves)
    ok("toom221_lcr2_exact_overpaid", t221_e2e, t221_e2e_d)
    t223_e2e, t223_e2e_d = t223_lcr2_bind(lcr_leaves)
    ok("toom223_lcr2_exact_overpaid", t223_e2e, t223_e2e_d)
    t225_e2e, t225_e2e_d = t225_lcr2_bind(lcr_leaves)
    ok("toom225_lcr2_exact_overpaid", t225_e2e, t225_e2e_d)
    t227_e2e, t227_e2e_d = t227_lcr2_bind(lcr_leaves)
    ok("toom227_lcr2_exact_overpaid", t227_e2e, t227_e2e_d)
    t229_e2e, t229_e2e_d = t229_lcr2_bind(lcr_leaves)
    ok("toom229_lcr2_exact_overpaid", t229_e2e, t229_e2e_d)
    t231_e2e, t231_e2e_d = t231_lcr2_bind(lcr_leaves)
    ok("toom231_lcr2_exact_overpaid", t231_e2e, t231_e2e_d)
    t233_e2e, t233_e2e_d = t233_lcr2_bind(lcr_leaves)
    ok("toom233_lcr2_exact_overpaid", t233_e2e, t233_e2e_d)
    t235_e2e, t235_e2e_d = t235_lcr2_bind(lcr_leaves)
    ok("toom235_lcr2_exact_overpaid", t235_e2e, t235_e2e_d)
    t237_e2e, t237_e2e_d = t237_lcr2_bind(lcr_leaves)
    ok("toom237_lcr2_exact_overpaid", t237_e2e, t237_e2e_d)
    t239_e2e, t239_e2e_d = t239_lcr2_bind(lcr_leaves)
    ok("toom239_lcr2_exact_overpaid", t239_e2e, t239_e2e_d)
    t241_e2e, t241_e2e_d = t241_lcr2_bind(lcr_leaves)
    ok("toom241_lcr2_exact_overpaid", t241_e2e, t241_e2e_d)
    t243_e2e, t243_e2e_d = t243_lcr2_bind(lcr_leaves)
    ok("toom243_lcr2_exact_overpaid", t243_e2e, t243_e2e_d)
    t245_e2e, t245_e2e_d = t245_lcr2_bind(lcr_leaves)
    ok("toom245_lcr2_exact_overpaid", t245_e2e, t245_e2e_d)
    t247_e2e, t247_e2e_d = t247_lcr2_bind(lcr_leaves)
    ok("toom247_lcr2_exact_overpaid", t247_e2e, t247_e2e_d)
    t249_e2e, t249_e2e_d = t249_lcr2_bind(lcr_leaves)
    ok("toom249_lcr2_exact_overpaid", t249_e2e, t249_e2e_d)
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
    tg_full, tg_full_d = tg_lcr2_full_bind(full["leaves"])
    ok("toom3_lcr2_full_exact_overpaid_phantom", tg_full, tg_full_d)
    ntt_full, ntt_full_d = ntt_lcr2_full_bind(full["leaves"])
    ok("ntt_lcr2_full_exact_overpaid_phantom", ntt_full, ntt_full_d)
    comba_full, comba_full_d = comba_lcr2_full_bind(full["leaves"])
    ok("comba_lcr2_full_exact_overpaid_phantom", comba_full, comba_full_d)
    t4_full, t4_full_d = t4_lcr2_full_bind(full["leaves"])
    ok("toom4_lcr2_full_exact_overpaid_phantom", t4_full, t4_full_d)
    fnt_full, fnt_full_d = fnt_lcr2_full_bind(full["leaves"])
    ok("fnt_lcr2_full_exact_overpaid_phantom", fnt_full, fnt_full_d)
    t5_full, t5_full_d = t5_lcr2_full_bind(full["leaves"])
    ok("toom5_lcr2_full_exact_overpaid_phantom", t5_full, t5_full_d)
    t6_full, t6_full_d = t6_lcr2_full_bind(full["leaves"])
    ok("toom6_lcr2_full_exact_overpaid_phantom", t6_full, t6_full_d)
    t7_full, t7_full_d = t7_lcr2_full_bind(full["leaves"])
    ok("toom7_lcr2_full_exact_overpaid_phantom", t7_full, t7_full_d)
    t8_full, t8_full_d = t8_lcr2_full_bind(full["leaves"])
    ok("toom8_lcr2_full_exact_overpaid_phantom", t8_full, t8_full_d)
    t9_full, t9_full_d = t9_lcr2_full_bind(full["leaves"])
    ok("toom9_lcr2_full_exact_overpaid_phantom", t9_full, t9_full_d)
    t10_full, t10_full_d = t10_lcr2_full_bind(full["leaves"])
    ok("toom10_lcr2_full_exact_overpaid_phantom", t10_full, t10_full_d)
    rns_full, rns_full_d = rns_lcr2_full_bind(full["leaves"])
    ok("rns_lcr2_full_exact_overpaid_phantom", rns_full, rns_full_d)
    ss_full, ss_full_d = ss_lcr2_full_bind(full["leaves"])
    ok("ss_lcr2_full_exact_overpaid_phantom", ss_full, ss_full_d)
    t37_full, t37_full_d = t37_lcr2_full_bind(full["leaves"])
    ok("toom37_lcr2_full_exact_overpaid_phantom", t37_full, t37_full_d)
    t25_full, t25_full_d = t25_lcr2_full_bind(full["leaves"])
    ok("toom25_lcr2_full_exact_overpaid_phantom", t25_full, t25_full_d)
    t27_full, t27_full_d = t27_lcr2_full_bind(full["leaves"])
    ok("toom27_lcr2_full_exact_overpaid_phantom", t27_full, t27_full_d)
    fft_full, fft_full_d = fft_lcr2_full_bind(full["leaves"])
    ok("fft_lcr2_full_exact_overpaid_phantom", fft_full, fft_full_d)
    sol_full, sol_full_d = sol_lcr2_full_bind(full["leaves"])
    ok("solinas_lcr2_full_exact_overpaid_phantom", sol_full, sol_full_d)
    cook_full, cook_full_d = cook_lcr2_full_bind(full["leaves"])
    ok("cook_lcr2_full_exact_overpaid_phantom", cook_full, cook_full_d)
    km_full, km_full_d = km_lcr2_full_bind(full["leaves"])
    ok("km_lcr2_full_exact_overpaid_phantom", km_full, km_full_d)
    st_full, st_full_d = st_lcr2_full_bind(full["leaves"])
    ok("toom29_lcr2_full_exact_overpaid_phantom", st_full, st_full_d)
    t211_full, t211_full_d = t211_lcr2_full_bind(full["leaves"])
    ok("toom211_lcr2_full_exact_overpaid_phantom", t211_full, t211_full_d)
    t213_full, t213_full_d = t213_lcr2_full_bind(full["leaves"])
    ok("toom213_lcr2_full_exact_overpaid_phantom", t213_full, t213_full_d)
    t215_full, t215_full_d = t215_lcr2_full_bind(full["leaves"])
    ok("toom215_lcr2_full_exact_overpaid_phantom", t215_full, t215_full_d)
    t217_full, t217_full_d = t217_lcr2_full_bind(full["leaves"])
    ok("toom217_lcr2_full_exact_overpaid_phantom", t217_full, t217_full_d)
    t219_full, t219_full_d = t219_lcr2_full_bind(full["leaves"])
    ok("toom219_lcr2_full_exact_overpaid_phantom", t219_full, t219_full_d)
    t221_full, t221_full_d = t221_lcr2_full_bind(full["leaves"])
    ok("toom221_lcr2_full_exact_overpaid_phantom", t221_full, t221_full_d)
    t223_full, t223_full_d = t223_lcr2_full_bind(full["leaves"])
    ok("toom223_lcr2_full_exact_overpaid_phantom", t223_full, t223_full_d)
    t225_full, t225_full_d = t225_lcr2_full_bind(full["leaves"])
    ok("toom225_lcr2_full_exact_overpaid_phantom", t225_full, t225_full_d)
    t227_full, t227_full_d = t227_lcr2_full_bind(full["leaves"])
    ok("toom227_lcr2_full_exact_overpaid_phantom", t227_full, t227_full_d)
    t229_full, t229_full_d = t229_lcr2_full_bind(full["leaves"])
    ok("toom229_lcr2_full_exact_overpaid_phantom", t229_full, t229_full_d)
    t231_full, t231_full_d = t231_lcr2_full_bind(full["leaves"])
    ok("toom231_lcr2_full_exact_overpaid_phantom", t231_full, t231_full_d)
    t233_full, t233_full_d = t233_lcr2_full_bind(full["leaves"])
    ok("toom233_lcr2_full_exact_overpaid_phantom", t233_full, t233_full_d)
    t235_full, t235_full_d = t235_lcr2_full_bind(full["leaves"])
    ok("toom235_lcr2_full_exact_overpaid_phantom", t235_full, t235_full_d)
    t237_full, t237_full_d = t237_lcr2_full_bind(full["leaves"])
    ok("toom237_lcr2_full_exact_overpaid_phantom", t237_full, t237_full_d)
    t239_full, t239_full_d = t239_lcr2_full_bind(full["leaves"])
    ok("toom239_lcr2_full_exact_overpaid_phantom", t239_full, t239_full_d)
    t241_full, t241_full_d = t241_lcr2_full_bind(full["leaves"])
    ok("toom241_lcr2_full_exact_overpaid_phantom", t241_full, t241_full_d)
    t243_full, t243_full_d = t243_lcr2_full_bind(full["leaves"])
    ok("toom243_lcr2_full_exact_overpaid_phantom", t243_full, t243_full_d)
    t245_full, t245_full_d = t245_lcr2_full_bind(full["leaves"])
    ok("toom245_lcr2_full_exact_overpaid_phantom", t245_full, t245_full_d)
    t247_full, t247_full_d = t247_lcr2_full_bind(full["leaves"])
    ok("toom247_lcr2_full_exact_overpaid_phantom", t247_full, t247_full_d)
    t249_full, t249_full_d = t249_lcr2_full_bind(full["leaves"])
    ok("toom249_lcr2_full_exact_overpaid_phantom", t249_full, t249_full_d)
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
    tg_ri, tg_ri_d = tg_lri1_identity(ri["leaves"])
    ok("toom3_lri1_remainder_identity", tg_ri, tg_ri_d)
    ntt_ri, ntt_ri_d = ntt_lri1_identity(ri["leaves"])
    ok("ntt_lri1_remainder_identity", ntt_ri, ntt_ri_d)
    comba_ri, comba_ri_d = comba_lri1_identity(ri["leaves"])
    ok("comba_lri1_remainder_identity", comba_ri, comba_ri_d)
    t4_ri, t4_ri_d = t4_lri1_identity(ri["leaves"])
    ok("toom4_lri1_remainder_identity", t4_ri, t4_ri_d)
    fnt_ri, fnt_ri_d = fnt_lri1_identity(ri["leaves"])
    ok("fnt_lri1_remainder_identity", fnt_ri, fnt_ri_d)
    t5_ri, t5_ri_d = t5_lri1_identity(ri["leaves"])
    ok("toom5_lri1_remainder_identity", t5_ri, t5_ri_d)
    t6_ri, t6_ri_d = t6_lri1_identity(ri["leaves"])
    ok("toom6_lri1_remainder_identity", t6_ri, t6_ri_d)
    t7_ri, t7_ri_d = t7_lri1_identity(ri["leaves"])
    ok("toom7_lri1_remainder_identity", t7_ri, t7_ri_d)
    t8_ri, t8_ri_d = t8_lri1_identity(ri["leaves"])
    ok("toom8_lri1_remainder_identity", t8_ri, t8_ri_d)
    t9_ri, t9_ri_d = t9_lri1_identity(ri["leaves"])
    ok("toom9_lri1_remainder_identity", t9_ri, t9_ri_d)
    t10_ri, t10_ri_d = t10_lri1_identity(ri["leaves"])
    ok("toom10_lri1_remainder_identity", t10_ri, t10_ri_d)
    rns_ri, rns_ri_d = rns_lri1_identity(ri["leaves"])
    ok("rns_lri1_remainder_identity", rns_ri, rns_ri_d)
    ss_ri, ss_ri_d = ss_lri1_identity(ri["leaves"])
    ok("ss_lri1_remainder_identity", ss_ri, ss_ri_d)
    t37_ri, t37_ri_d = t37_lri1_identity(ri["leaves"])
    ok("toom37_lri1_remainder_identity", t37_ri, t37_ri_d)
    t25_ri, t25_ri_d = t25_lri1_identity(ri["leaves"])
    ok("toom25_lri1_remainder_identity", t25_ri, t25_ri_d)
    t27_ri, t27_ri_d = t27_lri1_identity(ri["leaves"])
    ok("toom27_lri1_remainder_identity", t27_ri, t27_ri_d)
    fft_ri, fft_ri_d = fft_lri1_identity(ri["leaves"])
    ok("fft_lri1_remainder_identity", fft_ri, fft_ri_d)
    sol_ri, sol_ri_d = sol_lri1_identity(ri["leaves"])
    ok("solinas_lri1_remainder_identity", sol_ri, sol_ri_d)
    cook_ri, cook_ri_d = cook_lri1_identity(ri["leaves"])
    ok("cook_lri1_remainder_identity", cook_ri, cook_ri_d)
    km_ri, km_ri_d = km_lri1_identity(ri["leaves"])
    ok("km_lri1_remainder_identity", km_ri, km_ri_d)
    st_ri, st_ri_d = st_lri1_identity(ri["leaves"])
    ok("toom29_lri1_remainder_identity", st_ri, st_ri_d)
    t211_ri, t211_ri_d = t211_lri1_identity(ri["leaves"])
    ok("toom211_lri1_remainder_identity", t211_ri, t211_ri_d)
    t213_ri, t213_ri_d = t213_lri1_identity(ri["leaves"])
    ok("toom213_lri1_remainder_identity", t213_ri, t213_ri_d)
    t215_ri, t215_ri_d = t215_lri1_identity(ri["leaves"])
    ok("toom215_lri1_remainder_identity", t215_ri, t215_ri_d)
    t217_ri, t217_ri_d = t217_lri1_identity(ri["leaves"])
    ok("toom217_lri1_remainder_identity", t217_ri, t217_ri_d)
    t219_ri, t219_ri_d = t219_lri1_identity(ri["leaves"])
    ok("toom219_lri1_remainder_identity", t219_ri, t219_ri_d)
    t221_ri, t221_ri_d = t221_lri1_identity(ri["leaves"])
    ok("toom221_lri1_remainder_identity", t221_ri, t221_ri_d)
    t223_ri, t223_ri_d = t223_lri1_identity(ri["leaves"])
    ok("toom223_lri1_remainder_identity", t223_ri, t223_ri_d)
    t225_ri, t225_ri_d = t225_lri1_identity(ri["leaves"])
    ok("toom225_lri1_remainder_identity", t225_ri, t225_ri_d)
    t227_ri, t227_ri_d = t227_lri1_identity(ri["leaves"])
    ok("toom227_lri1_remainder_identity", t227_ri, t227_ri_d)
    t229_ri, t229_ri_d = t229_lri1_identity(ri["leaves"])
    ok("toom229_lri1_remainder_identity", t229_ri, t229_ri_d)
    t231_ri, t231_ri_d = t231_lri1_identity(ri["leaves"])
    ok("toom231_lri1_remainder_identity", t231_ri, t231_ri_d)
    t233_ri, t233_ri_d = t233_lri1_identity(ri["leaves"])
    ok("toom233_lri1_remainder_identity", t233_ri, t233_ri_d)
    t235_ri, t235_ri_d = t235_lri1_identity(ri["leaves"])
    ok("toom235_lri1_remainder_identity", t235_ri, t235_ri_d)
    t237_ri, t237_ri_d = t237_lri1_identity(ri["leaves"])
    ok("toom237_lri1_remainder_identity", t237_ri, t237_ri_d)
    t239_ri, t239_ri_d = t239_lri1_identity(ri["leaves"])
    ok("toom239_lri1_remainder_identity", t239_ri, t239_ri_d)
    t241_ri, t241_ri_d = t241_lri1_identity(ri["leaves"])
    ok("toom241_lri1_remainder_identity", t241_ri, t241_ri_d)
    t243_ri, t243_ri_d = t243_lri1_identity(ri["leaves"])
    ok("toom243_lri1_remainder_identity", t243_ri, t243_ri_d)
    t245_ri, t245_ri_d = t245_lri1_identity(ri["leaves"])
    ok("toom245_lri1_remainder_identity", t245_ri, t245_ri_d)
    t247_ri, t247_ri_d = t247_lri1_identity(ri["leaves"])
    ok("toom247_lri1_remainder_identity", t247_ri, t247_ri_d)
    t249_ri, t249_ri_d = t249_lri1_identity(ri["leaves"])
    ok("toom249_lri1_remainder_identity", t249_ri, t249_ri_d)

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
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.55",
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
        "audit": "zero-LIN Python/Node/Perl recompute five merkles; LIP1 inclusion verifies one leaf without the campaign; packed LCR2 binds to ref_amount_out; packed LCR2-full binds to ref_amount_out_full; POSIX GNU bc checks LRI1 q*d+r==n; C11 radix-2^32, rustc radix-2^64, and Python radix-2^8 schoolbooks agree on carry; Knuth Algorithm D (normalized long division, not restoring) agrees on q*d+r==n; FullMath CRT reconstructs the 512-bit product and Newton inverse divides without restoring; Karatsuba 128-bit split reconstructs n==a*b and Barrett (mu=floor(2^512/d), q=(n*mu)>>512, 512-bit ge corrections) divides without restoring n; Toom-3 86-bit 3-way split reconstructs n==a*b and Goldschmidt (F=2^257-Y, eight iterations, 512-bit ge corrections) divides without restoring n; NTT (base-256, length-64, p=998244353) reconstructs n==a*b and SRT radix-4 (digits {-2..2}, thresholds ±D/2 ±3D/2, 512-bit ge) divides without restoring n; Comba column mul reconstructs n==a*b and non-restoring 512/256 (signed remainder, one final restore, 512-bit ge) divides without restoring of n; Toom-4 64-bit 4-way split reconstructs n==a*b and Burnikel-Ziegler recursive D2n/1n (8xu64/4xu64, D3n/2n high-half, at most two add-backs, 512-bit ge) divides without restoring of n; FNT (base-2^16, length-32, ring 2^64+1, ω=16 shift butterflies) reconstructs n==a*b and SRT radix-8 (digits {-4..4}, thresholds ±D/2 ±3D/2 ±5D/2 ±7D/2, 512-bit ge) divides without restoring of n; Toom-5 52-bit 5-way split reconstructs n==a*b and SRT radix-16 (digits {-8..8}, thresholds ±D/2 … ±15D/2, 512-bit ge) divides without restoring of n; Toom-6 43-bit 6-way split reconstructs n==a*b and SRT radix-32 (digits {-16..16}, thresholds ±D/2 … ±31D/2, 512-bit ge) divides without restoring of n; Toom-7 37-bit 7-way split reconstructs n==a*b and SRT radix-64 (digits {-32..32}, thresholds ±D/2 … ±63D/2, 512-bit ge) divides without restoring of n; Toom-8 32-bit 8-way split reconstructs n==a*b and SRT radix-128 (digits {-64..64}, thresholds ±D/2 … ±127D/2, 512-bit ge) divides without restoring of n; Toom-9 32-bit 9-way split (256-bit padded to 288) reconstructs n==a*b and SRT radix-256 (digits {-128..128}, thresholds ±D/2 … ±255D/2, 512-bit ge) divides without restoring of n; Toom-10 32-bit 10-way split (256-bit padded to 320) reconstructs n==a*b and SRT radix-512 (digits {-256..256}, thresholds ±D/2 … ±511D/2, 512-bit ge) divides without restoring of n; RNS (17 coprime 32-bit primes, Garner mixed-radix, product 544 bits) reconstructs n==a*b and Newton-Raphson reciprocal (v=2^(512-bitlen(d)), ten iterations v:=2v-((d*v*v)>>512), q=(n*v)>>512, 512-bit ge) divides without restoring of n — not CRT/Mersenne, not Hensel mod 2^256, not Goldschmidt, not Barrett mu from sparse 2^512; Schönhage–Strassen (negacyclic Fermat FFT over F7=2^128+1, length-32, ψ=2^4, ω=2^8 shift butterflies) reconstructs n==a*b and SRT radix-1024 (digits {-512..512}, thresholds ±D/2 … ±1023D/2, 10 bits/step, 512-bit ge) divides without restoring of n — not FNT over F6, not SRT radix-512, not Newton-Raphson, not Hensel; unbalanced Toom-Cook 3x7 (37-bit digits, three 111-bit groups, nine eval products at {0,±1,±2,±3,4,inf}, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^768/d) (q=(n*mu)>>768, 512-bit ge) divides without restoring of n — not balanced Toom-3..10, not SS, not SRT radix-1024, not Barrett mu=floor(2^512/d); unbalanced Toom-Cook 2x5 (52-bit digits, three 104-bit groups, six eval products at {0,±1,±2,inf}, Lagrange interpolation) reconstructs n==a*b and SRT radix-2048 (digits {-1024..1024}, thresholds ±D/2 … ±2047D/2, 11 bits/step, 512-bit ge) divides without restoring of n — not unbalanced Toom-3x7, not Barrett-768, not SRT radix-1024, not restoring of n; unbalanced Toom-Cook 2x7 (37-bit digits, four 74-bit groups, seven eval products at {0,±1,±2,±3} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^1024/d) (q=(n*mu)>>1024, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5, not unbalanced Toom-3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d), not SRT radix-2048, not restoring of n; rustc-only auditor recomputes LRI1 Merkle + LCR2 bind; radix-2^8, Knuth-D, CRT, Karatsuba/Barrett, Toom-3/Goldschmidt, NTT/SRT, Comba/NR, Toom-4/BZ, FNT/SRT-8, Toom-5/SRT-16, Toom-6/SRT-32, Toom-7/SRT-64, Toom-8/SRT-128, Toom-9/SRT-256, Toom-10/SRT-512, RNS/Newton, SS/SRT-1024, Toom-3x7/Barrett-768, Toom-2x5/SRT-2048, Toom-2x7/Barrett-1024, and IEEE-754 FFT+Montgomery REDC auditors recompute identity + OpenSSL dgst LRI1 Merkle; IEEE-754 binary64 FFT convolution (8-bit digits, length-64 Cooley-Tukey, not Fermat SS, not FNT, not NTT) reconstructs n==a*b and Montgomery REDC (R=2^512, even-d CRT) plus Jebelean exact q of n-r divides without restoring of n — not unbalanced Toom-2x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d), not SRT radix-4..2048, not Newton, not Hensel-of-n; Solinas NTT (p=2^64-2^32+1, 16-bit digits, length-32, ω=2^18, 2^64≡2^32-1 reduction — not p=998244353, not Fermat SS, not FNT, not IEEE-754 FFT) reconstructs n==a*b and Granlund–Montgomery magic (M=ceil(2^p/d) from nc=2^512-1-((2^512-1)%d), add-indicator, d-dependent shift — not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d), not Montgomery REDC, not Jebelean, not SRT, not Newton, not Hensel-of-n, not restoring of n; Dekker double-double convolution (32-bit digits, 8x8 schoolbook, Veltkamp split 2^27+1, Dekker two-product, Knuth two-sum — not IEEE-754 FFT, not FMA, not Solinas NTT, not Fermat SS, not FNT) reconstructs n==a*b and Cook–Sieveking precision-doubling reciprocal (8-bit leading-digit seed, fixed scale K=768, multiplicative y:=(y*(2^{K+1}-d*y))>>K until 8→16→…→1024 bits, q=(n*y)>>768, 512-bit ge — not fixed-width Newton 10 iters at 512, not Goldschmidt, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) in one shot, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not SRT, not Hensel-of-n, not restoring of n; IEEE-754 binary80 convolution (40-bit digits, 8x8 schoolbook, Veltkamp split 2^32+1, 64-bit significand with explicit integer bit — not binary64 Dekker Veltkamp 2^27+1, not FMA, not length-64 binary64 FFT, not Solinas NTT, not Fermat SS, not FNT) reconstructs n==a*b and Karp–Markstein half-plus reciprocal (16-bit leading-digit seed, fixed scale K=448, precision doubles only until 448 bits, q0=(n*y)>>448, exact r0=n-q0*d, one correction q=q0+(r0*y)>>448, 512-bit ge — not Cook–Sieveking K=768 to 1024, not fixed-width Newton 10 iters at 512, not Goldschmidt, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) in one shot, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not SRT, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x9 (29-bit digits, five 58-bit groups, nine eval products at {0,±1,±2,±3,±4} plus inf, Lagrange interpolation) reconstructs n==a*b and Svoboda–Tung (bit-normalize leading digit >= 2^15, m=floor((2^32-1)/(d1+1)), leading-digit qhat, Tung restore, 512-bit ge) divides without restoring of n — not Knuth two-digit estimate, not Barrett μ of the whole d, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n; unbalanced Toom-Cook 2x11 (24-bit digits, six 48-bit groups, eleven eval products at {0,±1,±2,±3,±4,±5} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^1280/d) (q=(n*mu)>>1280, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n); unbalanced Toom-Cook 2x13 (20-bit digits, seven 40-bit groups, thirteen eval products at {0,±1,±2,±3,±4,±5,±6} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^1536/d) (q=(n*mu)>>1536, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x15 (18-bit digits, eight 36-bit groups, fifteen eval products at {0,±1,±2,±3,±4,±5,±6,±7} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^1792/d) (q=(n*mu)>>1792, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x17 (16-bit digits, nine 32-bit groups, seventeen eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^2048/d) (q=(n*mu)>>2048, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x19 (16-bit digits, ten 32-bit groups, nineteen eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^2304/d) (q=(n*mu)>>2304, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, ; unbalanced Toom-Cook 2x21 (16-bit digits, eleven 32-bit groups, twenty-one eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^2560/d) (q=(n*mu)>>2560, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x23 (16-bit digits, twelve 32-bit groups, twenty-three eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^2816/d) (q=(n*mu)>>2816, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x25 (16-bit digits, thirteen 32-bit groups, twenty-five eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^3072/d) (q=(n*mu)>>3072, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x27 (16-bit digits, fourteen 32-bit groups, twenty-seven eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^3328/d) (q=(n*mu)>>3328, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x29 (16-bit digits, fifteen 32-bit groups, twenty-nine eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^3584/d) (q=(n*mu)>>3584, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x31 (16-bit digits, sixteen 32-bit groups, thirty-one eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^3840/d) (q=(n*mu)>>3840, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x33 (16-bit digits, seventeen 32-bit groups, thirty-three eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^4096/d) (q=(n*mu)>>4096, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x35 (16-bit digits, eighteen 32-bit groups, thirty-five eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^4352/d) (q=(n*mu)>>4352, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n); unbalanced Toom-Cook 2x37 (16-bit digits, nineteen 32-bit groups, thirty-seven eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^4608/d) (q=(n*mu)>>4608, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x39 (16-bit digits, twenty 32-bit groups, thirty-nine eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^4864/d) (q=(n*mu)>>4864, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x41 (16-bit digits, twenty-one 32-bit groups, forty-one eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19,±20} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^5120/d) (q=(n*mu)>>5120, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/2x39/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d) or floor(2^4864/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n; unbalanced Toom-Cook 2x43 (16-bit digits, twenty-two 32-bit groups, forty-three eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19,±20,±21} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^5376/d) (q=(n*mu)>>5376, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/2x39/2x41/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d) or floor(2^4864/d) or floor(2^5120/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, ; unbalanced Toom-Cook 2x45 (16-bit digits, twenty-three 32-bit groups, forty-five eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19,±20,±21,±22} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^5632/d) (q=(n*mu)>>5632, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/2x39/2x41/2x43/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d) or floor(2^4864/d) or floor(2^5120/d) or floor(2^5376/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, ; unbalanced Toom-Cook 2x47 (16-bit digits, twenty-four 32-bit groups, forty-seven eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19,±20,±21,±22,±23} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^5888/d) (q=(n*mu)>>5888, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/2x39/2x41/2x43/2x45/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d) or floor(2^4864/d) or floor(2^5120/d) or floor(2^5376/d) or floor(2^5632/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n); unbalanced Toom-Cook 2x49 (16-bit digits, twenty-five 32-bit groups, forty-nine eval products at {0,±1,±2,±3,±4,±5,±6,±7,±8,±9,±10,±11,±12,±13,±14,±15,±16,±17,±18,±19,±20,±21,±22,±23,±24} plus inf, Lagrange interpolation) reconstructs n==a*b and Barrett mu=floor(2^6144/d) (q=(n*mu)>>6144, 512-bit ge) divides without restoring of n — not unbalanced Toom-2x5/2x7/2x9/2x11/2x13/2x15/2x17/2x19/2x21/2x23/2x25/2x27/2x29/2x31/2x33/2x35/2x37/2x39/2x41/2x43/2x45/2x47/3x7, not Barrett mu=floor(2^512/d) or floor(2^768/d) or floor(2^1024/d) or floor(2^1280/d) or floor(2^1536/d) or floor(2^1792/d) or floor(2^2048/d) or floor(2^2304/d) or floor(2^2560/d) or floor(2^2816/d) or floor(2^3072/d) or floor(2^3328/d) or floor(2^3584/d) or floor(2^3840/d) or floor(2^4096/d) or floor(2^4352/d) or floor(2^4608/d) or floor(2^4864/d) or floor(2^5120/d) or floor(2^5376/d) or floor(2^5632/d) or floor(2^5888/d), not Svoboda–Tung, not Karp–Markstein, not Cook–Sieveking, not SRT, not Newton, not Goldschmidt, not Granlund–Montgomery, not Montgomery REDC, not Jebelean, not Hensel-of-n, not restoring of n)",
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
            "oracle_toom3": tg["src"],
            "oracle_ntt": ntt["src"],
            "oracle_comba": comba["src"],
            "oracle_toom4": t4["src"],
            "oracle_fnt": fnt["src"],
            "oracle_toom5": t5["src"],
            "oracle_toom6": t6["src"],
            "oracle_toom7": t7["src"],
            "oracle_toom8": t8["src"],
            "oracle_toom9": t9["src"],
            "oracle_toom10": t10["src"],
            "oracle_rns": rns["src"],
            "oracle_ss": ss["src"],
            "oracle_toom37": t37["src"],
            "oracle_toom25": t25["src"],
            "oracle_toom27": t27["src"],
            "oracle_fft": fft["src"],
            "oracle_solinas": sol["src"],
            "oracle_cook": cook["src"],
            "oracle_km": km["src"],
            "oracle_st": stw["src"],
            "oracle_toom211": t211["src"],
            "oracle_toom213": t213["src"],
            "oracle_toom215": t215["src"],
            "oracle_toom217": t217["src"],
            "oracle_toom219": t219["src"],
            "oracle_toom221": t221["src"],
            "oracle_toom223": t223["src"],
            "oracle_toom225": t225["src"],
            "oracle_toom227": t227["src"],
            "oracle_toom229": t229["src"],
            "oracle_toom231": t231["src"],
            "oracle_toom233": t233["src"],
            "oracle_toom235": t235["src"],
            "oracle_toom237": t237["src"],
            "oracle_toom239": t239["src"],
            "oracle_toom241": t241["src"],
            "oracle_toom243": t243["src"],
            "oracle_toom245": t245["src"],
            "oracle_toom247": t247["src"],
            "oracle_toom249": t249["src"],
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
            "toom3_py": sha256_file(ROOT / "test" / "prove_u512_toom3.py"),
            "ntt_py": sha256_file(ROOT / "test" / "prove_u512_ntt.py"),
            "comba_py": sha256_file(ROOT / "test" / "prove_u512_comba.py"),
            "toom4_py": sha256_file(ROOT / "test" / "prove_u512_toom4.py"),
            "fnt_py": sha256_file(ROOT / "test" / "prove_u512_fnt.py"),
            "toom5_py": sha256_file(ROOT / "test" / "prove_u512_toom5.py"),
            "toom6_py": sha256_file(ROOT / "test" / "prove_u512_toom6.py"),
            "toom7_py": sha256_file(ROOT / "test" / "prove_u512_toom7.py"),
            "toom8_py": sha256_file(ROOT / "test" / "prove_u512_toom8.py"),
            "toom9_py": sha256_file(ROOT / "test" / "prove_u512_toom9.py"),
            "toom10_py": sha256_file(ROOT / "test" / "prove_u512_toom10.py"),
            "rns_py": sha256_file(ROOT / "test" / "prove_u512_rns.py"),
            "ss_py": sha256_file(ROOT / "test" / "prove_u512_ss.py"),
            "toom37_py": sha256_file(ROOT / "test" / "prove_u512_toom37.py"),
            "toom25_py": sha256_file(ROOT / "test" / "prove_u512_toom25.py"),
            "toom27_py": sha256_file(ROOT / "test" / "prove_u512_toom27.py"),
            "fft_py": sha256_file(ROOT / "test" / "prove_u512_fft.py"),
            "solinas_py": sha256_file(ROOT / "test" / "prove_u512_solinas.py"),
            "cook_py": sha256_file(ROOT / "test" / "prove_u512_cook.py"),
            "km_py": sha256_file(ROOT / "test" / "prove_u512_km.py"),
            "st_py": sha256_file(ROOT / "test" / "prove_u512_st.py"),
            "toom211_py": sha256_file(ROOT / "test" / "prove_u512_toom211.py"),
            "toom213_py": sha256_file(ROOT / "test" / "prove_u512_toom213.py"),
            "toom215_py": sha256_file(ROOT / "test" / "prove_u512_toom215.py"),
            "toom217_py": sha256_file(ROOT / "test" / "prove_u512_toom217.py"),
            "toom219_py": sha256_file(ROOT / "test" / "prove_u512_toom219.py"),
            "toom221_py": sha256_file(ROOT / "test" / "prove_u512_toom221.py"),
            "toom223_py": sha256_file(ROOT / "test" / "prove_u512_toom223.py"),
            "toom225_py": sha256_file(ROOT / "test" / "prove_u512_toom225.py"),
            "toom227_py": sha256_file(ROOT / "test" / "prove_u512_toom227.py"),
            "toom229_py": sha256_file(ROOT / "test" / "prove_u512_toom229.py"),
            "toom231_py": sha256_file(ROOT / "test" / "prove_u512_toom231.py"),
            "toom233_py": sha256_file(ROOT / "test" / "prove_u512_toom233.py"),
            "toom235_py": sha256_file(ROOT / "test" / "prove_u512_toom235.py"),
            "toom237_py": sha256_file(ROOT / "test" / "prove_u512_toom237.py"),
            "toom239_py": sha256_file(ROOT / "test" / "prove_u512_toom239.py"),
            "toom241_py": sha256_file(ROOT / "test" / "prove_u512_toom241.py"),
            "toom243_py": sha256_file(ROOT / "test" / "prove_u512_toom243.py"),
            "toom245_py": sha256_file(ROOT / "test" / "prove_u512_toom245.py"),
            "toom247_py": sha256_file(ROOT / "test" / "prove_u512_toom247.py"),
            "toom249_py": sha256_file(ROOT / "test" / "prove_u512_toom249.py"),
            "bc_py": sha256_file(ROOT / "test" / "prove_u512_bc.py"),
            "verifier_bc": sha256_file(VERIFY_BC),
            "verifier_rust64": sha256_file(VERIFY_R64),
            "verifier_radix8": sha256_file(VERIFY_R8),
            "verifier_knuth_d": sha256_file(VERIFY_KD),
            "verifier_crt": sha256_file(VERIFY_CRT),
            "verifier_karatsuba": sha256_file(VERIFY_KS),
            "verifier_toom3": sha256_file(VERIFY_TG),
            "verifier_ntt": sha256_file(VERIFY_NTT),
            "verifier_comba": sha256_file(VERIFY_COMBA),
            "verifier_toom4": sha256_file(VERIFY_T4),
            "verifier_fnt": sha256_file(VERIFY_FNT),
            "verifier_toom5": sha256_file(VERIFY_T5),
            "verifier_toom6": sha256_file(VERIFY_T6),
            "verifier_toom7": sha256_file(VERIFY_T7),
            "verifier_toom8": sha256_file(VERIFY_T8),
            "verifier_toom9": sha256_file(VERIFY_T9),
            "verifier_toom10": sha256_file(VERIFY_T10),
            "verifier_rns": sha256_file(VERIFY_RNS),
            "verifier_ss": sha256_file(VERIFY_SS),
            "verifier_toom37": sha256_file(VERIFY_T37),
            "verifier_toom25": sha256_file(VERIFY_T25),
            "verifier_toom27": sha256_file(VERIFY_T27),
            "verifier_fft": sha256_file(VERIFY_FFT),
            "verifier_solinas": sha256_file(VERIFY_SOL),
            "verifier_cook": sha256_file(VERIFY_COOK),
            "verifier_km": sha256_file(VERIFY_KM),
            "verifier_st": sha256_file(VERIFY_ST),
            "verifier_toom211": sha256_file(VERIFY_T211),
            "verifier_toom213": sha256_file(VERIFY_T213),
            "verifier_toom215": sha256_file(VERIFY_T215),
            "verifier_toom217": sha256_file(VERIFY_T217),
            "verifier_toom219": sha256_file(VERIFY_T219),
            "verifier_toom221": sha256_file(VERIFY_T221),
            "verifier_toom223": sha256_file(VERIFY_T223),
            "verifier_toom225": sha256_file(VERIFY_T225),
            "verifier_toom227": sha256_file(VERIFY_T227),
            "verifier_toom229": sha256_file(VERIFY_T229),
            "verifier_toom231": sha256_file(VERIFY_T231),
            "verifier_toom233": sha256_file(VERIFY_T233),
            "verifier_toom235": sha256_file(VERIFY_T235),
            "verifier_toom237": sha256_file(VERIFY_T237),
            "verifier_toom239": sha256_file(VERIFY_T239),
            "verifier_toom241": sha256_file(VERIFY_T241),
            "verifier_toom243": sha256_file(VERIFY_T243),
            "verifier_toom245": sha256_file(VERIFY_T245),
            "verifier_toom247": sha256_file(VERIFY_T247),
            "verifier_toom249": sha256_file(VERIFY_T249),
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
            "toom3_batch_n": tg["n"],
            "ntt_batch_n": ntt["n"],
            "comba_batch_n": comba["n"],
            "toom4_batch_n": t4["n"],
            "fnt_batch_n": fnt["n"],
            "toom5_batch_n": t5["n"],
            "toom6_batch_n": t6["n"],
            "toom7_batch_n": t7["n"],
            "toom8_batch_n": t8["n"],
            "toom9_batch_n": t9["n"],
            "toom10_batch_n": t10["n"],
            "rns_batch_n": rns["n"],
            "ss_batch_n": ss["n"],
            "toom37_batch_n": t37["n"],
            "toom25_batch_n": t25["n"],
            "toom27_batch_n": t27["n"],
            "fft_batch_n": fft["n"],
            "solinas_batch_n": sol["n"],
            "cook_batch_n": cook["n"],
            "km_batch_n": km["n"],
            "st_batch_n": stw["n"],
            "toom211_batch_n": t211["n"],
            "toom213_batch_n": t213["n"],
            "toom215_batch_n": t215["n"],
            "toom217_batch_n": t217["n"],
            "toom219_batch_n": t219["n"],
            "toom221_batch_n": t221["n"],
            "toom223_batch_n": t223["n"],
            "toom225_batch_n": t225["n"],
            "toom227_batch_n": t227["n"],
            "toom229_batch_n": t229["n"],
            "toom231_batch_n": t231["n"],
            "toom233_batch_n": t233["n"],
            "toom235_batch_n": t235["n"],
            "toom237_batch_n": t237["n"],
            "toom239_batch_n": t239["n"],
            "toom241_batch_n": t241["n"],
            "toom243_batch_n": t243["n"],
            "toom245_batch_n": t245["n"],
            "toom247_batch_n": t247["n"],
            "toom249_batch_n": t249["n"],
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
    tgv = run([sys.executable, str(VERIFY_TG), str(EVID)], timeout=120)
    ok("standalone_toom3_verifier", tgv.returncode == 0 and "PASS" in tgv.stdout
       and "lri1_match" in tgv.stdout and "lcr2_toom3_bind" in tgv.stdout
       and "lcr2_full_phantom" in tgv.stdout, tgv.stdout.strip()[:240])
    nttv = run([sys.executable, str(VERIFY_NTT), str(EVID)], timeout=120)
    ok("standalone_ntt_verifier", nttv.returncode == 0 and "PASS" in nttv.stdout
       and "lri1_match" in nttv.stdout and "lcr2_ntt_bind" in nttv.stdout
       and "lcr2_full_phantom" in nttv.stdout, nttv.stdout.strip()[:240])
    combav = run([sys.executable, str(VERIFY_COMBA), str(EVID)], timeout=120)
    ok("standalone_comba_verifier", combav.returncode == 0 and "PASS" in combav.stdout
       and "lri1_match" in combav.stdout and "lcr2_comba_bind" in combav.stdout
       and "lcr2_full_phantom" in combav.stdout, combav.stdout.strip()[:240])
    t4v = run([sys.executable, str(VERIFY_T4), str(EVID)], timeout=120)
    ok("standalone_toom4_verifier", t4v.returncode == 0 and "PASS" in t4v.stdout
       and "lri1_match" in t4v.stdout and "lcr2_toom4_bind" in t4v.stdout
       and "lcr2_full_phantom" in t4v.stdout, t4v.stdout.strip()[:240])
    fntv = run([sys.executable, str(VERIFY_FNT), str(EVID)], timeout=120)
    ok("standalone_fnt_verifier", fntv.returncode == 0 and "PASS" in fntv.stdout
       and "lri1_match" in fntv.stdout and "lcr2_fnt_bind" in fntv.stdout
       and "lcr2_full_phantom" in fntv.stdout, fntv.stdout.strip()[:240])
    t5v = run([sys.executable, str(VERIFY_T5), str(EVID)], timeout=120)
    ok("standalone_toom5_verifier", t5v.returncode == 0 and "PASS" in t5v.stdout
       and "lri1_match" in t5v.stdout and "lcr2_toom5_bind" in t5v.stdout
       and "lcr2_full_phantom" in t5v.stdout, t5v.stdout.strip()[:240])
    t6v = run([sys.executable, str(VERIFY_T6), str(EVID)], timeout=120)
    ok("standalone_toom6_verifier", t6v.returncode == 0 and "PASS" in t6v.stdout
       and "lri1_match" in t6v.stdout and "lcr2_toom6_bind" in t6v.stdout
       and "lcr2_full_phantom" in t6v.stdout, t6v.stdout.strip()[:240])
    t7v = run([sys.executable, str(VERIFY_T7), str(EVID)], timeout=120)
    ok("standalone_toom7_verifier", t7v.returncode == 0 and "PASS" in t7v.stdout
       and "lri1_match" in t7v.stdout and "lcr2_toom7_bind" in t7v.stdout
       and "lcr2_full_phantom" in t7v.stdout, t7v.stdout.strip()[:240])
    t8v = run([sys.executable, str(VERIFY_T8), str(EVID)], timeout=120)
    ok("standalone_toom8_verifier", t8v.returncode == 0 and "PASS" in t8v.stdout
       and "lri1_match" in t8v.stdout and "lcr2_toom8_bind" in t8v.stdout
       and "lcr2_full_phantom" in t8v.stdout, t8v.stdout.strip()[:240])
    t9v = run([sys.executable, str(VERIFY_T9), str(EVID)], timeout=120)
    ok("standalone_toom9_verifier", t9v.returncode == 0 and "PASS" in t9v.stdout
       and "lri1_match" in t9v.stdout and "lcr2_toom9_bind" in t9v.stdout
       and "lcr2_full_phantom" in t9v.stdout, t9v.stdout.strip()[:240])
    t10v = run([sys.executable, str(VERIFY_T10), str(EVID)], timeout=120)
    ok("standalone_toom10_verifier", t10v.returncode == 0 and "PASS" in t10v.stdout
       and "lri1_match" in t10v.stdout and "lcr2_toom10_bind" in t10v.stdout
       and "lcr2_full_phantom" in t10v.stdout, t10v.stdout.strip()[:240])
    rnsv = run([sys.executable, str(VERIFY_RNS), str(EVID)], timeout=120)
    ok("standalone_rns_verifier", rnsv.returncode == 0 and "PASS" in rnsv.stdout
       and "lri1_match" in rnsv.stdout and "lcr2_rns_bind" in rnsv.stdout
       and "lcr2_full_phantom" in rnsv.stdout, rnsv.stdout.strip()[:240])
    ssv = run([sys.executable, str(VERIFY_SS), str(EVID)], timeout=120)
    ok("standalone_ss_verifier", ssv.returncode == 0 and "PASS" in ssv.stdout
       and "lri1_match" in ssv.stdout and "lcr2_ss_bind" in ssv.stdout
       and "lcr2_full_phantom" in ssv.stdout, ssv.stdout.strip()[:240])
    t37v = run([sys.executable, str(VERIFY_T37), str(EVID)], timeout=120)
    ok("standalone_toom37_verifier", t37v.returncode == 0 and "PASS" in t37v.stdout
       and "lri1_match" in t37v.stdout and "lcr2_toom37_bind" in t37v.stdout
       and "lcr2_full_phantom" in t37v.stdout, t37v.stdout.strip()[:240])
    t25v = run([sys.executable, str(VERIFY_T25), str(EVID)], timeout=120)
    ok("standalone_toom25_verifier", t25v.returncode == 0 and "PASS" in t25v.stdout
       and "lri1_match" in t25v.stdout and "lcr2_toom25_bind" in t25v.stdout
       and "lcr2_full_phantom" in t25v.stdout, t25v.stdout.strip()[:240])
    t27v = run([sys.executable, str(VERIFY_T27), str(EVID)], timeout=120)
    ok("standalone_toom27_verifier", t27v.returncode == 0 and "PASS" in t27v.stdout
       and "lri1_match" in t27v.stdout and "lcr2_toom27_bind" in t27v.stdout
       and "lcr2_full_phantom" in t27v.stdout, t27v.stdout.strip()[:240])
    fftv = run([sys.executable, str(VERIFY_FFT), str(EVID)], timeout=120)
    ok("standalone_fft_verifier", fftv.returncode == 0 and "PASS" in fftv.stdout
       and "lri1_match" in fftv.stdout and "lcr2_fft_bind" in fftv.stdout
       and "lcr2_full_phantom" in fftv.stdout, fftv.stdout.strip()[:240])
    solv = run([sys.executable, str(VERIFY_SOL), str(EVID)], timeout=120)
    ok("standalone_solinas_verifier", solv.returncode == 0 and "PASS" in solv.stdout
       and "lri1_match" in solv.stdout and "lcr2_solinas_bind" in solv.stdout
       and "lcr2_full_phantom" in solv.stdout, solv.stdout.strip()[:240])
    cookv = run([sys.executable, str(VERIFY_COOK), str(EVID)], timeout=120)
    ok("standalone_cook_verifier", cookv.returncode == 0 and "PASS" in cookv.stdout
       and "lri1_match" in cookv.stdout and "lcr2_cook_bind" in cookv.stdout
       and "lcr2_full_phantom" in cookv.stdout, cookv.stdout.strip()[:240])
    kmv = run([sys.executable, str(VERIFY_KM), str(EVID)], timeout=120)
    ok("standalone_km_verifier", kmv.returncode == 0 and "PASS" in kmv.stdout
       and "lri1_match" in kmv.stdout and "lcr2_km_bind" in kmv.stdout
       and "lcr2_full_phantom" in kmv.stdout, kmv.stdout.strip()[:240])
    stv = run([sys.executable, str(VERIFY_ST), str(EVID)], timeout=120)
    ok("standalone_st_verifier", stv.returncode == 0 and "PASS" in stv.stdout
       and "lri1_match" in stv.stdout and "lcr2_st_bind" in stv.stdout
       and "lcr2_full_phantom" in stv.stdout, stv.stdout.strip()[:240])
    t211v = run([sys.executable, str(VERIFY_T211), str(EVID)], timeout=120)
    ok("standalone_toom211_verifier", t211v.returncode == 0 and "PASS" in t211v.stdout
       and "lri1_match" in t211v.stdout and "lcr2_toom211_bind" in t211v.stdout
       and "lcr2_full_phantom" in t211v.stdout, t211v.stdout.strip()[:240])
    t213v = run([sys.executable, str(VERIFY_T213), str(EVID)], timeout=120)
    ok("standalone_toom213_verifier", t213v.returncode == 0 and "PASS" in t213v.stdout
       and "lri1_match" in t213v.stdout and "lcr2_toom213_bind" in t213v.stdout
       and "lcr2_full_phantom" in t213v.stdout, t213v.stdout.strip()[:240])
    t215v = run([sys.executable, str(VERIFY_T215), str(EVID)], timeout=120)
    ok("standalone_toom215_verifier", t215v.returncode == 0 and "PASS" in t215v.stdout
       and "lri1_match" in t215v.stdout and "lcr2_toom215_bind" in t215v.stdout
       and "lcr2_full_phantom" in t215v.stdout, t215v.stdout.strip()[:240])
    t217v = run([sys.executable, str(VERIFY_T217), str(EVID)], timeout=120)
    ok("standalone_toom217_verifier", t217v.returncode == 0 and "PASS" in t217v.stdout
       and "lri1_match" in t217v.stdout and "lcr2_toom217_bind" in t217v.stdout
       and "lcr2_full_phantom" in t217v.stdout, t217v.stdout.strip()[:240])
    t219v = run([sys.executable, str(VERIFY_T219), str(EVID)], timeout=180)
    ok("standalone_toom219_verifier", t219v.returncode == 0 and "PASS" in t219v.stdout
       and "lri1_match" in t219v.stdout and "lcr2_toom219_bind" in t219v.stdout
       and "lcr2_full_phantom" in t219v.stdout, t219v.stdout.strip()[:240])
    t221v = run([sys.executable, str(VERIFY_T221), str(EVID)], timeout=240)
    ok("standalone_toom221_verifier", t221v.returncode == 0 and "PASS" in t221v.stdout
       and "lri1_match" in t221v.stdout and "lcr2_toom221_bind" in t221v.stdout
       and "lcr2_full_phantom" in t221v.stdout, t221v.stdout.strip()[:240])
    t223v = run([sys.executable, str(VERIFY_T223), str(EVID)], timeout=300)
    ok("standalone_toom223_verifier", t223v.returncode == 0 and "PASS" in t223v.stdout
       and "lri1_match" in t223v.stdout and "lcr2_toom223_bind" in t223v.stdout
       and "lcr2_full_phantom" in t223v.stdout, t223v.stdout.strip()[:240])
    t225v = run([sys.executable, str(VERIFY_T225), str(EVID)], timeout=400)
    ok("standalone_toom225_verifier", t225v.returncode == 0 and "PASS" in t225v.stdout
       and "lri1_match" in t225v.stdout and "lcr2_toom225_bind" in t225v.stdout
       and "lcr2_full_phantom" in t225v.stdout, t225v.stdout.strip()[:240])
    t227v = run([sys.executable, str(VERIFY_T227), str(EVID)], timeout=500)
    ok("standalone_toom227_verifier", t227v.returncode == 0 and "PASS" in t227v.stdout
       and "lri1_match" in t227v.stdout and "lcr2_toom227_bind" in t227v.stdout
       and "lcr2_full_phantom" in t227v.stdout, t227v.stdout.strip()[:240])
    t229v = run([sys.executable, str(VERIFY_T229), str(EVID)], timeout=600)
    ok("standalone_toom229_verifier", t229v.returncode == 0 and "PASS" in t229v.stdout
       and "lri1_match" in t229v.stdout and "lcr2_toom229_bind" in t229v.stdout
       and "lcr2_full_phantom" in t229v.stdout, t229v.stdout.strip()[:240])
    t231v = run([sys.executable, str(VERIFY_T231), str(EVID)], timeout=800)
    ok("standalone_toom231_verifier", t231v.returncode == 0 and "PASS" in t231v.stdout
       and "lri1_match" in t231v.stdout and "lcr2_toom231_bind" in t231v.stdout
       and "lcr2_full_phantom" in t231v.stdout, t231v.stdout.strip()[:240])
    t233v = run([sys.executable, str(VERIFY_T233), str(EVID)], timeout=1000)
    ok("standalone_toom233_verifier", t233v.returncode == 0 and "PASS" in t233v.stdout
       and "lri1_match" in t233v.stdout and "lcr2_toom233_bind" in t233v.stdout
       and "lcr2_full_phantom" in t233v.stdout, t233v.stdout.strip()[:240])
    t235v = run([sys.executable, str(VERIFY_T235), str(EVID)], timeout=1200)
    ok("standalone_toom235_verifier", t235v.returncode == 0 and "PASS" in t235v.stdout
       and "lri1_match" in t235v.stdout and "lcr2_toom235_bind" in t235v.stdout
       and "lcr2_full_phantom" in t235v.stdout, t235v.stdout.strip()[:240])
    t237v = run([sys.executable, str(VERIFY_T237), str(EVID)], timeout=1400)
    ok("standalone_toom237_verifier", t237v.returncode == 0 and "PASS" in t237v.stdout
       and "lri1_match" in t237v.stdout and "lcr2_toom237_bind" in t237v.stdout
       and "lcr2_full_phantom" in t237v.stdout, t237v.stdout.strip()[:240])
    t239v = run([sys.executable, str(VERIFY_T239), str(EVID)], timeout=1600)
    ok("standalone_toom239_verifier", t239v.returncode == 0 and "PASS" in t239v.stdout
       and "lri1_match" in t239v.stdout and "lcr2_toom239_bind" in t239v.stdout
       and "lcr2_full_phantom" in t239v.stdout, t239v.stdout.strip()[:240])
    t241v = run([sys.executable, str(VERIFY_T241), str(EVID)], timeout=1800)
    ok("standalone_toom241_verifier", t241v.returncode == 0 and "PASS" in t241v.stdout
       and "lri1_match" in t241v.stdout and "lcr2_toom241_bind" in t241v.stdout
       and "lcr2_full_phantom" in t241v.stdout, t241v.stdout.strip()[:240])
    t243v = run([sys.executable, str(VERIFY_T243), str(EVID)], timeout=2000)
    ok("standalone_toom243_verifier", t243v.returncode == 0 and "PASS" in t243v.stdout
       and "lri1_match" in t243v.stdout and "lcr2_toom243_bind" in t243v.stdout
       and "lcr2_full_phantom" in t243v.stdout, t243v.stdout.strip()[:240])
    t245v = run([sys.executable, str(VERIFY_T245), str(EVID)], timeout=2200)
    ok("standalone_toom245_verifier", t245v.returncode == 0 and "PASS" in t245v.stdout
       and "lri1_match" in t245v.stdout and "lcr2_toom245_bind" in t245v.stdout
       and "lcr2_full_phantom" in t245v.stdout, t245v.stdout.strip()[:240])
    t247v = run([sys.executable, str(VERIFY_T247), str(EVID)], timeout=2400)
    ok("standalone_toom247_verifier", t247v.returncode == 0 and "PASS" in t247v.stdout
       and "lri1_match" in t247v.stdout and "lcr2_toom247_bind" in t247v.stdout
       and "lcr2_full_phantom" in t247v.stdout, t247v.stdout.strip()[:240])
    t249v = run([sys.executable, str(VERIFY_T249), str(EVID)], timeout=2600)
    ok("standalone_toom249_verifier", t249v.returncode == 0 and "PASS" in t249v.stdout
       and "lri1_match" in t249v.stdout and "lcr2_toom249_bind" in t249v.stdout
       and "lcr2_full_phantom" in t249v.stdout, t249v.stdout.strip()[:240])

    npass = sum(1 for _, c, _ in CHECKS if c)
    print(f"\n{npass}/{len(CHECKS)} PASS")
    print("lnr1", py_root, "lcr2", lcr_root, "full", full["root"], "lge1", ge["root"], "lri1", ri["root"], "lip1", lip["n"])
    print("self_gate_steps", s_gate, "class EXPERIMENTAL toom249+Barrett-6144 auditor not EVM mulmod not a pool")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
