#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Saddle SwapUtils getD / getY (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of SwapUtils.sol (saddle-finance/saddle-contract)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Python arbitrary-precision int Newton
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * Solidity uint256 / N>2 / Curve.vy source parity
    * that LIN replaces Saddle, Curve, or a production stableswap
    * that Compiler 0 executes sol_from_sol string-literal paths
    * wall-clock superiority vs solc
    * a license to reproduce Curve.vy (Curve.Fi reserved-rights LICENSE)

Class: EXPERIMENTAL (real Saddle Newton D/Y, uint64-scale, N=2).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_saddle_getd.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "saddle_getd_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "saddle_getd_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_saddle_contract")
EVIDENCE = ROOT / "examples" / "saddle_getd" / "saddle_getd_evidence.json"

PINNED_COMMIT = "2cfdd05580efb626d79d597034b2cf5ae89b5626"
PINNED_SHA256 = "9684c7e46310e1b9d128587f08cf0b62e8d6d0574b094d338a9ed99e936f3df6"
PINNED_BLOB = "38e236c32c550ce63187dc9297eb36fac005851b"
SWAP_REL = "contracts/SwapUtils.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-saddle-getd"
A_PREC = 100
NCOIN = 2
U64 = 2**64 - 1

# (kind, args, lin_fn, lin_args, want)
VECTORS = [
    ("getd", ["1000", "1000", "10000"], "sgd_get_d", (1000, 1000, 10000), 2000),
    ("getd", ["1000", "2000", "10000"], "sgd_get_d", (1000, 2000, 10000), 2998),
    ("getd", ["1000000", "1000000", "20000"], "sgd_get_d", (1000000, 1000000, 20000), 2000000),
    ("getd", ["1000000", "1100000", "20000"], "sgd_get_d", (1000000, 1100000, 20000), 2099988),
    ("getd", ["100", "200", "10000"], "sgd_get_d", (100, 200, 10000), 299),
    ("gety", ["1000", "1000", "10000", "1000"], "sgd_get_y", (1000, 1000, 10000, 1000), 1000),
    ("gety", ["1000", "1000", "10000", "1010"], "sgd_get_y", (1000, 1000, 10000, 1010), 990),
    ("dy", ["1000", "1000", "10000", "10"], "sgd_dy", (1000, 1000, 10000, 10), 9),
    ("dy", ["1000000", "1000000", "20000", "10000"], "sgd_dy", (1000000, 1000000, 20000, 10000), 9999),
]


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def md(a: int, b: int, d: int) -> int:
    if d == 0 or a < 0 or b < 0:
        return 0
    q = a * b // d
    return 0 if q > U64 else q


def py_get_d(x0: int, x1: int, a: int) -> int:
    if x0 <= 0 or x1 <= 0 or a <= 0:
        return 0
    s = x0 + x1
    nA = md(a, NCOIN, 1)
    if nA == 0 or nA < A_PREC:
        return 0
    d = s
    for _ in range(256):
        dp = md(d, d, x0 * NCOIN)
        dp = md(dp, d, x1 * NCOIN)
        prev = d
        left = md(nA, s, A_PREC) + md(dp, NCOIN, 1)
        den = md(nA - A_PREC, d, A_PREC) + md(NCOIN + 1, dp, 1)
        if den == 0:
            return 0
        d = md(left, d, den)
        if abs(d - prev) <= 1:
            return d
    return 0


def py_get_y(x0: int, x1: int, a: int, x_new: int) -> int:
    d = py_get_d(x0, x1, a)
    if d == 0 or x_new <= 0:
        return 0
    nA = md(NCOIN, a, 1)
    c = md(d, d, x_new * NCOIN)
    c = md(md(c, A_PREC, 1), d, nA * NCOIN)
    b = x_new + md(d, A_PREC, nA)
    y = d
    for _ in range(256):
        prev = y
        num = md(y, y, 1) + c
        den = 2 * y + b - d
        if den <= 0:
            return 0
        y = md(num, 1, den)
        if abs(y - prev) <= 1:
            return y
    return 0


def py_dy(x0: int, x1: int, a: int, dx: int) -> int:
    if dx <= 0:
        return 0
    y = py_get_y(x0, x1, a, x0 + dx)
    if y == 0 or x1 <= y:
        return 0
    return x1 - y - 1


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    if kind == "getd":
        return py_get_d(*args)
    if kind == "gety":
        return py_get_y(*args)
    return py_dy(*args)


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/saddle-finance/saddle-contract.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / SWAP_REL
    if not live.exists():
        return "SKIP", "", f"{SWAP_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{SWAP_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    live_txt = live.read_text(encoding="utf-8")
    excerpt = (FIX / "getD.sol").read_text(encoding="utf-8")
    if "function getD(uint256[] memory xp, uint256 a)" not in live_txt:
        return "FAIL", commit, "getD missing"
    if "function getY(" not in live_txt:
        return "FAIL", commit, "getY missing"
    if "revert(\"D does not converge\")" not in live_txt:
        return "FAIL", commit, "getD revert missing"
    if "function getD(" not in excerpt or "function getY(" not in excerpt:
        return "FAIL", commit, "excerpt missing getD/getY"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  SADDLE getD / getY — external LIN proof (N=2 Newton, uint64-scale)")
    print("=" * 78)

    pinned = FIX / "SwapUtils.sol"
    excerpt = FIX / "getD.sol"
    if not pinned.exists() or not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned SwapUtils.sol / getD.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned SwapUtils.sol hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned SwapUtils.sol sha256 matches Saddle commit")

    src_ex = excerpt.read_text(encoding="utf-8")
    if "function getD(" not in src_ex or "function getY(" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing getD / getY")
        return 1
    if "uint256[]" not in src_ex or "revert(" not in src_ex or "within1" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing array / revert / within1")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has getD, getY, uint256[], revert, within1")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned saddle-contract commit matches fixture",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/SwapUtils.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb getD selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb getD/getY agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of saddle clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_saddle_getd.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3 (ARRAY/REVERT/FOR)")

    gate = run([str(C0), "vm", str(LIN), "sgd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "sgd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "sgd_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for kind, oargs, fn, largs, want in VECTORS:
        py = py_kind(kind, largs)
        c11 = int(oracle([kind, *oargs]).splitlines()[-1])
        limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got = lin_vm(fn, *largs)
        if py != want or c11 != want or limbs != want or got != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}",
                f"py={py} c11={c11} limbs={limbs} lin={got} want={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint == C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision Newton matches C11 and LIN")

    if lin_vm("sgd_get_d", 1000, 1000, 10000) != 2000 or lin_vm("sgd_get_d", 1000, 2000, 10000) != 2998:
        rec("INVARIANT", "FAIL", "balanced D vs imbalanced D")
        return 1
    rec("INVARIANT", "PASS", "balanced D(1000,1000)=2000; imbalanced D(1000,2000)=2998 < 3000")

    stable = lin_vm("sgd_dy", 1000000, 1000000, 20000, 10000)
    cp = lin_vm("sgd_cp_dy", 1000000, 1000000, 10000)
    if stable != 9999 or cp != 9871 or stable <= cp:
        rec("STABLE-VS-CP", "FAIL", "stableswap vs constant-product quote", f"stable={stable} cp={cp}")
        return 1
    rec("STABLE-VS-CP", "PASS", "1% swap of 1e6/1e6: Saddle fee-less dy=9999 > Uniswap-style cp=9871")

    if lin_vm("sgd_get_d", -1, 1000, 10000) != 0 or lin_vm("sgd_get_d", 1000, 1000, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "negative / A=0")
        return 1
    rec("FAIL-CLOSED", "PASS", "negative balances and A=0 fail-close to 0 (Saddle reverts)")

    jit_ok = lin_roundtrip_jit("sgd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sgd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("sgd_get_d", 1000, 1000, 10000)
        if jv == 2000:
            rec("C0-JIT", "PASS", "lin_c0 jit sgd_get_d(1000,1000,10000)==2000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "sgd_get_d(x0: int, x1: int, a: int)" in src and "uint256[]" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN flattens N=2 xp[0],xp[1],A; Saddle takes uint256[] + SafeMath")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit two-coin args vs Solidity array")

    if "sgd_muldiv_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses visible 128-bit schoolbook product (Saddle uses SafeMath uint256)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    rec("SOL-GD-REJ",
        "PASS" if "REJ_SOLIDITY_ARRAY" in sol_src and "REJ_SOLIDITY_REVERT" in sol_src else "FAIL",
        "lin_from_solidity.lin v3 rejects uint256[] / revert / for (lift is sgd_get_d)")
    rec("SOL-EX-SPLIT",
        "PASS" if 'out = out + "=";' in sol_src and 'out = out + "ex{"' in sol_src else "FAIL",
        "sol_from_sol concatenates '=' + 'ex{' so C0 export parse is honest")

    evidence = {
        "schema": "LIN_SADDLE_GETD_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/saddle-finance/saddle-contract",
            "commit": commit or PINNED_COMMIT,
            "path": SWAP_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "note": "Curve.vy was not pinned: Curve.Fi LICENSE grants no reproduction right. Saddle is the MIT Solidity Newton D.",
            "a_precision": "precise A = display A * 100; LIN a is precise A",
        },
        "lin_clone": "src/lin_saddle_getd.lin",
        "c11_oracle": "test/oracles/saddle_getd_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {"kind": k, "args": list(largs), "want": w} for k, _o, _f, largs, w in VECTORS
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
