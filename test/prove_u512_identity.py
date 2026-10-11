#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.5: Go math/big consensus + published LRI1 remainder-identity receipts."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from prove_u512_ge import ge_batch_lines, oracle_batch
from prove_u512_lib import (
    GO_SRC, LIN, RI_LEAF, RI_NODE,
    from_words, lin, lri1, merkle, py_muldiv, ri_dict, ri_vectors, run, sha256_file, words,
)

GO_BIN = Path("/tmp/u512_go_oracle")


def compile_go() -> tuple[bool, str]:
    p = run(["go", "build", "-o", str(GO_BIN), str(GO_SRC)], timeout=90)
    if p.returncode == 0 and GO_BIN.exists():
        return True, ""
    work = Path("/tmp/u512go")
    work.mkdir(exist_ok=True)
    (work / "go.mod").write_text("module u512oracle\n\ngo 1.22\n")
    shutil.copyfile(GO_SRC, work / "main.go")
    p2 = run(["go", "build", "-o", str(GO_BIN), "."], timeout=90, cwd=str(work))
    err = (p2.stderr or p.stderr or "")[-300:]
    return p2.returncode == 0 and GO_BIN.exists(), err


def go_selftest() -> tuple[bool, str]:
    if not GO_BIN.exists():
        return False, "missing go oracle"
    p = run([str(GO_BIN), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def go_batch(lines: str, expect: list[tuple[int, int, int]]) -> tuple[bool, int, str]:
    return oracle_batch(GO_BIN, lines, expect)


def go_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run([str(GO_BIN), "--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            if int(got.split()[0]) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def run_go_oracle(lines: str, expect: list[tuple[int, int, int]]) -> dict:
    cc, err = compile_go()
    st, stout = go_selftest()
    ok, n, berr = go_batch(lines, expect) if cc else (False, 0, "no binary")
    ge_ok, ge_err = go_ge_batch() if cc else (False, "no binary")
    return {
        "compile": cc, "compile_err": err,
        "selftest": st, "selftest_out": stout,
        "batch": ok, "n": n, "batch_err": berr,
        "ge": ge_ok, "ge_err": ge_err,
        "src": sha256_file(GO_SRC),
    }


def collect_lri1(rout_phantom: int) -> dict:
    src_d = hashlib.sha256(LIN.read_bytes()).digest()
    recs, leaves, detail = [], [], []
    ok = True
    for i, (name, a, b, d) in enumerate(ri_vectors(rout_phantom)):
        st_py, q_py, r_py = py_muldiv(a, b, d)
        n = a * b
        st, ss = lin("u512_muldiv_word", *words(a), *words(b), *words(d), -1, timeout=180)
        q = r = 0
        if st == 1:
            nq = 4 if q_py >= (1 << 64) else 1
            nr = 4 if r_py >= (1 << 64) else 1
            qw = [lin("u512_muldiv_word", *words(a), *words(b), *words(d), k, timeout=180)[0]
                  for k in range(nq)]
            rw = [lin("u512_muldiv_word", *words(a), *words(b), *words(d), 4 + k, timeout=180)[0]
                  for k in range(nr)]
            while len(qw) < 4:
                qw.append(0)
            while len(rw) < 4:
                rw.append(0)
            q, r = from_words(qw), from_words(rw)
        ident = st == 1 == st_py and q == q_py and r == r_py and q * d + r == n and r < d and ss != 0
        if not ident:
            ok = False
        detail.append(f"{name} lin_q={q} py_q={q_py} r={r} steps={ss} ident={ident}")
        recs.append(lri1(src_d, 5, i, n, d, q, r, ss, st))
        leaves.append(ri_dict(name, a, b, d, n, q, r, ss, st))
    root = merkle(recs, RI_LEAF, RI_NODE).hex()
    blob = Path("/tmp/u512_lri1.bin")
    blob.write_bytes(b"".join(recs))
    return {
        "ok": ok and len(recs) == 8,
        "root": root,
        "blob": blob,
        "leaves": leaves,
        "detail": " | ".join(detail),
        "n": len(recs),
        "src": sha256_file(LIN),
    }
