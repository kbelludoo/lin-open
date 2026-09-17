#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.7: GNU MP mpz consensus (dlopen libgmp.so.10, not TCB)."""
from __future__ import annotations

from pathlib import Path

from prove_u512_ge import ge_batch_lines, oracle_batch
from prove_u512_lib import ROOT, UMAX, run, sha256_file

GMP_SRC = ROOT / "test" / "oracles" / "u512_gmp_oracle.c"
GMP_BIN = Path("/tmp/u512_gmp_oracle")


def compile_gmp() -> tuple[bool, str]:
    p = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-o", str(GMP_BIN),
             str(GMP_SRC), "-ldl"])
    return p.returncode == 0 and GMP_BIN.exists(), (p.stderr or "")[-200:]


def gmp_selftest() -> tuple[bool, str]:
    if not GMP_BIN.exists():
        return False, "missing gmp oracle binary"
    p = run([str(GMP_BIN), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def gmp_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run([str(GMP_BIN), "--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            if int(got.split()[0]) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def gmp_lcr2_bind(leaves: list[dict]) -> tuple[bool, str]:
    lines, expect = [], []
    for leaf in leaves:
        if leaf.get("class") not in ("EXACT_INPUT", "OVERPAID_INPUT"):
            continue
        ain = int(leaf["ain"], 0)
        rin = int(leaf["rin"], 0)
        rout = int(leaf["rout"], 0)
        aout = int(leaf["aout"], 0)
        fee, den = ain * 997, rin * 1000 + ain * 997
        if fee > UMAX or den > UMAX:
            return False, "width"
        lines.append(f"MULDIV {fee:064x} {rout:064x} {den:064x}\n")
        expect.append((1, aout, (fee * rout) % den))
    if len(expect) < 6:
        return False, f"need 6 settlement vectors, got {len(expect)}"
    ok, n, err = oracle_batch(GMP_BIN, "".join(lines), expect)
    return ok, f"n={n} {err}"


def gmp_check_tuples(lines: str, expect: list, match: bool):
    cc, err = compile_gmp()
    st, stout = gmp_selftest() if cc else (False, "no bin")
    ok, n, berr = oracle_batch(GMP_BIN, lines, expect) if cc else (False, 0, "no bin")
    ge_ok, ge_err = gmp_ge_batch() if cc else (False, "no bin")
    info = {
        "compile": cc, "selftest": st, "batch": ok, "n": n, "ge": ge_ok,
        "src": sha256_file(GMP_SRC),
    }
    return info, [
        ("gmp_mpz_compile", cc, err),
        ("gmp_mpz_selftest", st, stout),
        ("gmp_python_c11_full_range", ok and match, f"n={n} {berr}"),
        ("gmp_ge512", ge_ok, ge_err),
    ]
