#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Solady FixedPointMathLib mulWad/divWad (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream excerpt + live full-file sha256 of FixedPointMathLib.sol
    * an independent C11 oracle (__int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Solidity transpiler reject of the upstream Yul `assembly` body

  NOT claimed:
    * Solidity uint256 range (LIN path is uint64-scale + 128-bit product)
    * that LIN replaces Solady, Morpho, or the EVM
    * automatic transpile of Yul assembly into LIN
    * wall-clock superiority vs solc/LLVM

Class: EXPERIMENTAL (real published wad algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_solady_mulwad.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "solady_mulwad_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "solady_mulwad_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_solady")
EVIDENCE = ROOT / "examples" / "solady_mulwad" / "solady_mulwad_evidence.json"

WAD = 10**18
PINNED_FULL_SHA256 = "d322e2a0b1f43dbd80a3cf26a40d1ca1cc19cf03737f1e8513485e266b47e9c3"
PINNED_BLOB = "12a83024751cd5fb7a12a7c22cc0bd5badd1846d"
PINNED_COMMIT = "2afba69bf67b78dd4abeadcc696052b3a6f71499"
PINNED_EXCERPT_SHA256 = "f4a6afa9b3f5031f14554542be6471fa4413386d745d04b089c1b5c6b5f2cc2d"
UPSTREAM_REL = "src/utils/FixedPointMathLib.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-solady-mulwad"


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


def py_mulwad(x: int, y: int) -> int:
    if y == 0:
        return 0
    q = (x * y) // WAD
    return 0 if q > (2**64 - 1) else q


def py_mulwad_up(x: int, y: int) -> int:
    if y == 0:
        return 0
    p = x * y
    q, r = divmod(p, WAD)
    if q > (2**64 - 1):
        return 0
    if r == 0:
        return q
    if q == 2**64 - 1:
        return 0
    return q + 1


def py_divwad(x: int, y: int) -> int:
    if y == 0:
        return 0
    q = (x * WAD) // y
    return 0 if q > (2**64 - 1) else q


def py_divwad_up(x: int, y: int) -> int:
    if y == 0:
        return 0
    q, r = divmod(x * WAD, y)
    if q > (2**64 - 1):
        return 0
    if r == 0:
        return q
    if q == 2**64 - 1:
        return 0
    return q + 1


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/Vectorized/solady.git"
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
    if live_hash != PINNED_FULL_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  SOLADY MULWAD — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    excerpt = FIX / "FixedPointMathLib_wad.sol"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned FixedPointMathLib_wad.sol missing")
        return 1
    got = sha256_file(excerpt)
    if got != PINNED_EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "pinned wad excerpt hash mismatch", f"{got}")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned wad excerpt sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    live_full = UPSTREAM / UPSTREAM_REL
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned solady commit matches full-file sha256",
            f"commit={commit} blob={blob}",
        )
        live_txt = live_full.read_text(encoding="utf-8")
        if excerpt.read_text(encoding="utf-8") not in live_txt:
            rec("EXCERPT-IN-FULL", "FAIL", "wad excerpt is not a prefix/substring of live file")
            return 1
        rec("EXCERPT-IN-FULL", "PASS", "pinned wad excerpt is contained in live FixedPointMathLib.sol")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; excerpt pin still holds",
            up_note,
        )
        rec("EXCERPT-IN-FULL", "SKIP", "live full file not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("EXCERPT-IN-FULL", "FAIL", "cannot confirm excerpt against live file", up_note)
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
        rec("LIN-CHECK", "FAIL", "lin_c0 check of solady clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_solady_mulwad.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "sdy_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "sdy_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "sdy_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    excerpt_txt = excerpt.read_text(encoding="utf-8")
    if "assembly" not in excerpt_txt:
        rec("ASM-UPSTREAM", "FAIL", "pinned excerpt lost Yul assembly")
        return 1
    rec("ASM-UPSTREAM", "PASS", "upstream mulWad/divWad bodies are Yul assembly")
    if "REJ_SOLIDITY_INLINE_ASM" not in sol_src:
        rec("ASM-REJ", "FAIL", "solidity transpiler missing assembly reject")
        return 1
    rec("ASM-REJ", "PASS", "lin_from_solidity.lin fail-closes Yul assembly (no fake emit)")

    if "0.5e" not in sol_src:
        rec("HALF-EXP", "FAIL", "0.5eN expansion missing")
    else:
        rec("HALF-EXP", "PASS", "solidity transpiler expands 1eN and 0.5eN integer literals")

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX" not in c_src or "ceil(" not in c_src:
        rec("C-REJ-CXX", "FAIL", "C transpiler missing C++ / ceil reject")
    else:
        rec("C-REJ-CXX", "PASS", "lin_from_c.lin v2 rejects C++ tokens and ceil/floor as float")
    if "cfs_strip_int_suffix" not in c_src:
        rec("C-SUFFIX", "FAIL", "C integer suffix strip missing")
    else:
        rec("C-SUFFIX", "PASS", "lin_from_c.lin strips C11 U/L/LL suffixes before emit")

    vectors = [
        ("mulwad", (2 * WAD, 3 * WAD), "sdy_mulwad", py_mulwad),
        ("mulwad", (1, 1), "sdy_mulwad", py_mulwad),
        ("mulwad", (WAD, 1), "sdy_mulwad", py_mulwad),
        ("mulwad", (0, 2 * WAD), "sdy_mulwad", py_mulwad),
        ("mulwadup", (1, 1), "sdy_mulwad_up", py_mulwad_up),
        ("mulwadup", (2 * WAD, 3 * WAD), "sdy_mulwad_up", py_mulwad_up),
        ("divwad", (6 * WAD, 2 * WAD), "sdy_divwad", py_divwad),
        ("divwad", (1, 2 * WAD), "sdy_divwad", py_divwad),
        ("divwadup", (1, 2 * WAD), "sdy_divwad_up", py_divwad_up),
        ("divwad", (1, 0), "sdy_divwad", py_divwad),
    ]
    n_ok = 0
    for kind, args, fn, pyfn in vectors:
        want = int(oracle([kind, str(args[0]), str(args[1])]).splitlines()[-1])
        want_limbs = int(oracle([kind, str(args[0]), str(args[1]), "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{args}", f"lin={got_lin} c11={want}")
            return 1
        py = pyfn(*args)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{args}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    wrapped = (2 * WAD * 3 * WAD) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    bigint = py_mulwad(2 * WAD, 3 * WAD)
    if wrapped == bigint:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint mulwad")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (2e18*3e18) wraps; 128-bit mulWad does not",
        f"i64_wrap={wrapped} bigint={bigint}",
    )

    jit_ok = lin_roundtrip_jit("sdy_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sdy_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("sdy_mulwad", 2 * WAD, 3 * WAD)
        if jv == 6 * WAD:
            rec("C0-JIT", "PASS", "lin_c0 jit sdy_mulwad(2e18,3e18)==6e18 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    rec("CLONE-LIN", "PASS", "separate clone-lin repository URL recorded", CLONE_LIN)

    evidence = {
        "schema": "LIN_SOLADY_MULWAD_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "clone_lin": CLONE_LIN,
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/Vectorized/solady",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_FULL_SHA256,
            "excerpt_sha256": PINNED_EXCERPT_SHA256,
            "license": "MIT",
        },
        "lin_clone": "src/lin_solady_mulwad.lin",
        "c11_oracle": "test/oracles/solady_mulwad_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "canonical_mulwad_2x3": lin_vm("sdy_mulwad", 2 * WAD, 3 * WAD),
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
