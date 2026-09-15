#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Head-to-head value proof: LIN vs established-language oracles.

This harness does not ask whether LIN is a better programming language than
C, Rust, Python, or Solidity. That claim is NOT-PROVEN and must stay so.

It asks a narrower, auditable question:

    On a published numeric kernel (UniswapV2Library.getAmountOut), do
    Python (unbounded int), GCC C (uint64), and LIN (Compiler-0 VM)
    return the same integer, and can a third party recompute a SHA-256
    receipt without the LIN compiler?

Domain (R5): TOY_I64. Intermediates that do not fit in signed 64-bit are
rejected as out of domain, not as a Mainnet proof.

Usage:
    python3 test/prove_value_vs_established.py
    python3 test/prove_value_vs_established.py --iterations 200
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
MANIFEST = FIX / "manifest.json"
UNISWAP_SOL = FIX / "UniswapV2Library.sol"
UNISWAP_LIN = ROOT / "src" / "lin_uniswap_v2_library.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
XREC = ROOT / "transpile" / "c" / "bin" / "lin_c_receipt"
VERIFY_RECEIPT = ROOT / "benchmarks" / "verify_receipt.py"
SQ_RECEIPT = ROOT / "benchmarks" / "fixtures" / "receipt_sqr9.json"

CANONICAL = (10000, 50000, 100000, 16624)
I64_MAX = (1 << 63) - 1

C_SRC = r"""
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    unsigned long long amount_in, reserve_in, reserve_out, fee, num, den;
    if (argc != 4) return 2;
    amount_in = strtoull(argv[1], 0, 10);
    reserve_in = strtoull(argv[2], 0, 10);
    reserve_out = strtoull(argv[3], 0, 10);
    if (amount_in == 0ULL || reserve_in == 0ULL || reserve_out == 0ULL) {
        puts("0");
        return 0;
    }
    fee = amount_in * 997ULL;
    num = fee * reserve_out;
    den = reserve_in * 1000ULL + fee;
    printf("%llu\n", num / den);
    return 0;
}
"""


class Claim:
    def __init__(self, ident: str, description: str, status: str, note: str = ""):
        self.ident = ident
        self.description = description
        self.status = status
        self.note = note

    def line(self) -> str:
        s = f"  [{self.status}] {self.ident:4s}  {self.description}"
        if self.note:
            s += f"\n            note: {self.note}"
        return s


def run(*argv: str, timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(
        [str(a) for a in argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip()


def py_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee = amount_in * 997
    num = fee * reserve_out
    den = reserve_in * 1000 + fee
    return num // den


def i64_domain(amount_in: int, reserve_in: int, reserve_out: int) -> bool:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return True
    fee = amount_in * 997
    num = fee * reserve_out
    den = reserve_in * 1000 + fee
    return max(fee, num, den) <= I64_MAX


def build_c_oracle() -> Path:
    fd, src_path = tempfile.mkstemp(suffix=".c", prefix="lin_vproof_")
    os.write(fd, C_SRC.encode("utf-8"))
    os.close(fd)
    bin_path = Path(src_path).with_suffix("")
    rc, out = run("cc", "-O2", "-std=c11", "-o", str(bin_path), src_path)
    Path(src_path).unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError(f"cc failed to build C oracle: {out}")
    return bin_path


def c_amount_out(binary: Path, amount_in: int, reserve_in: int, reserve_out: int) -> int:
    rc, out = run(str(binary), str(amount_in), str(reserve_in), str(reserve_out))
    if rc != 0:
        raise RuntimeError(f"C oracle rc={rc}: {out}")
    return int(out.splitlines()[-1])


def lin_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    rc, out = run(C0, "vm", UNISWAP_LIN, "get_amount_out",
                  amount_in, reserve_in, reserve_out)
    m = re.search(r"\bvalue=(-?\d+)\b", out)
    if rc != 0 or m is None:
        raise RuntimeError(f"LIN oracle rc={rc}: {out}")
    return int(m.group(1))


def v1_head_to_head(iterations: int) -> tuple[str, str]:
    if not C0.exists():
        return "FAIL", f"{C0} missing; run `make -C transpile/c all`"
    if not UNISWAP_LIN.exists():
        return "FAIL", f"{UNISWAP_LIN} missing"

    sol = UNISWAP_SOL.read_text(encoding="utf-8")
    if "amountIn.mul(997)" not in sol or "numerator / denominator" not in sol:
        return "FAIL", "pinned UniswapV2Library.sol no longer contains getAmountOut formula"

    binary = build_c_oracle()
    try:
        vectors = [CANONICAL[:3]]
        rng = random.Random(20260915)
        while len(vectors) < iterations:
            a, r_in, r_out = (rng.randint(1, 10**6),
                              rng.randint(1, 10**7),
                              rng.randint(1, 10**7))
            if i64_domain(a, r_in, r_out):
                vectors.append((a, r_in, r_out))

        checked = 0
        for amount_in, reserve_in, reserve_out in vectors:
            py = py_amount_out(amount_in, reserve_in, reserve_out)
            cc = c_amount_out(binary, amount_in, reserve_in, reserve_out)
            lin = lin_amount_out(amount_in, reserve_in, reserve_out)
            checked += 1
            if not (py == cc == lin):
                return "FAIL", (
                    f"divergence on ({amount_in},{reserve_in},{reserve_out}): "
                    f"python={py} gcc={cc} lin={lin}"
                )
        if py_amount_out(*CANONICAL[:3]) != CANONICAL[3]:
            return "FAIL", "canonical Uniswap vector is not 16624"
        return "PASS", (
            f"getAmountOut bit-exact Python==GCC-C==LIN on {checked} TOY_I64 "
            f"vectors; canonical (10000,50000,100000)->{CANONICAL[3]} matches "
            "UniswapV2Library.sol formula. This is kernel parity, not a language win."
        )
    finally:
        binary.unlink(missing_ok=True)


def v2_independent_receipt() -> tuple[str, str]:
    if not XREC.exists():
        rc_b, out_b = run("make", "-C", str(ROOT / "transpile" / "c"), "xver")
        if rc_b != 0 or not XREC.exists():
            return "FAIL", f"{XREC} missing after xver (rc={rc_b}): {out_b}"

    rc, out = run(XREC, "--expr", "x * x", "--env", "x=9")
    if rc != 0:
        return "FAIL", f"lin_c_receipt rejected: {out}"

    def grab(name: str) -> str:
        m = re.search(rf"\b{name}=(?:\"([^\"]*)\"|([^\s]+))", out)
        if not m:
            raise RuntimeError(f"missing {name}")
        return (m.group(1) or m.group(2)).strip()

    expr, env = grab("expr"), grab("env")
    result, steps, sp = int(grab("result")), int(grab("steps")), int(grab("sp_at_ret"))
    code_sha = grab("code_sha256")
    root = grab("root").replace("sha256:", "")

    def leaf(domain: str, data: bytes) -> bytes:
        return hashlib.sha256(domain.encode("utf-8") + data).digest()

    def node(left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(b"node:" + left + right).digest()

    computed = node(
        node(leaf("lin:xver:source:", expr.encode("utf-8")),
             leaf("lin:xver:env:", env.encode("utf-8"))),
        node(bytes.fromhex(code_sha),
             leaf("lin:xver:exec:", f"{result}:{steps}:{sp}".encode("utf-8"))),
    ).hex()
    if computed != root:
        return "FAIL", f"python hashlib root {computed} != emitter {root}"
    if result != 81:
        return "FAIL", f"x*x for x=9 produced {result}"

    rc, _ = run("python3", VERIFY_RECEIPT, SQ_RECEIPT)
    if rc != 0:
        return "FAIL", "committed receipt_sqr9.json did not verify"

    txt = SQ_RECEIPT.read_text(encoding="utf-8")
    tampered = txt.replace('"output": "81"', '"output": "82"')
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                     delete=False) as tmp:
        tmp.write(tampered)
        tmp_path = Path(tmp.name)
    rc, _ = run("python3", VERIFY_RECEIPT, tmp_path)
    tmp_path.unlink(missing_ok=True)
    if rc == 0:
        return "FAIL", "tampered output+1 receipt was accepted"

    return "PASS", (
        f"receipt root {root} recomputed by Python hashlib (no LIN compiler); "
        "output+1 rejected. Tamper-evidence + re-execution, not zk soundness."
    )


def v3_upstream_pin() -> tuple[str, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    src = manifest["sources"]["UniswapV2Library.sol"]
    data = UNISWAP_SOL.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != src["bytes"] or digest != src["file_sha256"]:
        return "FAIL", (
            f"pin mismatch: expected sha256:{src['file_sha256']} ({src['bytes']}B), "
            f"got sha256:{digest} ({len(data)}B)"
        )
    return "PASS", (
        f"Uniswap/v2-periphery UniswapV2Library.sol pin sha256:{digest} "
        f"({src['bytes']}B) matches published digest. Provenance, not execution."
    )


def np_language_replacement() -> tuple[str, str]:
    return "NOT-PROVEN", (
        "LIN is not shown to be a better general-purpose language than "
        "C, Rust, Python, or Solidity. No LLVM -O3 general benchmark, no "
        "uint256 Mainnet Uniswap/Compound parity, no zk soundness, no paid "
        "counterparty. Value, if any, is attested numeric coprocessor parity "
        "(V1-V3), class TOY_I64 / EXPERIMENTAL. See docs/VALUE_PROOF_VS_ESTABLISHED.rulel."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iterations", type=int, default=200)
    args = ap.parse_args()
    if args.iterations < 1:
        ap.error("--iterations must be >= 1")

    claims = [
        Claim("V1", "Uniswap getAmountOut: Python == GCC C == LIN (TOY_I64)",
              *v1_head_to_head(args.iterations)),
        Claim("V2", "Independent SHA-256 receipt recompute + tamper reject",
              *v2_independent_receipt()),
        Claim("V3", "Canonical UniswapV2Library.sol provenance pin",
              *v3_upstream_pin()),
        Claim("NP", "LIN replaces C/Rust/Python/Solidity as a language",
              *np_language_replacement()),
    ]

    print("=" * 78)
    print("   LIN VALUE vs ESTABLISHED LANGUAGES")
    print("   (kernel parity + independent receipt; not a language contest)")
    print("=" * 78)
    for c in claims:
        print(c.line())

    failures = [c for c in claims if c.status == "FAIL"]
    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} claim(s))")
        return 1
    n_pass = len([c for c in claims if c.status == "PASS"])
    n_np = len([c for c in claims if c.status == "NOT-PROVEN"])
    print(f"RESULT: PASS ({n_pass} PASS, {n_np} NOT-PROVEN). "
          "Continue LIN only as an attested coprocessor, not as a language.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
