#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.10: rustc radix-2^64 schoolbook (carry independent of 16-bit LIN)."""
from __future__ import annotations

from pathlib import Path

from prove_u512_ge import ge_batch_lines, oracle_batch
from prove_u512_lib import ROOT, UMAX, run, sha256_file

R64_LIMBS = ROOT / "test" / "oracles" / "u512_rust64_limbs.rs"
R64_SRC = ROOT / "test" / "oracles" / "u512_rust64_oracle.rs"
R64_BIN = Path("/tmp/u512_rust64_oracle")
RUSTC = "rustc"


def compile_r64() -> tuple[bool, str]:
    p = run([RUSTC, "--edition", "2021", "-O", "-C", "debuginfo=0",
             "-o", str(R64_BIN), str(R64_SRC)], timeout=90)
    return p.returncode == 0 and R64_BIN.exists(), (p.stderr or "")[-280:]


def r64_selftest() -> tuple[bool, str]:
    if not R64_BIN.exists():
        return False, "missing rust64 binary"
    p = run([str(R64_BIN), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def r64_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run([str(R64_BIN), "--batch"], inp=text, timeout=30)
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
    ok, n, err = oracle_batch(R64_BIN, "".join(lines), expect)
    return ok, f"n={n} {err}"


def r64_lcr2_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT"), 6, False)


def r64_lcr2_full_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT", "PHANTOM_APPROVE"), 7, True)


def r64_lri1_identity(leaves: list[dict]) -> tuple[bool, str]:
    lines, expect = [], []
    for leaf in leaves:
        a, b, d = int(leaf["a"], 0), int(leaf["b"], 0), int(leaf["d"], 0)
        q, r = int(leaf["q"], 0), int(leaf["r"], 0)
        if d == 0:
            return False, "d=0"
        lines.append(f"MULDIV {a:064x} {b:064x} {d:064x}\n")
        expect.append((1, q, r))
    if len(expect) < 8:
        return False, f"need 8 LRI1 got {len(expect)}"
    ok, n, err = oracle_batch(R64_BIN, "".join(lines), expect)
    return ok, f"n={n} {err}"


def r64_check_tuples(lines: str, expect: list, match: bool):
    cc, err = compile_r64()
    st, stout = r64_selftest() if cc else (False, "no bin")
    ok, n, berr = oracle_batch(R64_BIN, lines, expect) if cc else (False, 0, "no bin")
    ge_ok, ge_err = r64_ge_batch() if cc else (False, "no bin")
    info = {
        "compile": cc, "selftest": st, "batch": ok, "n": n, "ge": ge_ok,
        "src": sha256_file(R64_SRC), "limbs": sha256_file(R64_LIMBS),
    }
    return info, [
        ("rust64_compile", cc, err),
        ("rust64_selftest", st, stout),
        ("rust64_python_c11_full_range", ok and match, f"n={n} {berr}"),
        ("rust64_ge512", ge_ok, ge_err),
    ]
