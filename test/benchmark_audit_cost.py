#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Microbenchmark: producer vs independent verifier cost for LIN compute receipts.

This is an internal engineering measurement. It does NOT claim "gas savings",
"better than EVM", or "better than LLVM/C/Rust". It only reports:

  producer_seconds   = time for lin_c_receipt to parse/eval/lower/VM + emit root
  verifier_seconds   = time for Python stdlib to recompute the same root
  ratio              = producer / verifier (informational only)

The verifier never invokes the producer compiler, so this is the measurable
meaning of "audit without trusting the execution path" inside this repo.

Usage:
  python3 test/benchmark_audit_cost.py --iterations 1000
  python3 test/benchmark_audit_cost.py --iterations 1000 --json --report /tmp/bench.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))
from prove_all_claims_external import XREC, receipt_root_from_parts, run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iterations", type=int, default=1000)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    if args.iterations < 1:
        ap.error("--iterations must be >= 1")

    fields_list: list[dict] = []
    producer_start = time.monotonic()
    producer_errors = []
    for i in range(args.iterations):
        expr = "x*x"
        env = f"x={i}"
        rc, out = run(XREC, "--expr", expr, "--env", env)
        if rc != 0:
            producer_errors.append(out)
            break
        m = re.search(r"root=\"sha256:([0-9a-f]+)\"", out)
        m2 = re.search(r"result=(-?\d+)", out)
        m3 = re.search(r"steps=(\d+)", out)
        m4 = re.search(r"sp_at_ret=(\d+)", out)
        m5 = re.search(r"code_sha256=\"([0-9a-f]+)\"", out)
        if not (m and m2 and m3 and m4 and m5):
            producer_errors.append(out)
            break
        fields_list.append({
            "expr": expr,
            "env": env,
            "result": int(m2.group(1)),
            "steps": int(m3.group(1)),
            "sp_at_ret": int(m4.group(1)),
            "code_sha256": m5.group(1),
            "merkle_root": m.group(1),
        })
    producer_elapsed = time.monotonic() - producer_start

    verifier_start = time.monotonic()
    verifier_errors = []
    verified = 0
    for f in fields_list:
        claimed = f["merkle_root"]
        computed = receipt_root_from_parts(
            f["expr"], f["env"], f["result"], f["steps"],
            f["sp_at_ret"], f["code_sha256"],
        )
        if computed == claimed:
            verified += 1
        else:
            verifier_errors.append("root mismatch")
    verifier_elapsed = time.monotonic() - verifier_start

    ratio = producer_elapsed / verifier_elapsed if verifier_elapsed > 0 else 0.0
    summary = {
        "status": "PASS" if not (producer_errors or verifier_errors) else "FAIL",
        "iterations": len(fields_list),
        "producer_seconds": round(producer_elapsed, 6),
        "verifier_seconds": round(verifier_elapsed, 6),
        "ratio_producer_over_verifier": round(ratio, 3),
        "verified_roots": verified,
        "note": "Internal microbenchmark only. Not an EVM gas or LLVM/C/Rust "
                "performance claim.",
    }
    if args.report:
        Path(args.report).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"report written: {args.report}")
    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if summary["status"] == "FAIL" else 0

    print("=" * 78)
    print("   LIN RECEIPT PRODUCER vs INDEPENDENT VERIFIER (microbenchmark)")
    print("=" * 78)
    print(f"  receipts       : {len(fields_list)}")
    print(f"  producer       : {producer_elapsed:.6f}s  ({producer_elapsed/max(len(fields_list),1)*1e6:.1f} us/op)")
    print(f"  verifier       : {verifier_elapsed:.6f}s  ({verifier_elapsed/max(verified,1)*1e6:.1f} us/op)")
    print(f"  ratio          : {ratio:.3f}x")
    print(f"  verified roots : {verified}/{len(fields_list)}")
    if producer_errors or verifier_errors:
        print("\nRESULT: FAIL")
        for e in producer_errors + verifier_errors:
            print(f"  - {e}")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
