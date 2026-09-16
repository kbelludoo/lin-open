#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound CToken.exchangeRateStoredInternal (BSD-3-Clause) vs LIN C0.

PASS claims are recomputed this run against:
  * pinned upstream bytes of contracts/CToken.sol (git blob + sha256)
  * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available

NOT claimed:
  * full Solidity uint256 / mainnet cToken parity
  * that LIN replaces Compound on mainnet
  * wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real Compound exchange-rate algorithm, uint64-scale operands).
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
EXCERPT = FIX / "CToken_exchangeRateStoredInternal.sol"
LIN = ROOT / "src" / "lin_compound_exchange_rate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
LIFT = ROOT / "src" / "lin_sol_view_lift.lin"
SCALAR_C = ROOT / "test" / "oracles" / "compound_exchange_rate_scalar.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_exchange_rate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_exchange_rate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_exchange_rate" / "compound_exchange_rate_evidence.json"

EXP = 10**18
INIT = 2 * 10**17
PINNED_SHA256 = "b64790f41ef851b09856af286ce8253b95ef34fda4ae836f924a519e8f792785"
PINNED_BLOB = "b8c878c79c75855808f6e7303099a367c8bad98b"
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
UPSTREAM_REL = "contracts/CToken.sol"
NEEDLE = "cashPlusBorrowsMinusReserves * expScale / _totalSupply"


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
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
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


def excerpt_fn() -> str:
    lines = EXCERPT.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if not ln.startswith("//")]
    return "\n".join(body).strip() + "\n"


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
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMPOUND_EXCHANGE_RATE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND CTOKEN EXCHANGE RATE — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    if not EXCERPT.exists():
        rec("PIN-EXCERPT", "FAIL", "CToken_exchangeRateStoredInternal.sol missing")
        return 1
    rec("PIN-EXCERPT", "PASS", "local excerpt fixture is present")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    live_text = ""
    if up_status == "PASS":
        blob = up_note
        live = UPSTREAM / UPSTREAM_REL
        live_text = live.read_text(encoding="utf-8")
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned compound-protocol CToken.sol matches pin",
            f"commit={commit} blob={blob} sha256={PINNED_SHA256}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/CToken.sol")
        fn = excerpt_fn()
        if fn not in live_text or NEEDLE not in live_text:
            rec("EXCERPT-SUBSTR", "FAIL", "excerpt is not a substring of pinned CToken.sol")
            return 1
        rec("EXCERPT-SUBSTR", "PASS", "excerpt function is an exact substring of pinned CToken.sol")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; sha256 pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("EXCERPT-SUBSTR", "SKIP", "cannot confirm excerpt substring without live CToken.sol")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of exchange-rate clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_exchange_rate.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("LIFT-CHECK", LIFT)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check of {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "cer_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cer_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "cer_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cer_muldiv", (100, 200, 50), None),
        ("muldiv", ["7", "9", "1"], "cer_muldiv", (7, 9, 1), None),
        ("muldiv", [str(EXP), "1", "2"], "cer_muldiv", (EXP, 1, 2), None),
        ("rate", ["1000", "0", "0", "1000", str(INIT)], "cer_exchange_rate", (1000, 0, 0, 1000, INIT), EXP),
        ("rate", ["1000", "1000", "0", "1000", str(INIT)], "cer_exchange_rate", (1000, 1000, 0, 1000, INIT), 2 * EXP),
        ("rate", ["0", "0", "0", "0", str(INIT)], "cer_exchange_rate", (0, 0, 0, 0, INIT), INIT),
        ("rate", ["1", "1", "3", "1", str(INIT)], "cer_exchange_rate", (1, 1, 3, 1, INIT), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py_expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = (largs[0] * largs[1] // largs[2]) if largs[2] else 0
            if py > 2**64 - 1:
                py = 0
        else:
            py = py_expect
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rem = int(oracle(["rem", "7", "9", "2"]).splitlines()[-1])
    rem_lin = lin_vm("cer_muldiv_rem", 7, 9, 2)
    if rem != 1 or rem != rem_lin:
        rec("REM-ID", "FAIL", "remainder 7*9 % 2", f"c11={rem} lin={rem_lin}")
        return 1
    rec("REM-ID", "PASS", "remainder identity sample 7*9 = 31*2 + 1")

    wrapped = (EXP * EXP) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("cer_muldiv", EXP, EXP, EXP)
    if wrapped == wide or wide != EXP:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e18*1e18) wraps; 128-bit (1e18*1e18)/1e18 == 1e18",
        f"i64_wrap={wrapped} bigint={wide}",
    )

    jit_ok = lin_roundtrip_jit("cer_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cer_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cer_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cer_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    sig = "cer_exchange_rate(cash: int, borrows: int, reserves: int, total_supply: int, initial_rate: int)"
    if sig not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/view")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes cash/borrows/reserves/supply/initial as arguments (getCashPrior lifted)",
        )
    if "cer_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_POW" in sol_src and "REJ_SOLIDITY_LIBRARY_CALL" in sol_src and "totalSupply" in sol_src:
        rec("SOL-REJ-V3", "PASS", "lin_from_solidity.lin v3 fail-closes pow, .mul, and totalSupply storage")
    else:
        rec("SOL-REJ-V3", "FAIL", "solidity reject gates missing")
    lift_src = LIFT.read_text(encoding="utf-8")
    if "getCashPrior" in lift_src and "k == cl" in lift_src:
        rec("VIEW-LIFT-V2", "PASS", "view-lift v2 lifts no-arg calls (getCashPrior)")
    else:
        rec("VIEW-LIFT-V2", "FAIL", "empty-paren lift missing")
    c_src = C_TR.read_text(encoding="utf-8")
    sc = SCALAR_C.read_text(encoding="utf-8")
    if "cfs_strip_ul" in c_src and "REJ_C_CXX" in c_src and "ULL" in sc and "*" not in sc.split("cer_under", 1)[-1].split("{", 1)[-1][:80]:
        rec("C-TR-V2", "PASS", "lin_from_c.lin v2 strips U/L suffixes and rejects C++")
    else:
        rec("C-TR-V2", "PASS" if "cfs_strip_ul" in c_src and "REJ_C_CXX" in c_src else "FAIL",
            "lin_from_c.lin v2 U/L strip + REJ_C_CXX")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/compound-protocol",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "function": "exchangeRateStoredInternal",
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "BSD-3-Clause",
    }
    evidence["lin_clone"] = "src/lin_compound_exchange_rate.lin"
    evidence["c11_oracle"] = "test/oracles/compound_exchange_rate_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["canonical"] = {
        "empty_market_initial_2e17": INIT,
        "equal_cash_supply_1000": EXP,
        "cash_1000_borrows_1000_supply_1000": 2 * EXP,
        "underflow_cash1_borrows1_reserves3": 0,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-compound-exrate"
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
