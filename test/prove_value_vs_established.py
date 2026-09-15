#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN value gate vs established languages (gcc C11 + CPython).

Contest (honest): bit-exact numeric kernels + independent receipt.
Not the contest: replace C/Rust/Python/Solidity as a general language.

    python3 test/prove_value_vs_established.py
    make value-proof

Exit 0 = L0-L3 PASS, NP/L4 printed. Exit 1 = a win condition failed.
L4 is never auto-PASS. make value-proof does not substitute live pin-fetch or L4.
"""

from __future__ import annotations

import math
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "test" / "value_gate"))
from ladder import C4_ROOT, cut_overclaims, l1_pin, l3_frontend  # noqa: E402
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
BC1 = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
XREC = ROOT / "transpile" / "c" / "bin" / "lin_c_receipt"
ORACLE_C = ROOT / "test" / "value_gate" / "oracle_c11.c"
QOI_LIN = ROOT / "src" / "lin_siphash_xxhash_qoi.lin"
TINY_LIN = ROOT / "src" / "lin_tinyexpr_stage1.lin"
UNI_LIN = ROOT / "src" / "lin_uniswap_v2_library.lin"
U256_BC1 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.linbc"
SQ_RECEIPT = ROOT / "benchmarks" / "fixtures" / "receipt_sqr9.json"
VERIFY_RECEIPT = ROOT / "benchmarks" / "verify_receipt.py"
U256_MAX = (1 << 256) - 1


class Row:
    def __init__(self, ident: str, title: str, status: str, note: str = ""):
        self.ident = ident
        self.title = title
        self.status = status
        self.note = note

    def line(self) -> str:
        tag = f"[{self.status}]"
        s = f"  {tag:14s} {self.ident:4s}  {self.title}"
        if self.note:
            s += f"\n                 {self.note}"
        return s


def run(argv: list, timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(
        [str(a) for a in argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return p.returncode, p.stdout.strip()


def lin_value(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    if m:
        return int(m.group(1))
    m = re.search(r"\bresult=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def ensure_host() -> str | None:
    if C0.exists() and BC1.exists() and XREC.exists():
        return None
    rc, out = run(["make", "-C", str(ROOT / "transpile" / "c"), "all"], timeout=180)
    if rc != 0 or not C0.exists():
        return f"lin_c0 missing after make -C transpile/c all (rc={rc}): {out[-800:]}"
    return None


def build_c_oracle(bin_path: Path) -> str | None:
    rc, out = run(["cc", "-std=c11", "-O0", "-Wall", "-Wextra", "-o", str(bin_path), str(ORACLE_C)])
    if rc != 0:
        return f"cc failed: {out}"
    return None


def c_oracle(bin_path: Path, *args: object) -> int:
    rc, out = run([str(bin_path), *[str(a) for a in args]])
    if rc != 0:
        raise RuntimeError(f"oracle_c11 rc={rc}: {out}")
    return int(out.splitlines()[-1])


def py_qoi(r: int, g: int, b: int, a: int) -> int:
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


def py_fac(n: int) -> int:
    if n < 0:
        return -9002
    if n > 20:
        return -9003
    return math.factorial(n)


def py_amount_out(ain: int, rin: int, rout: int) -> int:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return 0
    in_fee = ain * 997
    return (in_fee * rout) // (rin * 1000 + in_fee)


def u256_oracle(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    in_fee = ain * 997
    num = in_fee * rout
    den = rin * 1000 + in_fee
    if in_fee > U256_MAX or num > U256_MAX or den > U256_MAX:
        return -2, 0
    return 1, num // den


def to_signed_words(x: int) -> list[str]:
    out = []
    for _ in range(4):
        w = x & 0xFFFFFFFFFFFFFFFF
        if w >= (1 << 63):
            w -= 1 << 64
        out.append(str(w))
        x >>= 64
    return out


def lin_u256(ain: int, rin: int, rout: int) -> tuple[int, int]:
    base = to_signed_words(ain) + to_signed_words(rin) + to_signed_words(rout)
    rc, out = run([str(BC1), str(U256_BC1), "settle_u256_word", *base, "-1"])
    if rc != 0:
        raise RuntimeError(f"lin_bc1_run status failed: {out}")
    status = lin_value(out)
    if status is None:
        raise RuntimeError(f"no status in {out!r}")
    if status < 0:
        return status, 0
    words = []
    for idx in range(4):
        rc, out = run([str(BC1), str(U256_BC1), "settle_u256_word", *base, str(idx)])
        if rc != 0:
            raise RuntimeError(f"lin_bc1_run word {idx} failed: {out}")
        val = lin_value(out)
        if val is None:
            raise RuntimeError(f"no word in {out!r}")
        words.append(val & 0xFFFFFFFFFFFFFFFF)
    return status, words[0] | (words[1] << 64) | (words[2] << 128) | (words[3] << 192)


def w1_nversion(cbin: Path) -> tuple[str, str]:
    rng = random.Random(20260915)
    n_qoi = 64
    for _ in range(n_qoi):
        r, g, b, a = [rng.randint(0, 255) for _ in range(4)]
        want = py_qoi(r, g, b, a)
        got_c = c_oracle(cbin, "qoi", r, g, b, a)
        rc, out = run([str(C0), "vm", str(QOI_LIN), "qoi_color_hash", str(r), str(g), str(b), str(a)])
        got_l = lin_value(out)
        if rc != 0 or got_c != want or got_l != want:
            return "FAIL", f"qoi ({r},{g},{b},{a}): py={want} c={got_c} lin={got_l} rc={rc}"
    for n in list(range(0, 21)) + [-1, 21]:
        want = py_fac(n)
        got_c = c_oracle(cbin, "fac", n)
        rc, out = run([str(C0), "vm", str(TINY_LIN), "tinyexpr_fac", str(n)])
        got_l = lin_value(out)
        if rc != 0 or got_c != want or got_l != want:
            return "FAIL", f"fac n={n}: py={want} c={got_c} lin={got_l} rc={rc}"
    vectors = [(10000, 50000, 100000), (2, 100, 100), (1000, 10000, 20000)]
    for _ in range(32):
        vectors.append((rng.randint(1, 10_000), rng.randint(1, 100_000), rng.randint(1, 100_000)))
    for ain, rin, rout in vectors:
        want = py_amount_out(ain, rin, rout)
        got_c = c_oracle(cbin, "amount_out", ain, rin, rout)
        rc, out = run(
            [str(C0), "vm", str(UNI_LIN), "get_amount_out", str(ain), str(rin), str(rout)]
        )
        got_l = lin_value(out)
        if rc != 0 or got_c != want or got_l != want:
            return "FAIL", (
                f"amount_out({ain},{rin},{rout}): py={want} c={got_c} lin={got_l} rc={rc}"
            )
    if py_amount_out(10000, 50000, 100000) != 16624:
        return "FAIL", "canonical Uniswap vector is not 16624 in the Python oracle"
    return "PASS", (
        f"V1 16624 empate (does not win). gcc-C11 == CPython == lin_c0 on "
        f"{n_qoi} QOI + fac 0..20/edges + {len(vectors)} get_amount_out i64 "
        "(TOY_INT64 domain, not mainnet uint256)"
    )


def w2_receipt() -> tuple[str, str]:
    rc, out = run([str(XREC), "--expr", "x * x", "--env", "x=9"])
    if rc != 0:
        return "FAIL", f"lin_c_receipt failed: {out}"
    m = re.search(r'root="sha256:([0-9a-f]+)"', out)
    if not m or m.group(1) != C4_ROOT:
        return "FAIL", f"V2 root mismatch: {out}"
    rc, _ = run(["python3", str(VERIFY_RECEIPT), str(SQ_RECEIPT)])
    if rc != 0:
        return "FAIL", "committed receipt_sqr9.json did not verify with hashlib"
    txt = SQ_RECEIPT.read_text(encoding="utf-8")
    tampered = txt.replace('"output": "81"', '"output": "82"')
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
        tmp.write(tampered)
        path = Path(tmp.name)
    rc, _ = run(["python3", str(VERIFY_RECEIPT), str(path)])
    path.unlink(missing_ok=True)
    if rc == 0:
        return "FAIL", "tampered output+1 receipt was accepted"
    return "PASS", (
        f"V2 sha256:{C4_ROOT[:8]}... output+1 rejected. "
        "Tamper-evidence, not zk/computational soundness."
    )


def w3_u256() -> tuple[str, str]:
    if not BC1.exists() or not U256_BC1.exists():
        return "FAIL", "lin_bc1_run or u256_settlement_engine.linbc missing"
    golden = [
        (10000, 50000, 100000, 16624),
        (10**18, 5 * 10**18, 10 * 10**18, 1662497915624478906),
        (0, 100, 100, 0),
    ]
    checked = 0
    for ain, rin, rout, expected_out in golden:
        exp_st, exp_val = u256_oracle(ain, rin, rout)
        got_st, got_val = lin_u256(ain, rin, rout)
        if ain == 0:
            if got_st != -1 or exp_st != -1:
                return "FAIL", f"zero input must fail-closed, got status={got_st}"
        elif got_st != exp_st or got_val != exp_val or (expected_out and got_val != expected_out):
            return "FAIL", (
                f"u256 ({ain},{rin},{rout}): py=({exp_st},{exp_val}) "
                f"lin=({got_st},{got_val}) want_out={expected_out}"
            )
        checked += 1
    return "PASS", (
        f"{checked} u256 golden vectors bit-exact vs Python int "
        "(Solidity uint256 getAmountOut math; canonical 18-decimal out="
        "1662497915624478906)"
    )


def main() -> int:
    print("=" * 78)
    print("  LIN VALUE GATE  (empate + recibo = produto; NP obrigatorio)")
    print("  L0-L3 = laboratorio. L4 = mundo real. Este comando nao substitui L1-live/L4.")
    print("=" * 78)

    rows: list[Row] = []
    host_err = ensure_host()
    if host_err:
        rows.append(Row("L0", "V1 N-version gcc == Python == lin_c0", "FAIL", host_err))
        print(rows[0].line())
        print("\nRESULT: FAIL")
        return 1

    with tempfile.TemporaryDirectory() as td:
        cbin = Path(td) / "oracle_c11"
        cerr = build_c_oracle(cbin)
        if cerr:
            rows.append(Row("L0", "V1 N-version gcc == Python == lin_c0", "FAIL", cerr))
        else:
            rows.append(Row("L0", "V1 16624 empate gcc == Python == lin_c0", *w1_nversion(cbin)))

    rows.append(Row("L1", "V3 pin UniswapV2Library.sol sha256:4f83e933...", *l1_pin()))
    rows.append(Row("L2", "V2 a6d17453... output+1 rejected (not zk)", *w2_receipt()))
    rows.append(Row("L3", "sol_from_sol fail-closed REJ_* / VM_REJ_*", *l3_frontend(run)))
    rows.append(Row("CUT", "RSA 2^36 / LayerZero bounty / 1.17M-as-wall / volume-savings", *cut_overclaims()))
    rows.append(Row("W3", "u256 Uniswap math: LinVM == Python bigint", *w3_u256()))
    rows.append(Row(
        "L4",
        "Stranger publishes the same root AND CSV refused without receipt",
        "NOT-PROVEN",
        "Laboratory until both exist. make value-proof cannot mint L4.",
    ))
    rows.append(Row(
        "NP1",
        "LIN as a general-purpose language vs C/Rust/Python",
        "NOT-PROVEN",
        "Must stay printed. Omitting this makes a reviewer dump C1-C7 with the hype.",
    ))
    rows.append(Row(
        "U4",
        "Merkle receipts are zk / computationally sound",
        "NOT-PROVEN",
        "V2 is tamper-evidence. A lying executor can mint a valid root.",
    ))

    for r in rows:
        print(r.line())

    failures = [r for r in rows if r.status == "FAIL"]
    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} win-condition(s) broken)")
        return 1
    print("VERDICT: CONTINUE as an auditable coprocessor. L4 still laboratory.")
    print("RESULT: PASS L0-L3 + CUT; NOT-PROVEN L4/NP1/U4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
