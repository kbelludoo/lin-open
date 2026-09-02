#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Differential fuzz harness for the no-Zig LinVM host.

Compares real LIN modules against independent Python oracles over a large,
deterministic corpus. This is an *internal engineering evidence* tool, not a
claim about on-chain gas, protocol security, or performance vs other languages.

Categories:
  qoi       - phoboslab/qoi color-index hash
  uniswap   - UniswapV2Library pure math (get_amount_out/quote/get_amount_in)
  hash      - SipHash-2-4 + xxHash64 round functions
  tinyexpr  - codeplea/tinyexpr factorial (0..20 + fail-closed edges)

Usage:
  python3 test/fuzz_differential.py --iterations 100000
  python3 test/fuzz_differential.py --categories qoi,uniswap
  python3 test/fuzz_differential.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))

# Reuse the independent oracles and runner already proven in the repo.
from prove_all_claims_external import (  # noqa: E402
    C0,
    QOI_LIN,
    TINYEXPR_LIN,
    UNISWAP_LIN,
    qoi_python,
    run,
    siphash_round_py,
    tinyexpr_claims,
    uniswap_amount_out,
    uniswap_quote,
    value_of,
    xxhash64_round_py,
)


def fuzz_qoi(iterations: int, rng: random.Random) -> tuple[int, str | None]:
    for _ in range(iterations):
        r, g, b, a = [rng.randint(0, 255) for _ in range(4)]
        want = qoi_python(r, g, b, a)
        rc, out = run(C0, "vm", QOI_LIN, "qoi_color_hash", r, g, b, a)
        if rc != 0 or value_of(out) != want:
            return 0, f"qoi_color_hash({r},{g},{b},{a}): want={want} got={value_of(out)} rc={rc}"
    return iterations, None


def fuzz_uniswap(iterations: int, rng: random.Random) -> tuple[int, str | None]:
    total = 0
    for _ in range(iterations):
        amount_in = rng.randint(1, 10**6)
        reserve_in = rng.randint(1, 10**9)
        reserve_out = rng.randint(1, 10**9)
        want = uniswap_amount_out(amount_in, reserve_in, reserve_out)
        rc, out = run(C0, "vmfull", UNISWAP_LIN, "get_amount_out",
                      amount_in, reserve_in, reserve_out)
        total += 1
        if rc != 0 or value_of(out) != want:
            return total, f"get_amount_out({amount_in},{reserve_in},{reserve_out}): want={want} got={value_of(out)} rc={rc}"
    for _ in range(iterations // 10 + 1):
        a = rng.randint(1, 10**6)
        ra = rng.randint(1, 10**9)
        rb = rng.randint(1, 10**9)
        want = uniswap_quote(a, ra, rb)
        rc, out = run(C0, "vmfull", UNISWAP_LIN, "quote", a, ra, rb)
        total += 1
        if rc != 0 or value_of(out) != want:
            return total, f"quote({a},{ra},{rb}): want={want} got={value_of(out)} rc={rc}"
    return total, None


def fuzz_hash(iterations: int, rng: random.Random) -> tuple[int, str | None]:
    total = 0
    for _ in range(iterations):
        sv = [rng.randint(-(2**62), 2**62) for _ in range(4)]
        want = siphash_round_py(*sv)
        rc, out = run(C0, "vmfull", QOI_LIN, "siphash_round", *sv)
        total += 1
        if rc != 0 or value_of(out) != want:
            return total, f"siphash_round({sv}): want={want} got={value_of(out)} rc={rc}"
        a = rng.randint(-(2**62), 2**62)
        inp = rng.randint(-(2**62), 2**62)
        want = xxhash64_round_py(a, inp)
        rc, out = run(C0, "vmfull", QOI_LIN, "xxhash64_round", a, inp)
        total += 1
        if rc != 0 or value_of(out) != want:
            return total, f"xxhash64_round({a},{inp}): want={want} got={value_of(out)} rc={rc}"
    return total, None


def fuzz_tinyexpr(iterations: int) -> tuple[int, str | None]:
    """Use the deterministic boundary rather than random n (module is bounded)."""
    status, err = tinyexpr_claims()
    if status != "PASS":
        return 0, err
    return 21 + 3, None  # 0..20 + 3 fail-closed edges


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iterations", type=int, default=100000,
                    help="vectors per random category (default 100000)")
    ap.add_argument("--categories", default="qoi,uniswap,hash,tinyexpr")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    start = time.monotonic()
    categories = {c.strip() for c in args.categories.split(",") if c.strip()}
    results: dict[str, dict] = {}
    failures: list[str] = []

    if "qoi" in categories:
        n, err = fuzz_qoi(args.iterations, rng)
        results["qoi"] = {"vectors": n, "error": err}
        if err:
            failures.append(err)
    if "uniswap" in categories:
        n, err = fuzz_uniswap(args.iterations, rng)
        results["uniswap"] = {"vectors": n, "error": err}
        if err:
            failures.append(err)
    if "hash" in categories:
        n, err = fuzz_hash(args.iterations, rng)
        results["hash"] = {"vectors": n, "error": err}
        if err:
            failures.append(err)
    if "tinyexpr" in categories:
        n, err = fuzz_tinyexpr(args.iterations)
        results["tinyexpr"] = {"vectors": n, "error": err}
        if err:
            failures.append(err)

    elapsed = time.monotonic() - start
    summary = {
        "status": "PASS" if not failures else "FAIL",
        "categories": results,
        "elapsed_seconds": round(elapsed, 3),
        "iterations_per_category": args.iterations,
        "seed": args.seed,
        "note": "Internal differential evidence only. Not a claim of on-chain "
                "gas savings or competitiveness with GCC/LLVM/Rust.",
    }
    if args.report:
        Path(args.report).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"report written: {args.report}")
    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if failures else 0

    print("=" * 78)
    print("   LIN DIFFERENTIAL FUZZ (no Zig, C11 + Python oracle)")
    print("=" * 78)
    for name, r in results.items():
        status = "PASS" if not r["error"] else "FAIL"
        print(f"  [{status}] {name:9s} vectors={r['vectors']}")
        if r["error"]:
            print(f"            error: {r['error']}")
    print(f"  elapsed: {elapsed:.3f}s")
    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
