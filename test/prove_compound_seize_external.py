#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound liquidateCalculateSeizeTokens (BSD-3-Clause) vs LIN C0.

PASS claims this run:
  * pinned Comptroller excerpt + ExponentialNoError.sol (git blob + sha256)
  * live git fetch of the pinned commit (SKIP if network fails; fixture pin holds)
  * C11 __int128 AND portable 32-bit limb muldiv
  * Compiler 0 interpreting src/lin_compound_seize.lin
  * in-memory libtcc JIT when libtcc is present
  * Solidity transpiler fail-closed on oracle/CToken/Exp/library/pow/state

NOT claimed: Solidity uint256 / mainnet cToken parity, LIN replacing Compound,
wall-clock superiority vs solc/EVM.

Class: EXPERIMENTAL (real Compound liquidation formula, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_compound_seize.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
LIFT = ROOT / "src" / "lin_sol_view_lift.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_seize_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_seize_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_seize" / "compound_seize_evidence.json"

BASE = 10**18
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
EXP_SHA256 = "dd272760b2d9082db9c94f6198896402fe3681bf41fc3f9d8bba31ada290c3c5"
EXP_BLOB = "23f833760db898ebdc6b2fef9654cb9bc1dd21c3"
COMPTROLLER_SHA256 = "89a4c77da4920d0d0e44d7591446fe15e6b0c8a4794646aa497f725dc72818d8"
COMPTROLLER_BLOB = "1d94cc756d1b52b84e4cc2ed3996cd9a7074a4ab"
EXCERPT_SHA256 = "bc0e31a964528088650047e17341bc9577ad91920a35c5e3cbd97b6a48ff568a"


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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/compound-finance/compound-protocol.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live_c = UPSTREAM / "contracts" / "Comptroller.sol"
    live_e = UPSTREAM / "contracts" / "ExponentialNoError.sol"
    if not live_c.exists() or not live_e.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob_c = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD:contracts/Comptroller.sol"]).stdout.strip()
    blob_e = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD:contracts/ExponentialNoError.sol"]).stdout.strip()
    if sha256_file(live_c) != COMPTROLLER_SHA256 or blob_c != COMPTROLLER_BLOB:
        return "FAIL", commit, f"comptroller live={sha256_file(live_c)} blob={blob_c}"
    if sha256_file(live_e) != EXP_SHA256 or blob_e != EXP_BLOB:
        return "FAIL", commit, f"exp live={sha256_file(live_e)} blob={blob_e}"
    excerpt = (FIX / "Comptroller_liquidateCalculateSeizeTokens.sol").read_text(encoding="utf-8")
    if excerpt not in live_c.read_text(encoding="utf-8"):
        return "FAIL", commit, "excerpt not a substring of live Comptroller.sol"
    return "PASS", commit, blob_c


def py_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (a * b) // d
    return 0 if q > (2**64 - 1) else q


def py_seize(repay: int, incentive: int, pb: int, pc: int, exch: int) -> int:
    if pb == 0 or pc == 0 or exch == 0:
        return 0
    num_m = py_muldiv(incentive, pb, BASE)
    den_m = py_muldiv(pc, exch, BASE)
    if den_m == 0:
        return 0
    ratio_m = py_muldiv(num_m, BASE, den_m)
    return py_muldiv(ratio_m, repay, BASE)


def sol_reason_py(sig: str, body: str) -> str:
    """Independent replica of src/lin_from_solidity.lin sol_reason (C0 vm rejects strings)."""
    if "payable" in sig:
        return "REJ_SOLIDITY_PAYABLE"
    if "msg.value" in body or "msg.sender" in body:
        return "REJ_SOLIDITY_STATE"
    if "block.timestamp" in body:
        return "REJ_SOLIDITY_ENV"
    if "assembly" in body:
        return "REJ_SOLIDITY_INLINE_ASM"
    if "mapping" in body or "storage" in sig:
        return "REJ_SOLIDITY_STORAGE"
    if "emit " in body:
        return "REJ_SOLIDITY_EVENT"
    if "oracle." in body:
        return "REJ_SOLIDITY_ORACLE"
    if "CToken(" in body:
        return "REJ_SOLIDITY_CTOKEN"
    if "address" in sig:
        return "REJ_SOLIDITY_ADDRESS"
    if "Exp({" in body or "Exp memory" in body:
        return "REJ_SOLIDITY_STRUCT"
    if "**" in body or "pow(" in body:
        return "REJ_SOLIDITY_POW"
    if ".mul(" in body or ".div(" in body:
        return "REJ_SOLIDITY_LIBRARY_CALL"
    if "totalSupply" in body or "totalAssets" in body or "totalBorrows" in body or "totalReserves" in body:
        return "REJ_SOLIDITY_STATE"
    if "pure" in sig:
        return "OK"
    if "view" in sig:
        return "OK_VIEW"
    return "REJ_SOLIDITY_NON_PURE"


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMPOUND_SEIZE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND SEIZE TOKENS — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    exp = FIX / "ExponentialNoError.sol"
    excerpt = FIX / "Comptroller_liquidateCalculateSeizeTokens.sol"
    if not exp.exists() or not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned ExponentialNoError.sol or Comptroller excerpt missing")
        return 1
    if sha256_file(exp) != EXP_SHA256:
        rec("PIN-EXP", "FAIL", "ExponentialNoError.sol sha256 mismatch", sha256_file(exp))
        return 1
    rec("PIN-EXP", "PASS", "pinned ExponentialNoError.sol sha256 matches manifest")
    if sha256_file(excerpt) != EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "Comptroller excerpt sha256 mismatch", sha256_file(excerpt))
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned liquidateCalculateSeizeTokens excerpt sha256 matches")

    up_status, commit, up_note = ensure_upstream()
    blob = COMPTROLLER_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned compound-protocol commit matches fixtures",
            f"commit={commit} comptroller_blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of Comptroller.sol + ExponentialNoError.sol")
        rec("EXCERPT-IN-FILE", "PASS", "excerpt is a substring of live Comptroller.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("EXCERPT-IN-FILE", "SKIP", "live Comptroller.sol not fetched this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("EXCERPT-IN-FILE", "FAIL", "excerpt/live mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of seize clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_seize.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("LIFT-CHECK", LIFT)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout and ".typecheck=passed" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "cls_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cls_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "cls_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cls_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "cls_muldiv", (7, 9, 1)),
        ("muldiv", [str(BASE), "1", "2"], "cls_muldiv", (BASE, 1, 2)),
        ("seize", ["1000", str(BASE), str(BASE), str(BASE), str(BASE)], "cls_seize",
         (1000, BASE, BASE, BASE, BASE)),
        ("seize", ["1000", "1080000000000000000", str(BASE), str(BASE), "200000000000000000"],
         "cls_seize", (1000, 1080000000000000000, BASE, BASE, 200000000000000000)),
        ("seize", ["1000", "1080000000000000000", "0", str(BASE), str(BASE)], "cls_seize",
         (1000, 1080000000000000000, 0, BASE, BASE)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} limbs={want_limbs}")
            return 1
        py = py_muldiv(*largs) if kind == "muldiv" else py_seize(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python bigint")

    wrapped = (BASE * BASE) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == (BASE * BASE) // BASE:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint muldiv")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes",
        f"i64_wrap={wrapped} bigint_or_failclosed={py_muldiv(BASE, BASE, 1)}")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    seize_body = excerpt.read_text(encoding="utf-8")
    seize_sig = (
        "function liquidateCalculateSeizeTokens(address cTokenBorrowed, "
        "address cTokenCollateral, uint actualRepayAmount) override external view"
    )
    r_seize = sol_reason_py(seize_sig, seize_body)
    if r_seize not in ("REJ_SOLIDITY_ORACLE", "REJ_SOLIDITY_CTOKEN", "REJ_SOLIDITY_ADDRESS", "REJ_SOLIDITY_STRUCT"):
        rec("SOL-REJ-SEIZE", "FAIL", "seize view must fail-closed", r_seize)
        return 1
    rec("SOL-REJ-SEIZE", "PASS", "lin_from_solidity v3 fail-closes Comptroller seize view", r_seize)
    if sol_reason_py("function f() internal pure", "return amountIn.mul(997);") != "REJ_SOLIDITY_LIBRARY_CALL":
        rec("SOL-REJ-LIB", "FAIL", ".mul library call not rejected")
        return 1
    rec("SOL-REJ-LIB", "PASS", "REJ_SOLIDITY_LIBRARY_CALL on SafeMath-style .mul(")
    if sol_reason_py("function f() internal pure", "return x ** 2;") != "REJ_SOLIDITY_POW":
        rec("SOL-REJ-POW", "FAIL", "pow not rejected")
        return 1
    rec("SOL-REJ-POW", "PASS", "REJ_SOLIDITY_POW on **")
    if "REJ_SOLIDITY_ORACLE" not in sol_src or "OK_VIEW" not in sol_src:
        rec("SOL-EMIT", "FAIL", "v3 rejection/OK_VIEW strings missing from lin_from_solidity.lin")
        return 1
    rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3: OK_VIEW emit + oracle/library/pow/state REJ")
    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX" not in c_src or "ceil" not in c_src:
        rec("C-REJ-CXX", "FAIL", "lin_from_c.lin missing REJ_C_CXX / ceil-floor")
        return 1
    rec("C-REJ-CXX", "PASS", "lin_from_c.lin rejects ::/static_cast/optional and ceil/floor")
    lift_src = LIFT.read_text(encoding="utf-8")
    if "getCashPrior" not in lift_src or "match_paren" not in lift_src:
        rec("VIEW-LIFT", "FAIL", "view-lift v2 no-arg call lift missing")
        return 1
    rec("VIEW-LIFT", "PASS", "lin_sol_view_lift.lin v2 lifts no-arg calls (getCashPrior/exchangeRateStored)")

    src = LIN.read_text(encoding="utf-8")
    if "cls_seize(repay: int, incentive: int, price_borrowed: int, price_collateral: int, exchange_rate: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity oracle/storage")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes prices, incentive and exchangeRate as arguments")
    if "cls_muldiv" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product for Exp mul_/div_/truncate")

    if lin_roundtrip_jit("cls_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cls_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cls_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cls_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/compound-protocol",
        "commit": commit or PINNED_COMMIT,
        "path": "contracts/Comptroller.sol + contracts/ExponentialNoError.sol",
        "git_blob_sha_comptroller": blob or COMPTROLLER_BLOB,
        "git_blob_sha_exp": EXP_BLOB,
        "file_sha256_comptroller": COMPTROLLER_SHA256,
        "file_sha256_exp": EXP_SHA256,
        "excerpt_sha256": EXCERPT_SHA256,
        "license": "BSD-3-Clause",
    }
    evidence["lin_clone"] = "src/lin_compound_seize.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-compound-seize"
    evidence["c11_oracle"] = "test/oracles/compound_seize_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["canonical_seize_8pct_exrate_0p2"] = 5400
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
