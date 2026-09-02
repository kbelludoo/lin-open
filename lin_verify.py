#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lin-verify — standalone, zero-trust CLI for LIN receipts and module proofs.

Uses only the Python standard library. It deliberately does not depend on the
LIN compiler/runtime for *receipt verification*: the SHA-256 Merkle root is
recomputed from public fields, so an auditor can validate a receipt on any
machine with Python 3.

Commands:
  lin_verify receipt <file> [--source "..."]      verify a LIN receipt.
  lin_verify provenance [--fetch]                 check pinned GitHub upstream digests.
  lin_verify module <file.lin> <fn> [args...]     run a LIN module via lin_c0 (needs C0 built).
  lin_verify module-full <file.lin> <fn> [...]    run via the experimental profile-full host.
  lin_verify selfhost                             run the no-Zig Compiler-0 gates.
  lin_verify all [--iterations N] [--fetch]       run the complete rationalist proof.
  lin_verify fuzz [--iterations N]                run the differential fuzz harness.
  lin_verify benchmark [--iterations N]           run the audit-cost microbenchmark.

Example:
  python3 lin_verify.py receipt benchmarks/fixtures/receipt_sqr9.json
  python3 lin_verify.py provenance --fetch
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
MANIFEST = FIX / "manifest.json"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"

SCHEMA = "LIN_COMPUTE_RECEIPT_1.0"
FIELD_NAMES = {"artifact", "input", "output", "steps", "sp_at_ret", "merkle_root"}


class LinVerifyError(ValueError):
    pass


def strip_sha256(s: str) -> str:
    return s[7:] if s.startswith("sha256:") else s


def parse_json(txt: str) -> dict:
    data = json.loads(txt)
    if not isinstance(data, dict):
        raise LinVerifyError("JSON root must be an object")
    missing = sorted(FIELD_NAMES - set(data))
    if missing:
        raise LinVerifyError(f"missing field(s): {', '.join(missing)}")
    try:
        return {
            "artifact": str(data["artifact"]),
            "input": str(data["input"]),
            "output": str(data["output"]),
            "steps": int(data["steps"]),
            "sp_at_ret": int(data["sp_at_ret"]),
            "merkle_root": str(data["merkle_root"]),
        }
    except (TypeError, ValueError) as e:
        raise LinVerifyError(f"field type error: {e}")


def parse_rulel(txt: str) -> dict:
    def val(tag: str):
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith(tag):
                return line[len(tag):].strip().strip('"')
        return None

    a, i, o, s, p, m = val(".a="), val(".i="), val(".o="), val(".s="), val(".p="), val(".m=")
    if None in (a, i, o, s, p, m):
        raise LinVerifyError("missing RULEL field(s) (.a/.i/.o/.s/.p/.m)")
    try:
        return {"artifact": a, "input": i, "output": o,
                "steps": int(s), "sp_at_ret": int(p), "merkle_root": m}
    except ValueError as e:
        raise LinVerifyError(f"field type error: {e}")


def build_leaf(fields: dict) -> bytes:
    art = bytes.fromhex(strip_sha256(fields["artifact"]))
    if len(art) != 32:
        raise LinVerifyError("artifact must be 32 bytes")
    output = int(fields["output"])
    steps = int(fields["steps"])
    sp = int(fields["sp_at_ret"])
    inp = int(fields["input"])
    if not -(2 ** 63) <= output < 2 ** 63:
        raise LinVerifyError("output out of i64 range")
    if not 0 <= steps < 2 ** 64:
        raise LinVerifyError("steps out of u64 range")
    if not 0 <= sp < 2 ** 64:
        raise LinVerifyError("sp_at_ret out of u64 range")
    if not -(2 ** 63) <= inp < 2 ** 63:
        raise LinVerifyError("input out of i64 range")
    leaf = bytearray(64)
    leaf[0:32] = art
    struct.pack_into("<q", leaf, 32, output)
    struct.pack_into("<Q", leaf, 40, steps)
    struct.pack_into("<Q", leaf, 48, sp)
    struct.pack_into("<q", leaf, 56, inp)
    return bytes(leaf)


def fetch_api(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "lin-verify"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        meta = json.load(resp)
    return base64.b64decode(meta["content"])


def cmd_receipt(args: argparse.Namespace) -> int:
    path = Path(args.receipt)
    txt = path.read_text(encoding="utf-8")
    fields = parse_json(txt) if txt.lstrip().startswith("{") else parse_rulel(txt)
    claimed = strip_sha256(fields["merkle_root"])
    computed = hashlib.sha256(build_leaf(fields)).hexdigest()
    artifact_ok = True
    if args.source is not None:
        artifact_ok = hashlib.sha256(args.source.encode("utf-8")).hexdigest() == strip_sha256(fields["artifact"])
    else:
        print("source   : not provided")
    ok = computed == claimed and artifact_ok
    print(f"artifact : sha256:{strip_sha256(fields['artifact'])}")
    print(f"input    : {fields['input']}")
    print(f"output   : {fields['output']}")
    print(f"steps    : {fields['steps']}")
    print(f"sp_at_ret: {fields['sp_at_ret']}")
    print(f"claimed  : sha256:{claimed}")
    print(f"computed : sha256:{computed}")
    if args.source is not None:
        print("source   : " + ("PASS" if artifact_ok else "FAIL"))
    print("RESULT   : " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_provenance(args: argparse.Namespace) -> int:
    if not MANIFEST.exists():
        print(f"[FAIL] manifest not found: {MANIFEST}", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = []
    checked = 0
    for name in sorted(manifest["sources"]):
        src = manifest["sources"][name]
        local = FIX / name
        if args.fetch:
            try:
                data = fetch_api(src["api_url"])
            except Exception as exc:
                print(f"  WARN fetch {name}: {exc} (using local pin)")
                data = local.read_bytes()
        else:
            data = local.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        ok = len(data) == src["bytes"] and digest == src["file_sha256"]
        checked += 1
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: sha256:{digest} ({len(data)}B)")
        if not ok:
            failures.append(name)
    if failures:
        print(f"RESULT: FAIL ({', '.join(failures)})")
        return 1
    print(f"RESULT: PASS ({checked} upstream files matched)")
    return 0


def cmd_module(args: argparse.Namespace) -> int:
    if not C0.exists():
        print(f"[FAIL] {C0} not found. Build it with `make -C transpile/c all`.", file=sys.stderr)
        return 2
    mode = "vmfull" if args.full else "vm"
    proc = subprocess.run([str(C0), mode, args.module, args.fn, *map(str, args.args)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(proc.stdout.strip())
    return proc.returncode


def cmd_selfhost(_args: argparse.Namespace) -> int:
    if not C0.exists():
        print(f"[FAIL] {C0} not found. Build it with `make -C transpile/c all`.", file=sys.stderr)
        return 2
    for label, script, cmd in [
        ("verify_c0.sh", ROOT / "test" / "verify_c0.sh", [C0]),
        ("verify_c0_selfhost.sh", ROOT / "test" / "verify_c0_selfhost.sh", []),
    ]:
        proc = subprocess.run(["bash", str(script), *map(str, cmd)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            print(f"[FAIL] {label}:\n{proc.stdout}")
            return proc.returncode
        print(f"[PASS] {label}")
    print("RESULT: PASS (no-Zig self-host gates)")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    return subprocess.run([
        sys.executable, str(ROOT / "test" / "prove_all_claims_external.py"),
        "--iterations", str(args.iterations),
    ] + (["--fetch"] if args.fetch else [])).returncode


def cmd_fuzz(args: argparse.Namespace) -> int:
    return subprocess.run([
        sys.executable, str(ROOT / "test" / "fuzz_differential.py"),
        "--iterations", str(args.iterations),
        "--categories", args.categories,
    ]).returncode


def cmd_benchmark(args: argparse.Namespace) -> int:
    return subprocess.run([
        sys.executable, str(ROOT / "test" / "benchmark_audit_cost.py"),
        "--iterations", str(args.iterations),
    ]).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Standalone LIN verifier CLI")
    sub = ap.add_subparsers(dest="command", required=True)
    p_r = sub.add_parser("receipt", help="verify a compute receipt")
    p_r.add_argument("receipt")
    p_r.add_argument("--source", default=None)
    p_r.set_defaults(func=cmd_receipt)

    p_p = sub.add_parser("provenance", help="check pinned upstream GitHub digests")
    p_p.add_argument("--fetch", action="store_true")
    p_p.set_defaults(func=cmd_provenance)

    p_m = sub.add_parser("module", help="run a LIN module through lin_c0")
    p_m.add_argument("module")
    p_m.add_argument("fn")
    p_m.add_argument("args", nargs="*", type=int, default=[])
    p_m.set_defaults(func=cmd_module, full=False)

    p_mf = sub.add_parser("module-full",
                          help="run a LIN module through the experimental profile-full lin_c0")
    p_mf.add_argument("module")
    p_mf.add_argument("fn")
    p_mf.add_argument("args", nargs="*", type=int, default=[])
    p_mf.set_defaults(func=cmd_module, full=True)

    p_s = sub.add_parser("selfhost", help="run the no-Zig self-host gates")
    p_s.set_defaults(func=cmd_selfhost)

    p_a = sub.add_parser("all", help="run the full rationalist proof")
    p_a.add_argument("--iterations", type=int, default=10000)
    p_a.add_argument("--fetch", action="store_true")
    p_a.set_defaults(func=cmd_all)

    p_f = sub.add_parser("fuzz", help="run the differential fuzz harness")
    p_f.add_argument("--iterations", type=int, default=10000)
    p_f.add_argument("--categories", default="qoi,uniswap,hash,tinyexpr")
    p_f.set_defaults(func=cmd_fuzz)

    p_b = sub.add_parser("benchmark", help="run the audit-cost microbenchmark")
    p_b.add_argument("--iterations", type=int, default=1000)
    p_b.set_defaults(func=cmd_benchmark)

    args = ap.parse_args()
    try:
        return args.func(args)
    except (LinVerifyError, OSError, ValueError) as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
