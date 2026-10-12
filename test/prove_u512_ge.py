#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.4: OpenSSL BIGNUM consensus + published LGE1 512-bit ge receipts."""
from __future__ import annotations

import hashlib
from pathlib import Path

from prove_u512_lib import (
    BN_SRC, GE_LEAF, GE_NODE, LIN, ROOT,
    ge_dict, ge_vectors, hex512, lge1, lin, merkle, node_bin, run, sha256_file, words,
)

BN_BIN = Path("/tmp/u512_openssl_bn")


def compile_bn() -> tuple[bool, str]:
    p = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-o", str(BN_BIN), str(BN_SRC), "-ldl"])
    return p.returncode == 0 and BN_BIN.exists(), (p.stderr or "")[-200:]


def bn_selftest() -> tuple[bool, str]:
    if not BN_BIN.exists():
        return False, "missing openssl bn binary"
    p = run([str(BN_BIN), "--self-test"], timeout=30)
    return p.returncode == 0 and "SELFTEST_PASS" in p.stdout, p.stdout.strip()


def oracle_batch(bin_path: Path, lines: str, expect: list[tuple[int, int, int]],
                 timeout: int = 60) -> tuple[bool, int, str]:
    p = run([str(bin_path), "--batch"], inp=lines, timeout=timeout)
    rows = [ln.split() for ln in p.stdout.splitlines() if ln]
    ok = p.returncode == 0 and len(rows) == len(expect)
    if ok:
        for (stt, q, r), row in zip(expect, rows):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                ok = False
                break
    return ok, len(expect), (p.stderr or "").strip()


def ge_batch_lines() -> tuple[str, list[int]]:
    lines, want = [], []
    for a, b, ge, _ in ge_vectors():
        lines.append(f"GE {hex512(a)} {hex512(b)}\n")
        want.append(ge)
    return "".join(lines), want


def bn_ge_batch() -> tuple[bool, str]:
    text, want = ge_batch_lines()
    p = run([str(BN_BIN), "--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            if int(got) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def node_ge_batch() -> tuple[bool, str]:
    node = node_bin()
    oracle = ROOT / "test" / "oracles" / "u512_node_oracle.js"
    text, want = ge_batch_lines()
    p = run([node, str(oracle), "--batch"], inp=text, timeout=30)
    rows = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    ok = p.returncode == 0 and len(rows) == len(want)
    if ok:
        for got, exp in zip(rows, want):
            parts = got.split()
            if int(parts[0]) != exp:
                ok = False
                break
    return ok, (p.stderr or "").strip() or f"n={len(want)}"


def collect_lge1() -> dict:
    src_d = hashlib.sha256(LIN.read_bytes()).digest()
    recs, leaves, detail = [], [], []
    ok = True
    for i, (a, b, ge, name) in enumerate(ge_vectors()):
        got, steps = lin("u512_ge_word", *words(a, 8), *words(b, 8))
        py_ge = 1 if a >= b else 0
        match = got == ge == py_ge and steps != 0
        if not match:
            ok = False
        detail.append(f"{name} lin={got} py={py_ge} steps={steps}")
        recs.append(lge1(src_d, 4, i, a, b, got, steps))
        leaves.append(ge_dict(name, a, b, got, steps))
    root = merkle(recs, GE_LEAF, GE_NODE).hex()
    blob = Path("/tmp/u512_lge1.bin")
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
