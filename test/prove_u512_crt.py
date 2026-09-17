#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.13: FullMath CRT product + Newton inverse (not restoring, not Knuth D)."""
from __future__ import annotations

import sys

from prove_u512_ge import ge_batch_lines
from prove_u512_lib import ROOT, UMAX, run, sha256_file

CRT_SRC = ROOT / "test" / "oracles" / "u512_crt_fullmath.py"
PY = sys.executable


def _cmd() -> list[str]:
    return [PY, str(CRT_SRC)]


def crt_selftest() -> tuple[bool, str]:
    p = run(_cmd() + ["--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def crt_batch(lines: str, expect: list) -> tuple[bool, int, str]:
    p = run(_cmd() + ["--batch"], inp=lines, timeout=180)
    rows = [ln.split() for ln in p.stdout.splitlines() if ln]
    ok = p.returncode == 0 and len(rows) == len(expect)
    if ok:
        for (stt, q, r), row in zip(expect, rows):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                ok = False
                break
    return ok, len(expect), (p.stderr or "").strip()


def crt_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run(_cmd() + ["--batch"], inp=text, timeout=30)
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
    ok, n, err = crt_batch("".join(lines), expect)
    return ok, f"n={n} {err}"


def crt_lcr2_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT"), 6, False)


def crt_lcr2_full_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT", "PHANTOM_APPROVE"), 7, True)


def crt_lri1_identity(leaves: list[dict]) -> tuple[bool, str]:
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
    ok, n, err = crt_batch("".join(lines), expect)
    return ok, f"n={n} {err}"


def crt_check_tuples(lines: str, expect: list, match: bool):
    st, stout = crt_selftest()
    ok, n, berr = crt_batch(lines, expect) if st else (False, 0, "no selftest")
    ge_ok, ge_err = crt_ge_batch() if st else (False, "no selftest")
    info = {
        "selftest": st, "batch": ok, "n": n, "ge": ge_ok,
        "src": sha256_file(CRT_SRC),
    }
    return info, [
        ("crt_fullmath_selftest", st, stout),
        ("crt_python_c11_full_range", ok and match, f"n={n} {berr}"),
        ("crt_ge512", ge_ok, ge_err),
    ]
