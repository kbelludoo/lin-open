#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI gate: the README §2 NOT PROVEN table is the only place forbidden overclaims
may appear. Re-introducing them as positive claims fails the PR.

Denial context (same line or ±240 chars): NOT PROVEN, FALSE AS STATED,
NOT claiming, must not be sold, etc.

Also requires the frozen one-liner in the grant-facing docs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ONE_LINER = (
    "LIN não executa seu sistema. "
    "Prova um kernel numérico pequeno com receipt stdlib + disputa otimista."
)

REQUIRED_ONE_LINER = [
    ROOT / "README.md",
    ROOT / "GRANT_PROPOSAL.md",
    ROOT / "docs" / "LIN_VALUE_PROPOSITION.md",
]

# Patterns that must not appear as marketing. The NOT PROVEN table is allowed
# because those rows carry a denial marker in-window.
FORBIDDEN = [
    (re.compile(r"\$1\.8T"), "$1.8T savings"),
    (re.compile(r"1\.8T saved", re.I), "1.8T saved"),
    (re.compile(r"faster than LLVM", re.I), "faster than LLVM"),
    (re.compile(r"vs LLVM/C/Rust"), "speed vs LLVM/C/Rust"),
    (re.compile(r"Full OpenSSL executes", re.I), "Full OpenSSL executes"),
    (re.compile(r"OpenSSL inteiro", re.I), "OpenSSL inteiro"),
    (re.compile(r"Full Uniswap protocol is replaced", re.I), "full Uniswap replaced"),
    (re.compile(r"Uniswap completo", re.I), "Uniswap completo"),
]

DENIAL = re.compile(
    r"NOT PROVEN|NOT-PROVEN|FALSE AS STATED|NOT claiming|not proven|"
    r"must not be sold|Nenhuma afirma[cç][aã]o|no general compiler|"
    r"pinned for provenance only|NOT SOUND|CONDITIONAL BASELINE|"
    r"FALSE_AS_STATED|NOT_PROVEN|must not be overclaimed",
    re.I,
)

SKIP_DIRS = {".git", "zig-out", "zig-cache", ".zig-cache", "bin", "__pycache__", "repos"}
SCAN_SUFFIX = {".md", ".py", ".rulel", ".html"}


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in SCAN_SUFFIX:
            continue
        if p.resolve() == Path(__file__).resolve():
            continue
        yield p


def violations_in(text: str, rel: str) -> list[str]:
    hits = []
    for rx, label in FORBIDDEN:
        for m in rx.finditer(text):
            lo = max(0, m.start() - 240)
            hi = min(len(text), m.end() + 240)
            window = text[lo:hi]
            if DENIAL.search(window):
                continue
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{rel}:{line}: {label} without denial marker")
    return hits


def main() -> int:
    missing = []
    for p in REQUIRED_ONE_LINER:
        if not p.is_file():
            missing.append(f"missing {p.relative_to(ROOT)}")
            continue
        body = p.read_text(encoding="utf-8")
        if ONE_LINER not in body:
            missing.append(f"{p.relative_to(ROOT)} missing frozen one-liner")
        title_ok = (
            "auditable scalar coprocessor" in body.lower()
            or "Auditable Scalar Coprocessor" in body
        )
        if p.name == "README.md" and not title_ok:
            missing.append("README.md title must say auditable scalar coprocessor")

    bad = []
    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        bad.extend(violations_in(text, str(p.relative_to(ROOT))))

    if missing or bad:
        print("FORBIDDEN OVERCLAIM GATE: FAIL")
        for x in missing + bad:
            print(f"  {x}")
        return 1
    print("FORBIDDEN OVERCLAIM GATE: PASS")
    print(f"  one-liner pinned in {len(REQUIRED_ONE_LINER)} grant-facing docs")
    print(f"  NOT PROVEN table remains the only home for denied claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
