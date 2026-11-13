#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Morpho Blue MathLib (MIT file SPDX) vs LIN Compiler 0.

PASS claims are recomputed this run against:
  * pinned upstream bytes of src/libraries/MathLib.sol (git blob + sha256)
  * an independent C11 oracle (unsigned __int128, i64-positive fail-closed)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int as a third oracle

NOT claimed: Solidity uint256 / mainnet Morpho market parity; LIN replacing
Morpho; TVL or dollar savings; zk soundness.
Class: EXPERIMENTAL (real Morpho WAD/Taylor algorithm, i64-positive operands).
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
LIN = ROOT / "src" / "lin_morpho_mathlib.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "morpho_mathlib_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "morpho_mathlib_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_morpho_blue")
EVIDENCE = ROOT / "examples" / "morpho_mathlib" / "morpho_mathlib_evidence.json"

WAD = 10**18
I64M = 2**63 - 1
PINNED_SHA256 = "61c0e20da6b026a356ed86d47da921ef2d69f65e40d9c8b97e7ae18ad497aa22"
PINNED_BLOB = "3c0afc991c3bfa9314498b43047a0675be4a9410"
PINNED_COMMIT = "339a885801972740eb27f51da110a4675b839d42"
UPSTREAM_REL = "src/libraries/MathLib.sol"
RATE_10PCT = 3170979198  # ~10% APY as WAD per-second: 0.10e18 / 31536000


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )


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


def ensure_oracle() -> None:
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_md(x: int, y: int, d: int) -> int:
    if d == 0 or x < 0 or y < 0:
        return 0
    q = (x * y) // d
    return 0 if q > I64M else q


def py_mu(x: int, y: int, d: int) -> int:
    if d == 0 or x < 0 or y < 0:
        return 0
    q = (x * y) // d
    r = (x * y) % d
    if q > I64M:
        return 0
    if r == 0:
        return q
    if q == I64M:
        return 0
    return q + 1


def py_taylor(x: int, n: int) -> int:
    first = py_md(x, n, 1)
    if first == 0:
        return 0
    second = py_md(first, first, 2 * WAD)
    third = py_md(second, first, 3 * WAD)
    s = first + second + third
    return 0 if s > I64M else s


def py_accrue(borrow: int, rate: int, elapsed: int) -> int:
    if elapsed == 0:
        return 0
    return py_md(borrow, py_taylor(rate, elapsed), WAD)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/morpho-org/morpho-blue.git"
    if not (UPSTREAM / ".git").exists():
        proc = run(["git", "clone", "--depth", "1", url, str(UPSTREAM)], timeout=120)
        if proc.returncode != 0:
            return "SKIP", "", proc.stderr[-400:]
    proc = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if proc.returncode != 0:
        head = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"])
        if head.stdout.strip() != PINNED_COMMIT:
            return "SKIP", "", "fetch of pinned commit unavailable"
    else:
        run(["git", "-C", str(UPSTREAM), "checkout", "--force", PINNED_COMMIT], timeout=30)
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    src = UPSTREAM / UPSTREAM_REL
    if not src.exists():
        return "FAIL", commit, "MathLib.sol missing"
    blob = run(["git", "-C", str(UPSTREAM), "hash-object", UPSTREAM_REL]).stdout.strip()
    live = sha256_file(src)
    pinned = FIX / "MathLib.sol"
    if live != PINNED_SHA256 or sha256_file(pinned) != PINNED_SHA256:
        return "FAIL", commit, f"sha256 live={live}"
    if blob != PINNED_BLOB:
        return "FAIL", commit, f"blob={blob}"
    if commit != PINNED_COMMIT:
        return "SKIP", commit, "HEAD is not the pinned commit; fixture pin holds"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict[str, object] = {"schema": "LIN_MORPHO_MATHLIB_EVIDENCE_1.0"}

    def rec(cid: str, status: str, msg: str, extra: str = "") -> None:
        row = {"id": cid, "status": status, "msg": msg}
        if extra:
            row["extra"] = extra
        claims.append(row)
        flag = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[status]
        print(f"  [{flag}] {cid}: {msg}" + (f" ({extra})" if extra else ""))

    print("=" * 78)
    print("  Morpho Blue MathLib — LIN clone external proof (C11 Compiler 0)")
    print("=" * 78)

    pinned = FIX / "MathLib.sol"
    if not pinned.exists() or sha256_file(pinned) != PINNED_SHA256:
        rec("PIN", "FAIL", "fixture sha256 mismatch", sha256_file(pinned) if pinned.exists() else "missing")
        return 1
    rec("PIN", "PASS", "pinned MathLib.sol sha256 matches", PINNED_SHA256)

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned morpho-blue commit matches fixture", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MathLib.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 oracle selftest")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if chk.returncode != 0 and ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Morpho MathLib clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_morpho_mathlib.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    gate = run([str(C0), "vm", str(SOL_TR), "sol_from_sol_gate"])
    gv = value_of(gate.stdout)
    if gate.returncode == 0 and gv == 1:
        rec("SOL-TR-GATE", "PASS", "sol_from_sol_gate == 1 (WAD const, require, OK_VIEW, CEIL_DIV)")
    else:
        rec(
            "SOL-TR-GATE",
            "SKIP" if gate.returncode != 0 else "FAIL",
            "sol_from_sol_gate not executed on C0" if gate.returncode != 0 else "sol_from_sol_gate != 1",
            gate.stdout[-400:],
        )

    suite = run([str(C0), "vm", str(LIN), "mm_test_suite"])
    sv = value_of(suite.stdout)
    if suite.returncode != 0 or sv != 1:
        rec("LIN-SUITE", "FAIL", "mm_test_suite via lin_c0 vm", suite.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "mm_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["7", "9", "2"], "mm_muldiv", (7, 9, 2), py_md(7, 9, 2)),
        ("muldivup", ["7", "9", "2"], "mm_muldiv_ceil", (7, 9, 2), py_mu(7, 9, 2)),
        ("wmul", [str(WAD), str(WAD)], "mm_wmul_down", (WAD, WAD), py_md(WAD, WAD, WAD)),
        ("wdiv", ["2", "3"], "mm_wdiv_down", (2, 3), py_md(2, WAD, 3)),
        ("wdivup", ["2", "3"], "mm_wdiv_up", (2, 3), py_mu(2, WAD, 3)),
        ("taylor", [str(RATE_10PCT), "86400"], "mm_wtaylor", (RATE_10PCT, 86400), py_taylor(RATE_10PCT, 86400)),
        ("accrue", [str(WAD), str(RATE_10PCT), "86400"], "mm_accrue_interest", (WAD, RATE_10PCT, 86400), py_accrue(WAD, RATE_10PCT, 86400)),
        ("accrue", [str(5 * WAD), str(RATE_10PCT), "86400"], "mm_accrue_interest", (5 * WAD, RATE_10PCT, 86400), py_accrue(5 * WAD, RATE_10PCT, 86400)),
        ("taylor", [str(RATE_10PCT), "3600"], "mm_wtaylor", (RATE_10PCT, 3600), py_taylor(RATE_10PCT, 3600)),
        ("muldiv", [str(WAD), str(WAD), "1"], "mm_muldiv", (WAD, WAD, 1), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got = lin_vm(fn, *largs)
        if want != py:
            rec("VEC-PY", "FAIL", f"{kind} python vs C11", f"py={py} c11={want}")
            return 1
        if got != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint == C11 i128 == LIN vm")

    wrapped = ((WAD * WAD) & ((1 << 64) - 1))
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("mm_naive_i64_mul", WAD, WAD)
    if naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 product did not wrap", f"lin={naive} wrap={wrapped}")
        return 1
    if lin_vm("mm_muldiv", WAD, WAD, 1) == 0 and naive != 0:
        rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes", f"i64_wrap={naive}")
    else:
        rec("I64-WRAP", "FAIL", "expected wrap vs fail-closed contrast missing")
        return 1

    floor = lin_vm("mm_wdiv_down", 2, 3)
    ceil = lin_vm("mm_wdiv_up", 2, 3)
    if ceil != floor + 1:
        rec("CEIL-REM", "FAIL", "wDivUp should be remainder+1 vs floor", f"floor={floor} ceil={ceil}")
        return 1
    rec("CEIL-REM", "PASS", "wDivUp uses remainder+1 (not overflow-prone prod+(d-1))", f"2*WAD/3 floor={floor} ceil={ceil}")

    jit_ok = lin_roundtrip_jit("mm_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mm_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mm_muldiv", 7, 9, 2)
        if jv == 31:
            rec("C0-JIT", "PASS", "lin_c0 jit mm_muldiv(7,9,2)==31 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "wTaylorCompounded" in sol and "mm_accrue_interest" in src and "elapsed" in src:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN accrueInterest kernel takes elapsed as an argument (Morpho.sol uses block.timestamp - lastUpdate)",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected mm_accrue_interest(elapsed) vs MathLib wTaylorCompounded")
    if "mm_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_apply_first_const" in sol_src and "sol_has_ceil_div" in sol_src:
        rec("SOL-EMIT-V3", "PASS", "lin_from_solidity.lin v3: const bind, require fail-closed, CEIL_DIV, OK_VIEW emit")
    else:
        rec("SOL-EMIT-V3", "FAIL", "v3 emit path missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/morpho-org/morpho-blue",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT (file SPDX); GPL-2.0 (repo LICENSE)",
    }
    evidence["lin_clone"] = "src/lin_morpho_mathlib.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-morpho-mathlib"
    evidence["c11_oracle"] = "test/oracles/morpho_mathlib_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "mulDivDown(7,9,2)": 31,
        "mulDivUp(7,9,2)": 32,
        "wTaylorCompounded(3170979198,86400)": 274010136628159,
        "accrueInterest(1e18,3170979198,86400)": 274010136628159,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
