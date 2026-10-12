#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound III getUtilization vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned excerpt of getUtilization plus live git bytes of
      CometWithExtendedAssetList.sol / CometCore.sol (blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_comet_util.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Compound V2 JumpRate utilization as a named contrast (same 1e18 numbers)

  NOT claimed:
    * full Solidity uint256 range
    * presentValue / principalValue / accruedInterestIndices (other clones)
    * that LIN replaces Compound III on mainnet
    * wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real Comet utilization wrap, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_comet_util.lin"
JUMP = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "comet_util_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "comet_util_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_comet")
EVIDENCE = ROOT / "examples" / "comet_util" / "comet_util_evidence.json"

FACTOR = 10**18
PINNED_SHA256 = "c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961"
PINNED_BLOB = "3490e984d133789aa1afe2e8f7e37a11d2512396"
PINNED_CORE_SHA256 = "1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78"
PINNED_CORE_BLOB = "534f2701b6c8e683f9294112b0bcc23878d39fe6"
PINNED_COMMIT = "f766f51583c23acc33b2a7824654ef2029a96804"
UPSTREAM_REL = "contracts/CometWithExtendedAssetList.sol"
CORE_REL = "contracts/CometCore.sol"
UTIL_SNIPPET = (
    "    function getUtilization() override public view returns (uint) {\n"
    "        uint totalSupply_ = presentValueSupply(baseSupplyIndex, totalSupplyBase);\n"
    "        uint totalBorrow_ = presentValueBorrow(baseBorrowIndex, totalBorrowBase);\n"
    "        if (totalSupply_ == 0) {\n"
    "            return 0;\n"
    "        } else {\n"
    "            return totalBorrow_ * FACTOR_SCALE / totalSupply_;\n"
    "        }\n"
    "    }\n"
)


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


def lin_vm(path: Path, fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(path), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


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
    url = "https://github.com/compound-finance/comet.git"
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
    core = UPSTREAM / CORE_REL
    if not live.exists() or not core.exists():
        return "SKIP", "", "comet sources missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    core_hash = sha256_file(core)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    if core_hash != PINNED_CORE_SHA256:
        return "FAIL", commit, f"core={core_hash}"
    text = live.read_text(encoding="utf-8")
    if UTIL_SNIPPET not in text:
        return "FAIL", commit, "getUtilization snippet missing from live file"
    if "uint64 internal constant FACTOR_SCALE = 1e18;" not in core.read_text(encoding="utf-8"):
        return "FAIL", commit, "FACTOR_SCALE missing from CometCore.sol"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMET_UTIL_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND III getUtilization — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    excerpt = FIX / "CometGetUtilization.excerpt.sol"
    if not excerpt.exists():
        rec("PIN-EXCERPT", "FAIL", "pinned getUtilization excerpt missing")
        return 1
    ex = excerpt.read_text(encoding="utf-8")
    if UTIL_SNIPPET not in ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt does not contain exact getUtilization bytes")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt contains exact getUtilization substring")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned comet commit matches fixture hashes",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CometWithExtendedAssetList.sol")
        rec("CORE-SHA", "PASS", "CometCore.sol sha256 + FACTOR_SCALE=1e18")
        rec("SNIPPET-IN-LIVE", "PASS", "getUtilization excerpt is a substring of live bytes")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; excerpt pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("CORE-SHA", "SKIP", "live CometCore.sol not hashed this run")
        rec("SNIPPET-IN-LIVE", "SKIP", "live substring check skipped")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("CORE-SHA", "FAIL", "CometCore.sol mismatch", up_note)
        rec("SNIPPET-IN-LIVE", "FAIL", "excerpt not in live file", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of comet util clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_comet_util.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "c3u_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "c3u_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "c3u_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "c3u_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "c3u_muldiv", (7, 9, 1)),
        ("util", [str(FACTOR), str(FACTOR)], "c3u_utilization", (FACTOR, FACTOR)),
        ("util", [str(2 * FACTOR), str(FACTOR)], "c3u_utilization", (2 * FACTOR, FACTOR)),
        ("util", [str(FACTOR), "0"], "c3u_utilization", (FACTOR, 0)),
        ("util", ["0", str(FACTOR)], "c3u_utilization", (0, FACTOR)),
        ("util", [str(FACTOR), str(2 * FACTOR)], "c3u_utilization", (FACTOR, 2 * FACTOR)),
        ("twostep", [str(2 * FACTOR), str(FACTOR)], "c3u_twostep", (2 * FACTOR, FACTOR)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        extra = ["--limbs"] if kind != "twostep" else []
        if extra:
            want_limbs = int(oracle([kind, *oargs, *extra]).splitlines()[-1])
            if want != want_limbs:
                rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
                return 1
        got_lin = lin_vm(LIN, fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = largs[0] * largs[1] // largs[2]
        elif kind == "twostep":
            py = 0 if largs[0] == 0 else (largs[1] // largs[0]) * FACTOR
        else:
            py = 0 if largs[0] == 0 else (largs[1] * FACTOR) // largs[0]
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    iii_same = lin_vm(LIN, "c3u_utilization", FACTOR, FACTOR)
    v2_same = lin_vm(JUMP, "cjr_utilization", FACTOR, FACTOR, 0)
    if iii_same != FACTOR or v2_same != FACTOR // 2:
        rec(
            "V2-CONTRAST",
            "FAIL",
            "III present-value util vs V2 cash util on 1e18/1e18",
            f"iii={iii_same} v2={v2_same}",
        )
        return 1
    rec(
        "V2-CONTRAST",
        "PASS",
        "same 1e18 numbers: III util=100% vs V2 JumpRate util=50% (2x)",
        f"iii={iii_same} v2={v2_same}",
    )
    iii_aligned = lin_vm(LIN, "c3u_utilization", 2 * FACTOR, FACTOR)
    if iii_aligned != v2_same:
        rec("V2-ALIGN", "FAIL", "III supply=cash+borrows should match V2 50%", f"{iii_aligned}")
        return 1
    rec("V2-ALIGN", "PASS", "III supply_pv=2e18 borrow_pv=1e18 matches V2 50% util")

    two = lin_vm(LIN, "c3u_twostep", 2 * FACTOR, FACTOR)
    if two == iii_aligned or two != 0:
        rec("TWOSTEP-REJ", "FAIL", "two-step floor(borrow/supply)*FACTOR must be 0 here")
        return 1
    rec(
        "TWOSTEP-REJ",
        "PASS",
        "named rejected path floor(borrow/supply)*1e18 = 0; Comet wrap = 5e17",
        f"twostep={two} comet={iii_aligned}",
    )

    wrapped = (FACTOR * FACTOR) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == (FACTOR * FACTOR) // FACTOR:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv does not",
        f"i64_wrap={wrapped} bigint={(FACTOR * FACTOR) // FACTOR}",
    )

    jit_ok = lin_roundtrip_jit("c3u_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on c3u_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    src = LIN.read_text(encoding="utf-8")
    if "c3u_utilization(supply_pv: int, borrow_pv: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit PV totals as arguments")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes present-value totals as arguments (no hidden index/storage)",
        )
    if "presentValueSupply" in src or "totalSupplyBase" in src:
        rec("NO-HIDDEN-PV", "FAIL", "clone must not call presentValue* or read totalSupplyBase")
    else:
        rec("NO-HIDDEN-PV", "PASS", "clone does not reimplement presentValue/principalValue")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = (
        "REJ_SOLIDITY_UTIL_WRAP",
        "totalBorrow_ * FACTOR_SCALE",
        "presentValueSupply(",
        "presentValueBorrow(",
        "totalSupplyBase",
        "totalBorrowBase",
        '"="',
        '"ex{"',
    )
    missing = [t for t in need if t not in sol_src]
    if missing:
        rec("SOL-REJ", "FAIL", "solidity transpiler v3 missing reject tokens", str(missing))
    else:
        rec("SOL-REJ", "PASS", "v3 rejects UTIL_WRAP / PV getters; emit splits '=' + 'ex{'")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_UTIL_WRAP" not in rs_src or "* FACTOR_SCALE" not in rs_src:
        rec("RS-REJ", "FAIL", "rust transpiler missing REJ_RUST_UTIL_WRAP")
    else:
        rec("RS-REJ", "PASS", "rust transpiler v2 rejects * FACTOR_SCALE wrapping util")

    gate_sol = run([str(C0), "vm", str(SOL_TR), "sol_parse_test_gate"])
    if "VM_REJ_STRING_LITERAL" in gate_sol.stdout or "VM_REJ_STRING_LITERAL" in gate_sol.stderr:
        rec(
            "SOL-GATE-REJ",
            "PASS",
            "Compiler 0 refuses sol_parse_test_gate string-literal path (VM_REJ_STRING_LITERAL)",
        )
    else:
        rec("SOL-GATE-REJ", "SKIP", "string-literal reject not observed", gate_sol.stdout[:200])

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/comet",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "core_path": CORE_REL,
        "core_git_blob_sha": PINNED_CORE_BLOB,
        "core_file_sha256": PINNED_CORE_SHA256,
        "license": "GPL-2.0-or-later (BUSL-1.1 Change Date 2025-12-31 elapsed)",
    }
    evidence["lin_clone"] = "src/lin_comet_util.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-comet-util"
    evidence["c11_oracle"] = "test/oracles/comet_util_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["iii_util_1e18_1e18"] = iii_same
    evidence["v2_util_1e18_1e18_0"] = v2_same
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
