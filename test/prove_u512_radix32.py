#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.9: C11 radix-2^32 schoolbook (carry independent of 16-bit LIN)."""
from __future__ import annotations

from pathlib import Path

from prove_u512_ge import ge_batch_lines, oracle_batch
from prove_u512_lib import ROOT, UMAX, run, sha256_file

R32_SRC = ROOT / "test" / "oracles" / "u512_radix32_oracle.c"
R32_BIN = Path("/tmp/u512_radix32_oracle")


def compile_r32() -> tuple[bool, str]:
    p = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-o", str(R32_BIN), str(R32_SRC)])
    return p.returncode == 0 and R32_BIN.exists(), (p.stderr or "")[-240:]


def r32_selftest() -> tuple[bool, str]:
    if not R32_BIN.exists():
        return False, "missing radix32 binary"
    p = run([str(R32_BIN), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def r32_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run([str(R32_BIN), "--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            if int(got.split()[0]) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def _bind(leaves: list[dict], classes: tuple[str, ...], min_n: int, need_ph: bool) -> tuple[bool, str]:
    lines, expect = [], []
    n_ph = 0
    for leaf in leaves:
        cls = leaf.get("class")
        if cls not in classes:
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
        if cls == "PHANTOM_APPROVE":
            n_ph += 1
    if len(expect) < min_n or (need_ph and n_ph < 1):
        return False, f"need {min_n} got {len(expect)} ph={n_ph}"
    ok, n, err = oracle_batch(R32_BIN, "".join(lines), expect)
    return ok, f"n={n} {err}"


def r32_lcr2_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT"), 6, False)


def r32_lcr2_full_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT", "PHANTOM_APPROVE"), 7, True)


def r32_check_tuples(lines: str, expect: list, match: bool):
    cc, err = compile_r32()
    st, stout = r32_selftest() if cc else (False, "no bin")
    ok, n, berr = oracle_batch(R32_BIN, lines, expect) if cc else (False, 0, "no bin")
    ge_ok, ge_err = r32_ge_batch() if cc else (False, "no bin")
    info = {
        "compile": cc, "selftest": st, "batch": ok, "n": n, "ge": ge_ok,
        "src": sha256_file(R32_SRC),
    }
    return info, [
        ("radix32_compile", cc, err),
        ("radix32_selftest", st, stout),
        ("radix32_python_c11_full_range", ok and match, f"n={n} {berr}"),
        ("radix32_ge512", ge_ok, ge_err),
    ]
