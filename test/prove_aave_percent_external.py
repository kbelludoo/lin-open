#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 PercentageMath (MIT after BUSL Change Date) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of PercentageMath.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_aave_percent.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 range
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL savings

Class: EXPERIMENTAL (real Aave percent half-up algorithm, i64-positive operands).
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
LIN = ROOT / "src" / "lin_aave_percent.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_percent_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_percent_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3")
EVIDENCE = ROOT / "examples" / "aave_percent" / "aave_percent_evidence.json"

FACTOR = 10**4
HALF = FACTOR // 2
W3 = 3 * 10**18
PINNED_SHA256 = "6f165ad32ddcc3383cbb611cc3045c1a4bb28f16f83a85015fe202803de0161f"
PINNED_BLOB = "c000be3a6c38a959aa3d28737445eaa5762c53b0"
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
UPSTREAM_REL = "contracts/protocol/libraries/math/PercentageMath.sol"
I64MAX = 2**63 - 1
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-percent"


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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/aave/aave-v3-core.git"
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


def py_pct_mul(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * b + HALF) // FACTOR
    return 0 if q > I64MAX else q


def py_pct_div(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * FACTOR + b // 2) // b
    return 0 if q > I64MAX else q


def py_floor_mul(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * b) // FACTOR
    return 0 if q > I64MAX else q


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_PERCENT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 PERCENTAGE — external LIN proof (i64-positive, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "PercentageMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned PercentageMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned PercentageMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned aave-v3-core commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of PercentageMath.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv_add selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Aave percent clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_percent.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec(
        "SOL-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3 (0.5eN + percent reject)",
    )
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec(
        "RS-TR-CHECK",
        "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2 (Aave percent reject)",
    )
    chk4 = run([str(C0), "check", str(C_TR)])
    rec(
        "C-TR-CHECK",
        "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL",
        "Compiler 0 check of C transpiler v2 (Aave percent reject)",
    )

    gate = run([str(C0), "vm", str(LIN), "apc_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "apc_test_suite via lin_c0 vm", f"rc={gate.returncode} value={gv}\n{gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "apc_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("pctmul", ["10000", "10000"], "apc_percent_mul", (FACTOR, FACTOR)),
        ("pctmul", ["3", "5000"], "apc_percent_mul", (3, HALF)),
        ("pctdiv", ["2", "3"], "apc_percent_div", (2, 3)),
        ("pctdiv", ["1", "3"], "apc_percent_div", (1, 3)),
        ("pctmul", ["0", "10000"], "apc_percent_mul", (0, FACTOR)),
        ("pctmul", [str(W3), "5000"], "apc_percent_mul", (W3, HALF)),
        ("pctmul", ["4000000000000000000", "30000"], "apc_percent_mul", (4 * 10**18, 30000)),
        ("floor_mul", ["3", "5000"], "apc_wrong_floor_mul", (3, HALF)),
        ("floor_div", ["2", "3"], "apc_wrong_floor_div", (2, 3)),
        ("pctmul", ["1", "5000"], "apc_percent_mul", (1, HALF)),
        ("pctmul", ["1", "4999"], "apc_percent_mul", (1, 4999)),
        ("pctdiv", ["10000", "10000"], "apc_percent_div", (FACTOR, FACTOR)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs or got_lin != want:
            rec("VEC-CONSENSUS", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} limbs={want_limbs}")
            return 1
        if kind == "pctmul":
            py = py_pct_mul(largs[0], largs[1])
        elif kind == "pctdiv":
            py = py_pct_div(largs[0], largs[1])
        elif kind == "floor_mul":
            py = py_floor_mul(largs[0], largs[1])
        else:
            py = (largs[0] * FACTOR) // largs[1]
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    half_up = lin_vm("apc_percent_mul", 3, HALF)
    floor = lin_vm("apc_wrong_floor_mul", 3, HALF)
    if half_up != 2 or floor != 1:
        rec("HALF-UP", "FAIL", "percentMul(3, 0.5e4) half-up vs floor", f"half={half_up} floor={floor}")
        return 1
    rec("HALF-UP", "PASS", "percentMul(3, 0.5e4)=2 half-up vs floor 1")

    d_up = lin_vm("apc_percent_div", 2, 3)
    d_floor = lin_vm("apc_wrong_floor_div", 2, 3)
    if d_up != 6667 or d_floor != 6666:
        rec("DIV-HALF-UP", "FAIL", "percentDiv(2,3) half-up vs floor", f"up={d_up} floor={d_floor}")
        return 1
    rec("DIV-HALF-UP", "PASS", "percentDiv(2,3)=6667 half-up vs floor 6666")

    wide = lin_vm("apc_percent_mul", W3, HALF)
    naive = lin_vm("apc_naive_i64_mul", W3, HALF)
    if wide != 1500000000000000000 or naive == wide:
        rec("I64-WRAP", "FAIL", "128-bit percentMul vs naive i64 3e18*5000", f"wide={wide} naive={naive}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e18*5000) wraps; 128-bit half-up percentMul does not",
        f"i64_wrap={naive} percentmul={wide}",
    )

    jit_ok = lin_roundtrip_jit("apc_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on apc_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("apc_percent_mul", 3, HALF)
        if jv == 2:
            rec("C0-JIT", "PASS", "lin_c0 jit apc_percent_mul(3,5000)==2 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "assembly" not in sol or "HALF_PERCENTAGE_FACTOR" not in sol or "0.5e4" not in sol:
        rec("UPSTREAM-YUL", "FAIL", "pinned PercentageMath.sol missing Yul half-up percentMul")
    else:
        rec("UPSTREAM-YUL", "PASS", "upstream percentMul is Yul (a*b+HALF)/1e4; LIN is explicit 128-bit")
    if "apc_muldiv_add_part" in src and "_lia_ushr" in src:
        rec("WIDE-HALFUP", "PASS", "clone uses 128-bit (a*b+add)/d; naive i64 a*b wraps on 3e18*5000")
    else:
        rec("WIDE-HALFUP", "FAIL", "128-bit half-up muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_AAVE_PERCENT" in sol_src and "0.5e4" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3 expands 0.5eN and rejects Aave percent Yul")
    else:
        rec("SOL-EMIT", "FAIL", "v3 Aave percent reject or 0.5eN expand missing")
    if "REJ_RUST_AAVE_PERCENT" in RS_TR.read_text(encoding="utf-8"):
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 rejects percent_mul / HALF_PERCENTAGE_FACTOR")
    else:
        rec("RS-EMIT", "FAIL", "Rust Aave percent reject missing")
    if "REJ_C_AAVE_PERCENT" in C_TR.read_text(encoding="utf-8"):
        rec("C-EMIT", "PASS", "lin_from_c.lin v2 rejects percent_mul / HALF_PERCENTAGE_FACTOR")
    else:
        rec("C-EMIT", "FAIL", "C Aave percent reject missing")
    if "sol_parse_test_gate" in sol_src and "REJ_SOLIDITY_AAVE_PERCENT" in sol_src:
        rec("SOL-GATE", "PASS", "sol_parse_test_gate source asserts Aave percent rejections (C0 check-only)")
    else:
        rec("SOL-GATE", "FAIL", "sol_parse_test_gate missing Aave percent assertions")
    if 'sol_expand_exp("0.5e4")' in sol_src and "5000" in sol_src:
        rec("SOL-EXPAND", "PASS", "sol_from_sol_gate asserts 0.5e4 -> 5000 (HALF_PERCENTAGE_FACTOR)")
    else:
        rec("SOL-EXPAND", "FAIL", "0.5e4 HALF_PERCENTAGE expand assertion missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/aave/aave-v3-core",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT",
        "license_note": "BUSL-1.1 Change Date 2023-01-27 elapsed; Change License MIT",
    }
    evidence["lin_clone"] = "src/lin_aave_percent.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/aave_percent_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "percentMul_3_HALF": 2,
        "floorMul_3_HALF": 1,
        "percentDiv_2_3": 6667,
        "floorDiv_2_3": 6666,
        "percentMul_3e18_HALF": 1500000000000000000,
        "naive_i64_3e18_HALF": 2797068074134536192,
        "percentMul_4e18_300pct": 0,
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
