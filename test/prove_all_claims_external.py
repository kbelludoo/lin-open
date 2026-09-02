#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN external, zero-trust, rationalist proof harness.

This script is deliberately conservative. It only reports a claim as PASS when
an independent observer can redo the check without trusting the LIN project's
advertising. Every claim carries an explicit status:

    PASS  - independently verified in this run (and reproducible by an auditor)
    SKIP  - the claim is legitimate but cannot be exercised on this host here
    FAIL  - the claim is false or contradicted by the observable artifact
    NOT-PROVEN - a claim that was made elsewhere but is NOT asserted by this
                 harness because the necessary execution path is unavailable

What it does NOT do:
  * It does not claim that LIN "saves $1.8 trillion" or that it is faster than
    LLVM/C/Rust for general computation. The pinned Uniswap/OpenSSL files are
    used for provenance and for the arithmetic/math oracle only.
  * It does not pretend that the Compiler-0 host can execute integer division
    or shifts in this environment. Those operations are explicitly rejected by
    the audited `lin_c0` front-end (VM_REJ_INT_DIVISION / VM_REJ_PARSE).

Usage:
    python3 test/prove_all_claims_external.py            # 10,000 math vectors
    python3 test/prove_all_claims_external.py --iterations 1000
    python3 test/prove_all_claims_external.py --fetch    # re-download upstream
    python3 test/prove_all_claims_external.py --require-all

Dependencies: Python 3.10+, a `cc`/`gcc` toolchain, no Zig required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
MANIFEST = FIX / "manifest.json"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
XREC = ROOT / "transpile" / "c" / "bin" / "lin_c_receipt"
VERIFY_RECEIPT = ROOT / "benchmarks" / "verify_receipt.py"
SQ_RECEIPT = ROOT / "benchmarks" / "fixtures" / "receipt_sqr9.json"

UNISWAP_LIN = ROOT / "src" / "lin_uniswap_v2_library.lin"
QOI_LIN = ROOT / "src" / "lin_siphash_xxhash_qoi.lin"
TINYEXPR_LIN = ROOT / "src" / "lin_tinyexpr_stage1.lin"
QOI_PURE_LIN = FIX / "qoi_hash_pure.lin"


class Claim:
    def __init__(self, ident: str, description: str, status: str, note: str = ""):
        self.ident = ident
        self.description = description
        self.status = status
        self.note = note

    def line(self) -> str:
        s = f"  {self.id_and_status()} {self.ident:12s}  {self.description}"
        if self.note:
            s += f"\n            note: {self.note}"
        return s

    def id_and_status(self) -> str:
        return {
            "PASS": "[PASS]",
            "SKIP": "[SKIP]",
            "FAIL": "[FAIL]",
            "NOT-PROVEN": "[NOT-PROVEN]",
        }.get(self.status, f"[{self.status}]")


def check_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "lin-independent-audit"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        meta = json.load(resp)
    return base64_decode(meta["content"])


def base64_decode(content: str) -> bytes:
    import base64
    return base64.b64decode(content)


def run(*argv: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        [str(a) for a in argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def steps_of(stdout: str) -> int | None:
    m = re.search(r"\bsteps=(\d+)\b", stdout)
    return int(m.group(1)) if m else None


def qoi_python(r: int, g: int, b: int, a: int) -> int:
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


_MASK64 = (1 << 64) - 1


def _u64(x: int) -> int:
    return x & _MASK64


def _s64(x: int) -> int:
    x &= _MASK64
    return x - (1 << 64) if x >= (1 << 63) else x


def _rotl64(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK64


def uniswap_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    """Official UniswapV2Library.getAmountOut integer math (independent Python)."""
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    amount_in_with_fee = amount_in * 997
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 1000 + amount_in_with_fee
    if denominator <= 0:
        return 0
    return numerator // denominator


def uniswap_quote(amount_a: int, reserve_a: int, reserve_b: int) -> int:
    if amount_a <= 0 or reserve_a <= 0 or reserve_b <= 0:
        return 0
    return (amount_a * reserve_b) // reserve_a


def siphash_round_py(v0: int, v1: int, v2: int, v3: int) -> int:
    v0 = _s64(_u64(v0) + _u64(v1))
    v1 = _s64(_rotl64(_u64(v1), 13) ^ _u64(v0))
    v0 = _s64(_rotl64(_u64(v0), 32))
    v2 = _s64(_u64(v2) + _u64(v3))
    v3 = _s64(_rotl64(_u64(v3), 16) ^ _u64(v2))
    v0 = _s64(_u64(v0) + _u64(v3))
    v3 = _s64(_rotl64(_u64(v3), 21) ^ _u64(v0))
    v2 = _s64(_u64(v2) + _u64(v1))
    v1 = _s64(_rotl64(_u64(v1), 17) ^ _u64(v2))
    v2 = _s64(_rotl64(_u64(v2), 32))
    return _s64(_u64(v0) ^ _u64(v1) ^ _u64(v2) ^ _u64(v3))


def xxhash64_round_py(acc: int, inp: int) -> int:
    p1 = _s64(-7046029254386353131)
    p2 = _s64(-4417276706815106179)
    total = (_u64(acc) + _u64(inp) * _u64(p2)) & _MASK64
    rotated = ((total << 31) | (total >> 33)) & _MASK64
    return _s64(rotated * _u64(p1))


def receipt_root_from_parts(expr: str, env: str, result: int, steps: int, sp: int,
                            code_sha: str) -> str:
    def leaf(domain: str, data: bytes) -> bytes:
        return hashlib.sha256(domain.encode("utf-8") + data).digest()

    def node(left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(b"node:" + left + right).digest()

    ls = leaf("lin:xver:source:", expr.encode("utf-8"))
    le = leaf("lin:xver:env:", env.encode("utf-8"))
    lc = bytes.fromhex(code_sha)
    lx = leaf("lin:xver:exec:", f"{result}:{steps}:{sp}".encode("utf-8"))
    return node(node(ls, le), node(lc, lx)).hex()


def parse_receipt_output(out: str) -> dict:
    def grab(name: str) -> str:
        m = re.search(rf"\b{name}=(?:\"([^\"]*)\"|([^\s]+))", out)
        if not m:
            raise RuntimeError(f"missing field {name} in receipt output")
        return (m.group(1) or m.group(2)).strip()

    return {
        "expr": grab("expr"),
        "env": grab("env"),
        "result": int(grab("result")),
        "steps": int(grab("steps")),
        "sp_at_ret": int(grab("sp_at_ret")),
        "code_sha256": grab("code_sha256"),
        "root": grab("root").replace("sha256:", ""),
    }


def provenance_claims(manifest: dict, use_fetch: bool) -> tuple[str, str]:
    """Return (status, note) for upstream downloads/pins."""
    failures = []
    checked = 0
    for name in sorted(manifest["sources"]):
        src = manifest["sources"][name]
        local = FIX / name
        if use_fetch:
            try:
                data = check_fetch(src["api_url"])
            except Exception as exc:  # network problem: fall back to the pin
                data = local.read_bytes()
                failures.append(f"{name}: fetch failed ({exc}); used local pin")
        else:
            data = local.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        ok_bytes = len(data) == src["bytes"]
        ok_digest = digest == src["file_sha256"]
        checked += 1
        if not (ok_bytes and ok_digest):
            failures.append(
                f"{name}: expected sha256:{src['file_sha256']} "
                f"({src['bytes']}B), got sha256:{digest} ({len(data)}B)"
            )
    if failures:
        return "FAIL", "; ".join(failures)
    if use_fetch:
        return "PASS", f"{checked} upstream files fetched from GitHub API and matched published SHA-256"
    return "PASS", f"{checked} pinned upstream files matched published SHA-256 (--fetch to re-download)"


def qoi_claims(iterations: int) -> tuple[str, str]:
    if not C0.exists():
        return "FAIL", f"{C0} missing; run `make -C transpile/c all`"

    rng = random.Random(20260902)
    mismatches = []
    vector_checks = 0

    for _ in range(iterations):
        r, g, b, a = [rng.randint(0, 255) for _ in range(4)]
        want = qoi_python(r, g, b, a)
        rc, out = run(C0, "vm", QOI_LIN, "qoi_color_hash", r, g, b, a)
        got = value_of(out)
        vector_checks += 1
        if rc != 0 or got != want:
            mismatches.append((r, g, b, a, want, got, rc, out))
            break

    if mismatches:
        r, g, b, a, want, got, rc, out = mismatches[0]
        return "FAIL", (
            f"first divergence on ({r},{g},{b},{a}): python={want}, lin={got}, "
            f"rc={rc}, out={out!r}"
        )

    # Round-trip / LINBC1 image route on a small deterministic matrix.
    rt_mismatch = []
    for (r, g, b, a) in [(0, 0, 0, 255), (255, 0, 0, 255), (0, 255, 0, 255),
                         (50, 60, 70, 80), (255, 255, 255, 255)]:
        want = qoi_python(r, g, b, a)
        rc, out = run(C0, "roundtrip", QOI_PURE_LIN, "qoi_hash", r, g, b, a)
        got = value_of(out)
        if rc != 0 or got != want:
            rt_mismatch.append((r, g, b, a, want, got, rc, out))
            break

    if rt_mismatch:
        r, g, b, a, want, got, rc, out = rt_mismatch[0]
        return "FAIL", (
            f"roundtrip divergence on ({r},{g},{b},{a}): python={want}, "
            f"lin-image={got}, rc={rc}, out={out!r}"
        )

    return "PASS", (
        f"qoi_color_hash: {vector_checks} random vectors exact vs qoi.h spec; "
        "5 round-trip/linbc1 vectors exact"
    )


def tinyexpr_claims() -> tuple[str, str]:
    # The LIN module is currently bounded to 20 unrolled steps (matching the
    # integer range used by the fail-closed sentinel for >20).
    mismatches = []
    for n in range(0, 21):
        want = 1 if n == 0 else __import__("math").factorial(n)
        rc, out = run(C0, "vm", TINYEXPR_LIN, "tinyexpr_fac", n)
        got = value_of(out)
        if rc != 0 or got != want:
            mismatches.append((n, want, got, rc, out))
            break

    if mismatches:
        n, want, got, rc, out = mismatches[0]
        return "FAIL", (
            f"tinyexpr_fac({n}): python={want}, lin={got}, rc={rc}, out={out!r}"
        )

    # Fail-closed sentinels (not upstream's NAN/INF representation, but the
    # deterministic LIN contract we are asserting here).
    for n, want in [(-1, -9002), (21, -9003), (100, -9003)]:
        rc, out = run(C0, "vm", TINYEXPR_LIN, "tinyexpr_fac", n)
        got = value_of(out)
        if rc != 0 or got != want:
            return "FAIL", f"tinyexpr_fac({n}): expected sentinel {want}, got {got}, rc={rc}"

    return "PASS", (
        "tinyexpr_fac(0..20) equals Python math.factorial; n<0 and n>20 fail closed"
    )


def uniswap_claims(iterations: int) -> tuple[str, str]:
    """Profile-full execution of the three pure UniswapV2Library math fns."""
    if not C0.exists():
        return "SKIP", "lin_c0 not built"

    rng = random.Random(20260903)
    mismatches = []
    checked = 0
    for _ in range(iterations):
        amount_in = rng.randint(1, 10**6)
        reserve_in = rng.randint(1, 10**9)
        reserve_out = rng.randint(1, 10**9)
        want_out = uniswap_amount_out(amount_in, reserve_in, reserve_out)
        rc, out = run(C0, "vmfull", UNISWAP_LIN, "get_amount_out",
                      amount_in, reserve_in, reserve_out)
        got = value_of(out)
        checked += 1
        if rc != 0 or got != want_out:
            mismatches.append(("get_amount_out", amount_in, reserve_in, reserve_out,
                               want_out, got, rc, out))
            break

    # Fixed canonical vector and quote/get_amount_in round-trip.
    for (name, args, want) in [
        ("get_amount_out", [10000, 50000, 100000], uniswap_amount_out(10000, 50000, 100000)),
        ("quote", [100, 50, 100], uniswap_quote(100, 50, 100)),
        ("get_amount_in", [16624, 50000, 100000], 10000),
    ]:
        rc, out = run(C0, "vmfull", UNISWAP_LIN, name, *args)
        got = value_of(out)
        checked += 1
        if rc != 0 or got != want:
            mismatches.append((name, *args, want, got, rc, out))
            break

    if mismatches:
        name, *rest = mismatches[0]
        want, got, rc, out = rest[-4:]
        return "FAIL", f"{name} divergence: python={want}, lin={got}, rc={rc}, out={out!r}"

    return "PASS", (
        f"UniswapV2Library scalar math (get_amount_out/quote/get_amount_in) "
        f"matches Python oracle over {checked} vectors via profile-full vmfull; "
        f"canonical vector = 16624"
    )


def hashing_claims(iterations: int) -> tuple[str, str]:
    if not C0.exists():
        return "SKIP", "lin_c0 not built"

    rng = random.Random(20260904)
    mismatches = []
    checked = 0
    for _ in range(iterations):
        args = [rng.randint(-(2**62), 2**62) for _ in range(4)]
        want = siphash_round_py(*args)
        rc, out = run(C0, "vmfull", QOI_LIN, "siphash_round", *args)
        got = value_of(out)
        checked += 1
        if rc != 0 or got != want:
            mismatches.append(("siphash_round", *args, want, got, rc, out))
            break
        a = rng.randint(-(2**62), 2**62)
        inp = rng.randint(-(2**62), 2**62)
        want = xxhash64_round_py(a, inp)
        rc, out = run(C0, "vmfull", QOI_LIN, "xxhash64_round", a, inp)
        got = value_of(out)
        checked += 1
        if rc != 0 or got != want:
            mismatches.append(("xxhash64_round", a, inp, want, got, rc, out))
            break

    if mismatches:
        name, *rest = mismatches[0]
        want, got, rc, out = rest[-4:]
        return "FAIL", f"{name} divergence: oracle={want}, lin={got}, rc={rc}, out={out!r}"

    return "PASS", (
        f"SipHash-2-4 and xxHash64 round parity vs independent Python oracle "
        f"over {checked} vectors via profile-full vmfull"
    )


def receipt_claims() -> tuple[str, str]:
    if not XREC.exists():
        return "FAIL", f"{XREC} missing; run `make -C transpile/c all`"

    rc, out = run(XREC, "--expr", "x * x", "--env", "x=9")
    if rc != 0:
        return "FAIL", f"lin_c_receipt rejected expression:\n{out}"
    fields = parse_receipt_output(out)
    computed = receipt_root_from_parts(
        fields["expr"], fields["env"], fields["result"],
        fields["steps"], fields["sp_at_ret"], fields["code_sha256"],
    )
    if computed != fields["root"]:
        return "FAIL", (
            f"embedded root {fields['root']} != independently recomputed root "
            f"{computed} (expr={fields['expr']!r}, env={fields['env']!r})"
        )

    rc, _ = run("python3", VERIFY_RECEIPT, SQ_RECEIPT)
    if rc != 0:
        return "FAIL", "committed square receipt did not independently verify"

    # Tamper the output by +1; independent verification must reject it.
    with open(SQ_RECEIPT, "r", encoding="utf-8") as f:
        txt = f.read()
    tampered = txt.replace('"output": "81"', '"output": "82"')
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False
    ) as tmp:
        tmp.write(tampered)
        tmp_path = Path(tmp.name)
    rc, _ = run("python3", VERIFY_RECEIPT, tmp_path)
    tmp_path.unlink(missing_ok=True)
    if rc == 0:
        return "FAIL", "tampered (+1 output) receipt was accepted; verifier bug"

    return "PASS", (
        f"x*x receipt root {fields['root']} independently recomputed by Python; "
        "committed receipt verifies; output+1 tamper is rejected"
    )


def selfhost_claims() -> tuple[str, str]:
    if not C0.exists():
        return "SKIP", "lin_c0 not built"
    rc1, out1 = run("bash", ROOT / "test" / "verify_c0.sh", C0)
    if rc1 != 0:
        return "FAIL", f"verify_c0.sh failed (rc={rc1}):\n{out1}"
    rc2, out2 = run("bash", ROOT / "test" / "verify_c0_selfhost.sh")
    if rc2 != 0:
        return "FAIL", f"verify_c0_selfhost.sh failed (rc={rc2}):\n{out2}"
    return "PASS", "verify_c0.sh (16 checks) and verify_c0_selfhost.sh (30 checks) pass with no Zig"


def not_proven_scope() -> str:
    """Honest limits that the harness explicitly does not claim."""
    # Ensure the default fail-closed path still rejects division; the
    # experiment must not silently change the default profile.
    rc, out = run(C0, "info", UNISWAP_LIN)
    if rc != 0:
        return "FAIL", f"lin_c0 info failed on Uniswap module:\n{out}"
    m = re.search(r"\.coverage\{ total=(\d+) eligible=(\d+) rejected=(\d+) \}", out)
    if not m:
        return "FAIL", f"cannot parse info output:\n{out}"
    total, eligible, rejected = (int(x) for x in m.groups())
    reasons = [x for x in re.findall(r"reason=\"([A-Z0-9_]+)\"", out)]
    if eligible != 0 or rejected != total or "VM_REJ_INT_DIVISION" not in reasons:
        return "FAIL", (
            f"expected the default C0 host to reject all Uniswap functions with "
            f"VM_REJ_INT_DIVISION (eligible=0), got total={total} eligible={eligible} "
            f"rejected={rejected} reasons={reasons}"
        )
    return "NOT-PROVEN", (
        "Scope limits: the proof executes the three pure UniswapV2Library math "
        "functions and the SipHash/xxHash round kernels on the experimental "
        "profile-full host. It does NOT prove full protocol security, full "
        "OpenSSL execution, on-chain gas savings, or performance vs LLVM/"
        "C/Rust. Those are not measured here and must not be sold as proven."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iterations", type=int, default=10000,
                    help="random QOI vectors to test (default 10000)")
    ap.add_argument("--fetch", action="store_true",
                    help="re-download upstream files from the GitHub API")
    ap.add_argument("--require-all", action="store_true",
                    help="fail if any SKIP/NOT-PROVEN claim exists")
    args = ap.parse_args()

    if args.iterations < 1:
        ap.error("--iterations must be >= 1")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    claims = []
    claims.append(Claim("C1", "Upstream source provenance", *provenance_claims(manifest, args.fetch)))
    claims.append(Claim("C2", "QOI index-hash parity (qoi.h -> LIN -> C0)", *qoi_claims(args.iterations)))
    claims.append(Claim("C3", "TinyExpr factorial parity (0..20, fail-closed edges)", *tinyexpr_claims()))
    claims.append(Claim("C4", "Compute receipt root independently recomputed", *receipt_claims()))
    claims.append(Claim("C5", "Compiler-0 no-Zig self-host gates", *selfhost_claims()))
    claims.append(Claim("C6", "UniswapV2Library scalar math parity (profile-full)", *uniswap_claims(args.iterations)))
    claims.append(Claim("C7", "SipHash/xxHash round parity (profile-full)", *hashing_claims(args.iterations)))
    np_status, np_note = not_proven_scope()
    claims.append(Claim("NP1", "Full protocol/security/performance proof", np_status, np_note))

    print("=" * 78)
    print("   LIN RATIONALIST EXTERNAL PROOF   (only observable claims)")
    print("=" * 78)
    for c in claims:
        print(c.line())

    failures = [c for c in claims if c.status == "FAIL"]
    hard = [c for c in claims if c.status in ("SKIP", "NOT-PROVEN") and args.require_all]

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} false claim(s))")
        for c in failures:
            print(f"  - {c.ident}: {c.description}")
        return 1
    if hard:
        print("RESULT: FAIL (--require-all requested, but unproven claims remain)")
        for c in hard:
            print(f"  - {c.ident}: {c.status} — {c.note}")
        return 1
    print(f"RESULT: PASS ({len([c for c in claims if c.status == 'PASS'])} PASS, "
          f"{len([c for c in claims if c.status != 'PASS'])} non-PASS/non-FAIL claims)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
