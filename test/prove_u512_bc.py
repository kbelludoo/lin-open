#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.9: POSIX GNU bc tenth math (not GMP, not a compiler)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from prove_u512_ge import ge_batch_lines
from prove_u512_lib import ROOT, UMAX, sha256_file

BC_SRC = ROOT / "test" / "oracles" / "u512_bc_oracle.bc"


def bc_selftest() -> tuple[bool, str]:
    env = os.environ.copy()
    env["BC_LINE_LENGTH"] = "0"
    p = subprocess.run(["bc", "-q", str(BC_SRC)], capture_output=True, text=True,
                       timeout=30, check=False, env=env)
    out = (p.stdout or "").strip()
    ok = p.returncode == 0 and "SELFTEST_PASS" in out and "FAIL" not in out
    return ok, out or (p.stderr or "").strip()


def _ops_script(lines: str) -> str:
    body = ["scale=0", "umax=2^256-1"]
    for line in lines.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "MUL":
            a, b = int(p[1], 16), int(p[2], 16)
            body += [f"n={a}*{b}", "q=n%(umax+1)", "r=n/(umax+1)",
                     'print "1 ", q, " ", r, "\\n"']
        elif p[0] == "MULDIV":
            a, b, d = int(p[1], 16), int(p[2], 16), int(p[3], 16)
            if d == 0:
                body.append('print "-1 0 0\\n"')
            else:
                body += [
                    f"n={a}*{b}", f"d={d}", "q=n/d", "r=n%d",
                    "if (q*d+r != n) { print \"FAIL identity\\n\"; halt }",
                    "if (r >= d) { print \"FAIL rge\\n\"; halt }",
                    "if (q > umax) { print \"-2 0 0\\n\" } else { print \"1 \", q, \" \", r, \"\\n\" }",
                ]
        elif p[0] == "GE":
            a, b = int(p[1], 16), int(p[2], 16)
            body += [f"a={a}", f"b={b}", 'print (a >= b), "\\n"']
    return "\n".join(body) + "\n"


def _bc_batch(lines: str, expect: list[tuple[int, int, int]]) -> tuple[bool, int, str]:
    env = os.environ.copy()
    env["BC_LINE_LENGTH"] = "0"
    p = subprocess.run(["bc", "-q"], input=_ops_script(lines), capture_output=True,
                       text=True, timeout=120, check=False, env=env)
    rows = [ln.split() for ln in p.stdout.splitlines() if ln.strip() and not ln.startswith("FAIL")]
    ok = p.returncode == 0 and "FAIL" not in p.stdout and len(rows) == len(expect)
    if ok:
        for (stt, q, r), row in zip(expect, rows):
            got_s, got_q, got_r = int(row[0]), int(row[1]), int(row[2])
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                ok = False
                break
    err = (p.stderr or "").strip()
    if "FAIL" in p.stdout:
        err = (err + " " + p.stdout.strip()).strip()
    return ok, len(expect), err


def bc_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    env = os.environ.copy()
    env["BC_LINE_LENGTH"] = "0"
    p = subprocess.run(["bc", "-q"], input=_ops_script(text), capture_output=True,
                       text=True, timeout=30, check=False, env=env)
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
    ok, n, err = _bc_batch("".join(lines), expect)
    return ok, f"n={n} {err}"


def bc_lcr2_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT"), 6, False)


def bc_lcr2_full_bind(leaves: list[dict]) -> tuple[bool, str]:
    return _bind(leaves, ("EXACT_INPUT", "OVERPAID_INPUT", "PHANTOM_APPROVE"), 7, True)


def bc_lri1_identity(leaves: list[dict]) -> tuple[bool, str]:
    body = ["scale=0"]
    n_ok = 0
    for leaf in leaves:
        n = int(leaf["n"], 0)
        d = int(leaf["d"], 0)
        q = int(leaf["q"], 0)
        r = int(leaf["r"], 0)
        if d == 0:
            return False, "d=0"
        body += [
            f"n={n}", f"d={d}", f"q={q}", f"r={r}",
            "if (q*d+r != n) { print \"FAIL identity\\n\"; halt }",
            "if (r >= d) { print \"FAIL rge\\n\"; halt }",
            'print "OK\\n"',
        ]
        n_ok += 1
    if n_ok < 8:
        return False, f"need 8 LRI1 got {n_ok}"
    env = os.environ.copy()
    env["BC_LINE_LENGTH"] = "0"
    p = subprocess.run(["bc", "-q"], input="\n".join(body) + "\n", capture_output=True,
                       text=True, timeout=30, check=False, env=env)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip() == "OK"]
    ok = p.returncode == 0 and "FAIL" not in p.stdout and len(rows) == n_ok
    return ok, f"n={n_ok} {(p.stderr or '').strip()}"


def bc_check_tuples(lines: str, expect: list, match: bool):
    st, stout = bc_selftest()
    ok, n, berr = _bc_batch(lines, expect) if st else (False, 0, "no selftest")
    ge_ok, ge_err = bc_ge_batch() if st else (False, "no selftest")
    info = {
        "selftest": st, "batch": ok, "n": n, "ge": ge_ok,
        "src": sha256_file(BC_SRC),
    }
    return info, [
        ("posix_bc_selftest", st, stout),
        ("posix_bc_python_c11_full_range", ok and match, f"n={n} {berr}"),
        ("posix_bc_ge512", ge_ok, ge_err),
    ]
