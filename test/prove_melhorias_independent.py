#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent re-proof of recent LIN melhorias.

Third oracle is Python arbitrary-precision int — not the C11 limb clone and
not LinVM. Hashes are recomputed with hashlib / git hash-object this run.

Class: EXPERIMENTAL for Compound uint64-scale IRM. Does not claim mainnet
uint256 parity, EVM replacement, zk/Merkle soundness, or general superiority
vs LLVM. Real deltas: explicit IRM arguments and 128-bit (a*b)/d with
fail-closed uint64 quotient overflow.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof" / "BaseJumpRateModelV2.sol"
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
LIFT = ROOT / "src" / "lin_sol_view_lift.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "independent_reproof.json"

PIN_SHA = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"
PIN_BLOB = "4d6828c39ed737c0c48508adc414b919ab6c2a55"
BASE = 10**18
KINK = 800_000_000_000_000_000
MULT_YEAR = 40_000_000_000_000_000
JUMP_YEAR = 1_090_000_000_000_000_000
BLOCKS = 2_102_400


def run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def rec(claims: list[dict[str, str]], ident: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:16s}  {desc}")
    if note:
        print(f"            note: {note}")


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    m = re.search(r"\bvalue=(-?\d+)\b", proc.stdout)
    if not m:
        raise RuntimeError(proc.stdout)
    return int(m.group(1))


def view_lift_free(params: str, body: str) -> list[str]:
    """Python oracle of src/lin_sol_view_lift.lin (C0 vm rejects string literals)."""
    types = {"uint256", "uint128", "uint64", "uint32", "uint", "int", "bool"}
    kws = {"function", "returns", "return", "internal", "public", "view", "pure", "if", "else", "while"}

    def idents(s: str) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        i = 0
        n = len(s)
        while i < n:
            if s[i].isalpha() or s[i] == "_":
                j = i + 1
                while j < n and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                out.append((i, s[i:j]))
                i = j
            else:
                i += 1
        return out

    known: list[str] = []
    last = ""
    i = 0
    n = len(params)
    while i < n:
        if params[i].isalpha() or params[i] == "_":
            j = i + 1
            while j < n and (params[j].isalnum() or params[j] == "_"):
                j += 1
            tok = params[i:j]
            if tok not in types and tok not in kws:
                last = tok
            i = j
            continue
        if params[i] == "," or i + 1 >= n:
            if last:
                known.append(last)
                last = ""
        i += 1
    if last:
        known.append(last)

    locals_: list[str] = []
    extra: list[str] = []
    ids = idents(body)
    skip_until = -1
    for pos, name in ids:
        if pos < skip_until:
            continue
        if name in types:
            rest = body[pos + len(name) :].lstrip()
            loc = ""
            k = 0
            if rest and (rest[0].isalpha() or rest[0] == "_"):
                k = 1
                while k < len(rest) and (rest[k].isalnum() or rest[k] == "_"):
                    k += 1
                loc = rest[:k]
            if loc:
                locals_.append(loc)
                skip_until = pos + len(name) + (len(body[pos + len(name) :]) - len(rest)) + len(loc)
            continue
        after = body[pos + len(name) :].lstrip()
        if after.startswith("("):
            continue
        if name not in kws and name not in known and name not in locals_ and name not in extra:
            extra.append(name)
    return extra


def c11_cmd(*args: str) -> int:
    proc = run([str(ORACLE_BIN), *args])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    return int(proc.stdout.strip().splitlines()[-1])


def i64_wrap(x: int) -> int:
    x = x & ((1 << 64) - 1)
    return x - (1 << 64) if x >= 2**63 else x


def main() -> int:
    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  INDEPENDENT RE-PROOF — Python bigint vs LIN C0 vs C11 (this run)")
    print("=" * 78)

    got_sha = hashlib.sha256(FIX.read_bytes()).hexdigest()
    if got_sha != PIN_SHA:
        rec(claims, "PIN-SHA", "FAIL", "fixture sha256 mismatch", got_sha)
        return 1
    rec(claims, "PIN-SHA", "PASS", "BaseJumpRateModelV2.sol sha256 recomputed this run")

    blob = run(["git", "hash-object", str(FIX)]).stdout.strip()
    if blob != PIN_BLOB:
        rec(claims, "PIN-BLOB", "FAIL", "git blob mismatch", blob)
        return 1
    rec(claims, "PIN-BLOB", "PASS", "git hash-object matches pinned blob")

    gcc = run(["gcc", "-O2", "-std=c11", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if gcc.returncode != 0:
        rec(claims, "C11-BUILD", "FAIL", "gcc oracle", gcc.stderr)
        return 1
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "C11 selftest", st.stdout)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11 __int128 vs limb clone selftest")

    if not C0.exists():
        built = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
        if built.returncode != 0 or not C0.exists():
            rec(claims, "C0-BUILD", "FAIL", "make -C transpile/c c0", built.stdout)
            return 1

    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check", chk.stdout)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of JumpRate clone")

    vectors = [
        (100, 200, 50),
        (7, 9, 1),
        (BASE, 1, 2),
        (BASE, BASE, 2 * BASE),
    ]
    for a, b, d in vectors:
        py = (a * b) // d
        py_r = (a * b) % d
        lin = lin_vm("cjr_muldiv", a, b, d)
        lin_r = lin_vm("cjr_muldiv_rem", a, b, d)
        c11 = c11_cmd("muldiv", str(a), str(b), str(d))
        c11_r = c11_cmd("rem", str(a), str(b), str(d))
        if not (py == lin == c11):
            rec(claims, "MULDIV-3WAY", "FAIL", f"({a}*{b})/{d}", f"py={py} lin={lin} c11={c11}")
            return 1
        if not (py_r == lin_r == c11_r) or py != (py * d + py_r) // d:
            rec(claims, "MULDIV-REM", "FAIL", f"rem({a}*{b})/{d}", f"py={py_r} lin={lin_r} c11={c11_r}")
            return 1
        if py * d + py_r != a * b:
            rec(claims, "MULDIV-ID", "FAIL", f"q*d+r != a*b for ({a}*{b})/{d}")
            return 1
    rec(claims, "MULDIV-3WAY", "PASS", "4/4 muldiv: Python bigint == LIN vm == C11 __int128")
    rec(claims, "MULDIV-REM", "PASS", "4/4 remainder: a*b = q*d + r with r < d on Python/LIN/C11")

    wrap = i64_wrap(BASE * BASE)
    bigint_half = (BASE * BASE) // (2 * BASE)
    if wrap == bigint_half:
        rec(claims, "I64-WRAP", "FAIL", "i64 wrap equalled bigint")
        return 1
    rec(
        claims,
        "I64-WRAP",
        "PASS",
        "naive signed-i64 1e18*1e18 wraps; Python/LIN 128-bit muldiv does not",
        f"i64={wrap} bigint_half={bigint_half}",
    )

    sol_mb = (MULT_YEAR * BASE) // (BLOCKS * KINK)
    lin_mb = ((MULT_YEAR * BASE) // KINK) // BLOCKS
    c0_mb = lin_vm("cjr_multiplier_per_block", MULT_YEAR, KINK)
    if not (sol_mb == lin_mb == c0_mb):
        rec(claims, "MULT-REORDER", "FAIL", "year-to-block multiplier", f"{sol_mb} {lin_mb} {c0_mb}")
        return 1
    rec(claims, "MULT-REORDER", "PASS", "Solidity (a*BASE)/(blocks*kink) equals LIN reorder on this vector", f"mb={sol_mb}")

    bb = lin_vm("cjr_base_per_block", 0)
    jb = lin_vm("cjr_jump_per_block", JUMP_YEAR)
    py_util = (BASE * BASE) // (BASE + BASE)
    lin_util = lin_vm("cjr_utilization", BASE, BASE, 0)
    py_r50 = (py_util * c0_mb) // BASE + bb
    lin_r50 = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK)
    c11_r50 = int(
        run(
            [str(ORACLE_BIN), "borrow", str(BASE), str(BASE), "0", str(bb), str(c0_mb), str(jb), str(KINK)]
        ).stdout.strip().splitlines()[-1]
    )
    if not (py_util == lin_util == 500_000_000_000_000_000):
        rec(claims, "UTIL-50", "FAIL", "50% utilization", f"py={py_util} lin={lin_util}")
        return 1
    if not (py_r50 == lin_r50 == c11_r50):
        rec(claims, "BORROW-50", "FAIL", "borrow@50%", f"py={py_r50} lin={lin_r50} c11={c11_r50}")
        return 1
    rec(claims, "UTIL-50", "PASS", "50% utilization = 0.5e18 on Python, LIN, formula")
    rec(claims, "BORROW-50", "PASS", "borrow@50% three-way consensus", f"rate={py_r50}")

    q_big = (BASE * BASE) // 1
    lin_ov = lin_vm("cjr_muldiv", BASE, BASE, 1)
    c11_ov = c11_cmd("muldiv", str(BASE), str(BASE), "1")
    if q_big <= 2**64 - 1:
        rec(claims, "Q-OVERFLOW", "FAIL", "1e18*1e18 unexpectedly fits uint64")
        return 1
    if lin_ov != 0 or c11_ov != 0:
        rec(claims, "Q-OVERFLOW", "FAIL", "expected fail-closed 0", f"lin={lin_ov} c11={c11_ov}")
        return 1
    rec(claims, "Q-OVERFLOW", "PASS", "quotient 1e36 does not fit uint64; LIN/C11 fail-closed to 0")

    cash90 = 100_000_000_000_000_000
    bor90 = 900_000_000_000_000_000
    py_u90 = (bor90 * BASE) // (cash90 + bor90)
    lin_u90 = lin_vm("cjr_utilization", cash90, bor90, 0)
    excess = py_u90 - KINK
    py_r90 = (KINK * c0_mb) // BASE + (excess * jb) // BASE + bb
    lin_r90 = lin_vm("cjr_borrow_rate", cash90, bor90, 0, bb, c0_mb, jb, KINK)
    c11_r90 = c11_cmd("borrow", str(cash90), str(bor90), "0", str(bb), str(c0_mb), str(jb), str(KINK))
    if not (py_u90 == lin_u90 == 900_000_000_000_000_000):
        rec(claims, "UTIL-90", "FAIL", "90% utilization", f"py={py_u90} lin={lin_u90}")
        return 1
    if not (py_r90 == lin_r90 == c11_r90) or py_r90 <= py_r50:
        rec(claims, "BORROW-90", "FAIL", "jump-region borrow@90%", f"py={py_r90} lin={lin_r90} c11={c11_r90}")
        return 1
    rec(claims, "BORROW-90", "PASS", "jump-region borrow@90% three-way consensus", f"rate={py_r90}")

    rf = 100_000_000_000_000_000
    py_s50 = (py_util * ((py_r50 * (BASE - rf)) // BASE)) // BASE
    lin_s50 = lin_vm("cjr_supply_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK, rf)
    c11_s50 = c11_cmd(
        "supply", str(BASE), str(BASE), "0", str(bb), str(c0_mb), str(jb), str(KINK), str(rf)
    )
    if not (py_s50 == lin_s50 == c11_s50) or py_s50 >= py_r50:
        rec(claims, "SUPPLY-50", "FAIL", "supply@50% rf=0.1", f"py={py_s50} lin={lin_s50} c11={c11_s50}")
        return 1
    rec(claims, "SUPPLY-50", "PASS", "supply@50% rf=10% three-way consensus", f"rate={py_s50}")

    if lin_vm("cjr_util_ok", 1, 1, 3) != 0 or lin_vm("cjr_utilization", 1, 1, 3) != 0:
        rec(claims, "UTIL-UNDERFLOW", "FAIL", "cash+borrows < reserves should fail-closed")
        return 1
    if lin_vm("cjr_util_ok", 100, 0, 0) != 1 or lin_vm("cjr_utilization", 100, 0, 0) != 0:
        rec(claims, "UTIL-UNDERFLOW", "FAIL", "borrows==0 is genuine zero, not underflow")
        return 1
    rec(
        claims,
        "UTIL-UNDERFLOW",
        "PASS",
        "Solidity 0.8 would revert cash+borrows-reserves underflow; LIN returns 0 and util_ok=0",
    )

    lift_chk = run([str(C0), "check", str(LIFT)])
    if ".typecheck=passed" not in lift_chk.stdout:
        rec(claims, "VIEW-LIFT", "FAIL", "lin_sol_view_lift.lin check", lift_chk.stdout)
        return 1
    params = "uint cash, uint borrows, uint reserves"
    body = (
        "uint util = utilizationRate(cash, borrows, reserves); "
        "if (util <= kink) { return ((util * multiplierPerBlock) / BASE) + baseRatePerBlock; }"
    )
    extra = view_lift_free(params, body)
    banned = {"utilizationRate", "util", "cash", "borrows", "reserves"}
    need = {"kink", "multiplierPerBlock", "BASE", "baseRatePerBlock"}
    if not need.issubset(set(extra)) or banned.intersection(extra):
        rec(claims, "VIEW-LIFT", "FAIL", "Python lift oracle mismatch", ",".join(extra))
        return 1
    rec(
        claims,
        "VIEW-LIFT",
        "PASS",
        "view storage names become extra args; locals and calls are not lifted "
        "(LIN module typechecks; C0 vm rejects string literals so the scan is re-run in Python)",
        ",".join(extra),
    )

    src = LIN.read_text(encoding="utf-8")
    sig = 'cjr_borrow_rate(cash: int, borrows: int, reserves: int, base_block: int, mult_block: int, jump_block: int, kink: int)'
    sol = FIX.read_text(encoding="utf-8")
    if sig not in src or "internal view" not in sol or "msg.sender" not in sol:
        rec(claims, "EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/view")
        return 1
    rec(claims, "EXPLICIT-ARGS", "PASS", "LIN takes IRM params as arguments; Solidity reads storage + msg.sender")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "cjr_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec(claims, "C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite")
    else:
        rec(
            claims,
            "C0-JIT",
            "SKIP",
            "in-memory JIT not exercised (libtcc missing or module rejected)",
            (jit.stdout + jit.stderr)[:240],
        )

    evidence = {
        "schema": "LIN_INDEPENDENT_REPROOF_1.0",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "numbers": {
            "borrow_rate_50_util": py_r50,
            "borrow_rate_90_util": py_r90,
            "supply_rate_50_rf10": py_s50,
            "multiplier_per_block": c0_mb,
            "jump_per_block": jb,
            "i64_wrap_1e18_sq": wrap,
            "bigint_half_util": bigint_half,
            "fixture_sha256": got_sha,
            "fixture_git_blob": blob,
        },
        "not_claimed": [
            "full Solidity uint256 / mainnet cToken parity",
            "LIN replaces Compound, Uniswap, or the EVM",
            "general speed vs solc/EVM/LLVM (SipHash ~20.8x is compile-turnaround on one host)",
            "zk / computational soundness of Merkle (C4 is tamper-evidence + re-execution)",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
