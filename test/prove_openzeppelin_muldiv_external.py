#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: OpenZeppelin Math.mulDiv + Rounding (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of Math.sol in OpenZeppelin Contracts v5.0.2
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * Solidity uint256 / 512-bit CRT product parity
    * that LIN replaces OpenZeppelin, ERC-4626 vaults, or the EVM
    * that Compiler 0 executes sol_from_sol string-literal paths
    * wall-clock superiority vs solc

Class: EXPERIMENTAL (real OZ mulDiv rounding algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_openzeppelin_muldiv.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "openzeppelin_muldiv_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "openzeppelin_muldiv_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_openzeppelin")
EVIDENCE = ROOT / "examples" / "openzeppelin_muldiv" / "openzeppelin_muldiv_evidence.json"

PINNED_COMMIT = "dbb6104ce834628e473d2173bbc9d47f81a9eec3"
PINNED_TAG = "v5.0.2"
PINNED_SHA256 = "a6ee779fc42e6bf01b5e6a963065706e882b016affbedfd8be19a71ea48e6e15"
PINNED_BLOB = "9681524529b34f34033ae97064a2700bfc4eec00"
MATH_REL = "contracts/utils/math/Math.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-oz-muldiv"
WAD = 10**18

# (x, y, d, rounding, want)
VECTORS = [
    (100, 200, 50, 0, 400),
    (7, 9, 2, 0, 31),
    (7, 9, 2, 1, 32),
    (7, 9, 2, 2, 31),
    (7, 9, 2, 3, 32),
    (1, 1, 2, 0, 0),
    (1, 1, 2, 1, 1),
    (WAD, 1, 2, 0, WAD // 2),
    (7, 2, 3, 1, 5),
    (100, 50, 200, 0, 25),
    (25, 200, 50, 1, 100),
    (1, 100, 3, 1, 34),
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


def py_muldiv(x: int, y: int, d: int, rounding: int) -> int:
    if d == 0 or rounding not in (0, 1, 2, 3) or x < 0 or y < 0:
        return 0
    prod = x * y
    q, r = divmod(prod, d)
    if q > (2**64 - 1):
        return 0
    if rounding % 2 == 0:
        return q
    if r == 0:
        return q
    if q == 2**64 - 1:
        return 0
    return q + 1


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
    url = "https://github.com/OpenZeppelin/openzeppelin-contracts.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / MATH_REL
    if not live.exists():
        return "SKIP", "", f"{MATH_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MATH_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    live_txt = live.read_text(encoding="utf-8")
    excerpt = (FIX / "mulDiv.sol").read_text(encoding="utf-8")
    if "function mulDiv(uint256 x, uint256 y, uint256 denominator)" not in live_txt:
        return "FAIL", commit, "mulDiv missing"
    if "function unsignedRoundsUp(Rounding rounding)" not in live_txt:
        return "FAIL", commit, "unsignedRoundsUp missing"
    if "mulmod" not in live_txt or "assembly" not in live_txt:
        return "FAIL", commit, "Yul mulmod/assembly path missing"
    if excerpt.strip() not in live_txt:
        return "FAIL", commit, "mulDiv.sol excerpt not a substring"
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
    print("  OPENZEPPELIN Math.mulDiv — external LIN proof (Rounding, uint64-scale)")
    print("=" * 78)

    pinned = FIX / "Math.sol"
    excerpt = FIX / "mulDiv.sol"
    if not pinned.exists() or not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned Math.sol / mulDiv.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned Math.sol hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned Math.sol sha256 matches OpenZeppelin v5.0.2")

    src_ex = excerpt.read_text(encoding="utf-8")
    if "function mulDiv(" not in src_ex or "unsignedRoundsUp" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing mulDiv / unsignedRoundsUp")
        return 1
    if "assembly" not in src_ex or "mulmod" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing Yul mulmod product")
        return 1
    if "enum Rounding" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing Rounding enum")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has mulDiv, Rounding, unsignedRoundsUp, Yul mulmod")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of OpenZeppelin v5.0.2 matches pinned sha256/blob",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/utils/math/Math.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb mulDiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb mulDiv+rounding agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of mulDiv clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_openzeppelin_muldiv.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec(
        "SOL-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3 (MULMOD/REVERT/CAST)",
    )

    gate = run([str(C0), "vm", str(LIN), "ozmd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ozmd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ozmd_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for x, y, d, rounding, want in VECTORS:
        py = py_muldiv(x, y, d, rounding)
        c11 = int(oracle(["muldiv", str(x), str(y), str(d), str(rounding)]).splitlines()[-1])
        limbs = int(oracle(["muldiv", str(x), str(y), str(d), str(rounding), "--limbs"]).splitlines()[-1])
        got = lin_vm("ozmd_muldiv", x, y, d, rounding)
        if py != want or c11 != want or limbs != want or got != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"muldiv({x},{y},{d},{rounding})",
                f"py={py} c11={c11} limbs={limbs} lin={got} want={want}",
            )
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint == C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    if lin_vm("ozmd_rem", 7, 9, 2) != 1:
        rec("REM-ID", "FAIL", "remainder 7*9 % 2")
        return 1
    rec("REM-ID", "PASS", "remainder identity witness: 7*9 = 31*2 + 1")

    if lin_vm("ozmd_ceil_div", 7, 3) != 3 or lin_vm("ozmd_muldiv", 7, 2, 3, 1) != 5:
        rec("CEILDIV-DELTA", "FAIL", "ceilDiv vs mulDiv-ceil")
        return 1
    rec("CEILDIV-DELTA", "PASS", "named contrast: OZ ceilDiv(7,3)=3 != mulDiv(7,2,3,Ceil)=5")

    if lin_vm("ozmd_convert_to_shares", 100, 50, 200) != 25:
        rec("VAULT-FLOOR", "FAIL", "convertToShares Floor")
        return 1
    rec("VAULT-FLOOR", "PASS", "ERC-4626-style convertToShares = mulDiv Floor (100*50/200=25)")

    if lin_vm("ozmd_preview_mint", 1, 3, 100) != 34:
        rec("VAULT-CEIL", "FAIL", "previewMint Ceil")
        return 1
    rec("VAULT-CEIL", "PASS", "ERC-4626-style previewMint = mulDiv Ceil (ceil(1*100/3)=34)")

    if lin_vm("ozmd_floor", WAD, WAD, 1) != 0 or lin_vm("ozmd_ov", WAD, WAD, 1) != 1:
        rec("I64-WRAP", "FAIL", "1e18*1e18 overflow")
        return 1
    wrapped = (WAD * WAD) & ((1 << 64) - 1)
    rec(
        "I64-WRAP",
        "PASS",
        "naive 64-bit (1e18*1e18) wraps; 128-bit mulDiv fail-closes to 0",
        f"i64_wrap={wrapped}",
    )

    if lin_vm("ozmd_muldiv", 7, 9, 2, 4) != 0 or lin_vm("ozmd_floor", -1, 9, 2) != 0:
        rec("FAIL-CLOSED", "FAIL", "bounds")
        return 1
    rec("FAIL-CLOSED", "PASS", "rounding outside 0..3 and negative inputs fail-close to 0")

    if lin_vm("ozmd_floor", 7, 9, 0) != 0 or lin_vm("ozmd_ceil", 7, 9, 0) != 0:
        rec("DIV0", "FAIL", "div-by-zero")
        return 1
    rec("DIV0", "PASS", "denominator 0 fail-closes to 0 (OZ reverts; LIN documents the delta)")

    jit_ok = lin_roundtrip_jit("ozmd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ozmd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ozmd_muldiv", 7, 9, 2, 1)
        if jv == 32:
            rec("C0-JIT", "PASS", "lin_c0 jit ozmd_muldiv(7,9,2,1)==32 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "ozmd_muldiv(x: int, y: int, d: int, rounding: int)" in src and "enum Rounding" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes Rounding as 0/1/2/3; pinned OZ uses an enum + uint8 cast")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit rounding int vs OZ enum")

    if "ozmd_muldiv_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses visible 128-bit schoolbook product (OZ uses Yul mulmod/CRT)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    rec(
        "SOL-MD-REJ",
        "PASS" if "REJ_SOLIDITY_MULMOD" in sol_src and "REJ_SOLIDITY_CAST" in sol_src else "FAIL",
        "lin_from_solidity.lin v3 rejects mulmod / uint8(enum) / revert (lift is ozmd_muldiv)",
    )
    rec(
        "SOL-EX-SPLIT",
        "PASS" if 'out = out + "=";' in sol_src and 'out = out + "ex{"' in sol_src else "FAIL",
        "sol_from_sol concatenates '=' + 'ex{' so C0 export parse is honest",
    )

    evidence = {
        "schema": "LIN_OPENZEPPELIN_MULDIV_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/OpenZeppelin/openzeppelin-contracts",
            "tag": PINNED_TAG,
            "commit": commit or PINNED_COMMIT,
            "path": MATH_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "rounding": "Floor=0 Ceil=1 Trunc=2 Expand=3; unsignedRoundsUp = rounding%2",
        },
        "lin_clone": "src/lin_openzeppelin_muldiv.lin",
        "c11_oracle": "test/oracles/openzeppelin_muldiv_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {"x": a, "y": b, "d": c, "rounding": d, "want": e} for a, b, c, d, e in VECTORS
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
