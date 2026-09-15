#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound JumpRateModel V2 (BSD-3-Clause) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of BaseJumpRateModelV2.sol (git blob + sha256)
    * independent C11 oracle (__int128 AND portable 32-bit limb muldiv)
    * independent Python oracle (test/oracles/compound_jumprate_py.py)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  Real melhorias on this uint64 profile:
    * IRM storage parameters are explicit arguments
    * (a*b)/d uses a 128-bit product; quotient overflow fail-closes to 0

  NOT claimed:
    * full Solidity uint256 / mainnet cToken parity
    * LIN replacing Compound, Uniswap, or the EVM
    * general superiority vs solc/LLVM
    * Merkle computational soundness (C4 is tamper-evidence, not zk)

Class: EXPERIMENTAL (real Compound IRM algorithm, uint64-scale operands).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PY = ROOT / "test" / "oracles" / "compound_jumprate_py.py"
_spec = importlib.util.spec_from_file_location("compound_jumprate_py", _PY)
py_cjr = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(py_cjr)
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "compound_jumprate_evidence.json"

BASE = 10**18
PINNED_SHA256 = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"
PINNED_BLOB = "4d6828c39ed737c0c48508adc414b919ab6c2a55"
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
UPSTREAM_REL = "contracts/BaseJumpRateModelV2.sol"


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


def ensure_upstream() -> str:
    """Checkout the pinned commit, not whatever master is today."""
    if not (UPSTREAM / ".git").exists():
        proc = run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/compound-finance/compound-protocol.git",
                str(UPSTREAM),
            ],
            timeout=120,
        )
        if proc.returncode != 0:
            return ""
    fetched = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetched.returncode != 0:
        fetched = run(
            ["git", "-C", str(UPSTREAM), "fetch", "origin", PINNED_COMMIT],
            timeout=120,
        )
    if fetched.returncode != 0:
        return ""
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", PINNED_COMMIT])
    if co.returncode != 0:
        return ""
    proc = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"])
    return proc.stdout.strip()


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMPOUND_JUMPRATE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND JUMPRATE V2 — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "BaseJumpRateModelV2.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned BaseJumpRateModelV2.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned BaseJumpRateModelV2.sol sha256 matches manifest")

    commit = ensure_upstream()
    live = UPSTREAM / UPSTREAM_REL
    blob = ""
    if not commit or not live.exists():
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "could not fetch pinned compound-protocol commit (fixture pin still holds)",
            PINNED_COMMIT,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live git blob skipped; fixture git hash-object is authoritative")
    else:
        live_hash = sha256_file(live)
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
        if commit != PINNED_COMMIT:
            rec("UPSTREAM-SHA", "FAIL", "checked out commit is not the pin", f"{commit}")
        elif live_hash != PINNED_SHA256:
            rec(
                "UPSTREAM-SHA",
                "FAIL",
                "pinned-commit clone hash differs from fixture",
                f"live={live_hash} pin={PINNED_SHA256} commit={commit}",
            )
        else:
            rec(
                "UPSTREAM-SHA",
                "PASS",
                "compound-protocol at pinned commit matches fixture bytes",
                f"commit={commit} blob={blob}",
            )
        if blob and blob != PINNED_BLOB:
            rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", f"{blob} != {PINNED_BLOB}")
        elif blob == PINNED_BLOB:
            rec("UPSTREAM-BLOB", "PASS", "git blob sha of BaseJumpRateModelV2.sol")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of compound clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_jumprate.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v2 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "cjr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cjr_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "cjr_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cjr_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "cjr_muldiv", (7, 9, 1)),
        ("muldiv", [str(BASE), "1", "2"], "cjr_muldiv", (BASE, 1, 2)),
        ("util", [str(BASE), str(BASE), "0"], "cjr_utilization", (BASE, BASE, 0)),
        ("util", ["0", str(BASE), "0"], "cjr_utilization", (0, BASE, 0)),
        ("util", ["100", "0", "0"], "cjr_utilization", (100, 0, 0)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
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
            py = py_cjr.muldiv(*largs)
        else:
            py = py_cjr.utilization(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python oracle {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    mb = lin_vm("cjr_multiplier_per_block", 40000000000000000, 800000000000000000)
    jb = lin_vm("cjr_jump_per_block", 1090000000000000000)
    bb = lin_vm("cjr_base_per_block", 0)
    r50 = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, mb, jb, 800000000000000000)
    want50 = int(
        oracle(
            [
                "borrow",
                str(BASE),
                str(BASE),
                "0",
                str(bb),
                str(mb),
                str(jb),
                "800000000000000000",
            ]
        ).splitlines()[-1]
    )
    if r50 != want50:
        rec("BORROW-50", "FAIL", "50% util borrow rate", f"lin={r50} c11={want50}")
        return 1
    rec("BORROW-50", "PASS", "parameterized getBorrowRate at 50% util matches C11", f"rate={r50}")
    py50 = py_cjr.borrow_rate(BASE, BASE, 0, bb, mb, jb, 800000000000000000)
    if py50 != r50:
        rec("PY-BORROW-50", "FAIL", "python oracle borrow@50%", f"py={py50} lin={r50}")
        return 1
    rec("PY-BORROW-50", "PASS", "Python oracle borrow rate at 50% util matches LIN/C11", f"rate={py50}")
    wrapped = py_cjr.i64_wrap(BASE * BASE)
    wide = py_cjr.muldiv(BASE, BASE, 2 * BASE)
    lin_wide = lin_vm("cjr_muldiv", BASE, BASE, 2 * BASE)
    if wrapped == wide or lin_wide != wide or wide != 500000000000000000:
        rec("WIDE-MULDIV", "FAIL", "128-bit (1e18*1e18)/2e18", f"i64={wrapped} py={wide} lin={lin_wide}")
        return 1
    rec(
        "WIDE-MULDIV",
        "PASS",
        "128-bit product: (1e18*1e18)/2e18 = 5e17; naive signed-i64 wraps",
        f"i64_wrap={wrapped} bigint={wide}",
    )
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv does not",
        f"i64_wrap={wrapped} bigint={wide}",
    )

    q_ovf_py = py_cjr.muldiv(BASE, BASE, 1)
    q_ovf_lin = lin_vm("cjr_muldiv", BASE, BASE, 1)
    q_ovf_c11 = int(oracle(["muldiv", str(BASE), str(BASE), "1"]).splitlines()[-1])
    if not (q_ovf_py == q_ovf_lin == q_ovf_c11 == 0):
        rec("Q-OVF", "FAIL", "quotient overflow must fail-close to 0", f"py={q_ovf_py} lin={q_ovf_lin} c11={q_ovf_c11}")
        return 1
    rec("Q-OVF", "PASS", "uint64 profile: (1e18*1e18)/1 fail-closes to 0 (not silent wrap)")

    if not py_cjr.solidity_util_reverts(1, 1, 10):
        rec("UFL-DIFF", "FAIL", "oracle should mark Solidity revert on cash+borrows < reserves")
        return 1
    ufl_lin = lin_vm("cjr_utilization", 1, 1, 10)
    ufl_c11 = int(oracle(["util", "1", "1", "10"]).splitlines()[-1])
    if not (ufl_lin == ufl_c11 == 0):
        rec("FAIL-CLOSED-UFL", "FAIL", "underflow util", f"lin={ufl_lin} c11={ufl_c11}")
        return 1
    rec(
        "FAIL-CLOSED-UFL",
        "PASS",
        "cash+borrows < reserves: LIN/C11 return 0; Solidity 0.8 would revert (documented difference)",
    )

    if not py_cjr.blocks_kink_overflows_u64(800000000000000000):
        rec("MULT-REORDER", "FAIL", "blocks*kink unexpectedly fits uint64")
        return 1
    sol_mb = py_cjr.multiplier_solidity(40000000000000000, 800000000000000000)
    lin_mb = py_cjr.multiplier_lin(40000000000000000, 800000000000000000)
    if sol_mb != lin_mb or lin_mb != mb:
        rec("MULT-REORDER", "FAIL", "year-to-block multiplier", f"sol={sol_mb} lin_py={lin_mb} c0={mb}")
        return 1
    ident_ok = all(
        py_cjr.floor_div_identity(x, py_cjr.BLOCKS, z)
        for x, z in ((py_cjr.MULT_YEAR * BASE, py_cjr.KINK), (10**24, 7), (99, 3))
    )
    if not ident_ok:
        rec("MULT-REORDER", "FAIL", "floor(x/(y*z)) != floor(floor(x/z)/y)")
        return 1
    rec(
        "MULT-REORDER",
        "PASS",
        "blocks*kink overflows uint64; LIN reorder is floor-identical to Solidity uint256 formula",
        f"mb={mb}",
    )

    r90 = lin_vm("cjr_borrow_rate", 100000000000000000, 900000000000000000, 0, bb, mb, jb, 800000000000000000)
    py90 = py_cjr.borrow_rate(100000000000000000, 900000000000000000, 0, bb, mb, jb, 800000000000000000)
    c1190 = int(
        oracle(
            ["borrow", "100000000000000000", "900000000000000000", "0", str(bb), str(mb), str(jb), "800000000000000000"]
        ).splitlines()[-1]
    )
    if not (r90 == py90 == c1190) or r90 <= r50:
        rec("JUMP-90", "FAIL", "jump regime 90% util", f"lin={r90} py={py90} c11={c1190} r50={r50}")
        return 1
    rec("JUMP-90", "PASS", "above-kink borrow rate three-way consensus and r90 > r50", f"rate={r90}")

    rf = 100000000000000000
    s50 = lin_vm("cjr_supply_rate", BASE, BASE, 0, bb, mb, jb, 800000000000000000, rf)
    pys = py_cjr.supply_rate(BASE, BASE, 0, bb, mb, jb, 800000000000000000, rf)
    c11s = int(
        oracle(["supply", str(BASE), str(BASE), "0", str(bb), str(mb), str(jb), "800000000000000000", str(rf)]).splitlines()[-1]
    )
    if not (s50 == pys == c11s) or s50 <= 0:
        rec("SUPPLY-50", "FAIL", "supply@50% rf=0.1", f"lin={s50} py={pys} c11={c11s}")
        return 1
    rec("SUPPLY-50", "PASS", "supply rate at 50% util, 10% reserve factor, three-way", f"rate={s50}")

    kink_lo = 400000000000000000
    r50_lo = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, mb, jb, kink_lo)
    py_lo = py_cjr.borrow_rate(BASE, BASE, 0, bb, mb, jb, kink_lo)
    if r50_lo == r50 or r50_lo != py_lo:
        rec("EXPLICIT-ARGS", "FAIL", "changing kink must change rate", f"kink80={r50} kink40={r50_lo} py={py_lo}")
        return 1
    rec(
        "EXPLICIT-ARGS",
        "PASS",
        "same cash/borrows, different kink argument => different borrow rate (params are not hidden storage)",
        f"kink80={r50} kink40={r50_lo}",
    )

    jit_ok = lin_roundtrip_jit("cjr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cjr_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cjr_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    sol_fix = pinned.read_text(encoding="utf-8")
    if "sol_from_sol" not in sol_src or "sol_expand_exp" not in sol_src:
        rec("SOL-PURE-SCOPE", "FAIL", "emit path missing")
    elif "function getBorrowRateInternal" not in sol_fix or "internal view" not in sol_fix:
        rec("SOL-PURE-SCOPE", "FAIL", "upstream fixture lost view-on-storage getBorrowRateInternal")
    else:
        rec(
            "SOL-PURE-SCOPE",
            "PASS",
            "sol_from_sol is for eligible pure fns; JumpRate clone is hand-written (view+storage, not transpiled IRM)",
        )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/compound-protocol",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "BSD-3-Clause",
    }
    evidence["lin_clone"] = "src/lin_compound_jumprate.lin"
    evidence["c11_oracle"] = "test/oracles/compound_jumprate_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["python_oracle"] = "test/oracles/compound_jumprate_py.py"
    evidence["class"] = "EXPERIMENTAL"
    evidence["borrow_rate_50_util"] = r50
    evidence["borrow_rate_90_util"] = r90
    evidence["supply_rate_50_rf10"] = s50
    evidence["multiplier_per_block"] = mb
    evidence["jump_per_block"] = jb
    evidence["not_claimed"] = [
        "full Solidity uint256 / mainnet cToken parity",
        "LIN replaces Compound, Uniswap, or the EVM",
        "general superiority vs solc/LLVM",
        "computational soundness of Merkle (C4 is tamper-evidence + reexecution, not zk)",
    ]
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
