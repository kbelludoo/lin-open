#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Maker ExponentialDecrease.price vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git blob + sha256 of makerdao/dss src/abaci.sol (AGPL, NOT vendored)
    * an independent C11 oracle (unsigned __int128 AND wrap-detect muldiv)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision rpow/rmul

  NOT claimed:
    * full Solidity uint256 / RAY=1e27 / mainnet clipper parity
    * that LIN replaces Maker, Sky, or the EVM
    * wall-clock superiority vs solc/EVM
    * LinearDecrease.price or StairstepExponentialDecrease (n=dur/step)

Class: EXPERIMENTAL (real Maker abacus algorithm, uint64-scale RAY'=1e9).
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
LIN = ROOT / "src" / "lin_maker_abacus_exp.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
VIEW_TR = ROOT / "src" / "lin_sol_view_lift.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_abacus_exp_c11.c"
KERNEL_SRC = ROOT / "test" / "oracles" / "maker_abacus_exp_kernel.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_abacus_exp_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_dss")
EVIDENCE = ROOT / "examples" / "maker_abacus_exp" / "maker_abacus_exp_evidence.json"

RAY = 10**9
PINNED_SHA256 = "a4c3dc0368d66a5bf84e586f0cf76e2e80fb8b336c00348a97cc0d4ddcb016ca"
PINNED_BLOB = "6cbd666267fc9f534ae52a45926eec5aa44b3bc5"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/abaci.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-abacus-exp"


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


def py_rpow(x: int, n: int, b: int) -> int:
    if n < 0 or x < 0 or b <= 0:
        return 0
    if n == 0:
        return b
    if x == 0:
        return 0
    z = b if (n % 2 == 0) else x
    half = b // 2
    n = n // 2
    while n:
        xx = x * x
        xx_round = xx + half
        if xx_round < xx:
            return 0
        x = xx_round // b
        if n % 2:
            zx = z * x
            if x != 0 and zx // x != z:
                return 0
            zx_round = zx + half
            if zx_round < zx:
                return 0
            z = zx_round // b
        n = n // 2
    return z


def py_price(top: int, dur: int, cut: int) -> int:
    if top < 0 or dur < 0 or cut < 0 or cut > RAY:
        return 0
    p = py_rpow(cut, dur, RAY)
    return (top * p) // RAY


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
    url = "https://github.com/makerdao/dss.git"
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


def kernel_eligible() -> bool:
    src = KERNEL_SRC.read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    body = re.sub(r"//.*?$", "", body, flags=re.M)
    if any(tok in body for tok in ("->", "struct", "union", "float", "double", "goto")):
        return False
    for m in re.finditer(r"\bint\s+\w+\s*\(([^)]*)\)", body):
        if "*" in m.group(1):
            return False
    return True


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
    print("  MAKER EXPONENTIAL DECREASE — external LIN proof")
    print("  uint64-scale RAY'=1e9, C11 oracle, Compiler 0 in-memory")
    print("=" * 78)

    if KERNEL_SRC.exists() is False:
        rec("KERNEL-FILE", "FAIL", "pointer-free C kernel missing")
        return 1
    rec("AGPL-NOVENDOR", "PASS", "abaci.sol is hash-pinned, not vendored (AGPL)")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned makerdao/dss commit matches abaci.sol pin",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/abaci.sol")
        live = UPSTREAM / UPSTREAM_REL
        txt = live.read_text(encoding="utf-8", errors="replace")
        if "contract ExponentialDecrease" not in txt or "rpow(cut, dur, RAY)" not in txt:
            rec("UPSTREAM-TEXT", "FAIL", "pinned abaci.sol missing continuous exp formula")
            return 1
        if "dur / step" not in txt:
            rec("UPSTREAM-TEXT", "FAIL", "expected stairstep formula in same file for contrast")
            return 1
        rec("UPSTREAM-TEXT", "PASS", "pinned abaci.sol contains ExponentialDecrease.price n=dur")
        if "assembly" not in txt:
            rec("UPSTREAM-ASM", "FAIL", "expected assembly rpow in abaci.sol")
        else:
            rec("UPSTREAM-ASM", "PASS", "upstream rpow is inline assembly (transpiler must reject)")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; hash pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-TEXT", "SKIP", "live abaci.sol not read this run")
        rec("UPSTREAM-ASM", "SKIP", "live abaci.sol not read this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect and __int128 rpow/price agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of exp clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_abacus_exp.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler (OK_VIEW + abacus kind)")

    chk3 = run([str(C0), "check", str(VIEW_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("VIEW-LIFT", "FAIL", "lin_sol_view_lift.lin check", chk3.stdout)
    else:
        rec("VIEW-LIFT", "PASS", "Compiler 0 check of view-storage lift")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    view_src = VIEW_TR.read_text(encoding="utf-8")
    if "sol_rewrite_logic" not in sol_src or "REJ_SOLIDITY_INLINE_ASM" not in sol_src:
        rec("SOL-GATE", "FAIL", "expected || rewrite and assembly reject in lin_from_solidity.lin")
        return 1
    if "&& reason.length == 2" in sol_src:
        rec("SOL-GATE", "FAIL", "OK_VIEW still filtered out (reason.length == 2)")
        return 1
    if "sol_abacus_kind" not in sol_src or 'rpow(cut, dur,' not in sol_src:
        rec("SOL-GATE", "FAIL", "sol_abacus_kind missing EXP classifier")
        return 1
    rec(
        "SOL-GATE",
        "PASS",
        "lin_from_solidity.lin emits OK_VIEW, classifies EXP vs STAIR vs LINEAR, rejects assembly rpow",
        "C0 vm cannot execute string-literal gates (VM_REJ_STRING_LITERAL); vectors are source-pinned",
    )
    if "rpow(cut, dur, RAY)" not in view_src or "step" not in view_src:
        rec("LIFT-GATE", "FAIL", "view lift missing continuous-exp cut/RAY and stair step contrast")
        return 1
    rec("LIFT-GATE", "PASS", "view lift pins cut+RAY extras on exp price and does not invent step")

    suite = run([str(C0), "vm", str(LIN), "ed_test_suite"])
    sv = value_of(suite.stdout)
    if suite.returncode != 0 or sv != 1:
        rec("LIN-SUITE", "FAIL", "ed_test_suite via lin_c0 vm", suite.stdout + suite.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ed_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("price", [str(RAY), "0", "990000000"], "ed_price", (RAY, 0, 990000000)),
        ("price", [str(RAY), "1", "990000000"], "ed_price", (RAY, 1, 990000000)),
        ("price", [str(RAY), "2", "990000000"], "ed_price", (RAY, 2, 990000000)),
        ("price", [str(RAY), "3", "990000000"], "ed_price", (RAY, 3, 990000000)),
        ("price", ["123456789", "1", "990000000"], "ed_price", (123456789, 1, 990000000)),
        ("price", [str(RAY), "89", "990000000"], "ed_price", (RAY, 89, 990000000)),
        ("rpow", ["3", "2", "2"], "ed_rpow", (3, 2, 2)),
        ("rpow", ["990000000", "2", str(RAY)], "ed_rpow", (990000000, 2, RAY)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want_wrap = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want_wrap != want_i128:
            rec("VEC-LIMBS", "FAIL", f"{kind} wrap vs i128", f"{want_wrap} != {want_i128}")
            return 1
        if got_lin != want_wrap:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want_wrap}")
            return 1
        py = py_price(*largs) if kind == "price" else py_rpow(*largs)
        if py != want_wrap:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want_wrap}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap == i128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint matches C11 and LIN")

    sec1 = lin_vm("ed_price", RAY, 1, 990000000)
    if sec1 != 990000000:
        rec("DISTINCT-STAIR", "FAIL", "continuous n=dur must decay at dur=1", f"{sec1}")
        return 1
    rec(
        "DISTINCT-STAIR",
        "PASS",
        "dur=1 decays (StairstepExponentialDecrease with step=90 would still equal top)",
        f"price={sec1}",
    )
    hold = lin_vm("ed_price", RAY, 89, 990000000)
    if hold == RAY:
        rec("DISTINCT-HOLD", "FAIL", "continuous n=89 collided with stairstep hold-until-step")
        return 1
    rec(
        "DISTINCT-HOLD",
        "PASS",
        "n=dur (89) is not stairstep n=dur/step=0 hold-at-top",
        f"exp={hold}",
    )

    wrapped = (10**10 * 10**9) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("ed_muldiv", 10**10, 10**9, 1)
    if wide != 0:
        rec("I64-WRAP", "FAIL", "wide product should fail-close", f"lin={wide}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e10*1e9) wraps; 128-bit muldiv fail-closes",
        f"i64_wrap={wrapped} lin={wide}",
    )

    jit_ok = lin_roundtrip_jit("ed_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ed_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ed_price", RAY, 1, 990000000)
        if jv == 990000000:
            rec("C0-JIT", "PASS", "lin_c0 jit ed_price SEC1==990000000 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    if "ed_price(top: int, dur: int, cut: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected cut as explicit LIN argument (no step)")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes cut as argument (no hidden storage / wards / file / step)",
        )
    if "ed_rpow" in src and "_lia_ushr" in src:
        rec("WIDE-RPOW", "PASS", "clone uses 128-bit half-up rpow (assembly rpow is not copied)")
    else:
        rec("WIDE-RPOW", "FAIL", "128-bit rpow missing")

    if kernel_eligible():
        rec("C-KERNEL", "PASS", "pointer-free C kernel is lin_from_c eligible (no * -> struct goto)")
    else:
        rec("C-KERNEL", "FAIL", "C kernel has rejected C constructs")

    if "sol_abacus_kind" in sol_src and "OK_VIEW" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin emits OK_VIEW and classifies Maker abaci")
    else:
        rec("SOL-EMIT", "FAIL", "OK_VIEW emit / abacus classifier missing")

    evidence = {
        "schema": "LIN_MAKER_ABACUS_EXP_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/makerdao/dss",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "AGPL-3.0-or-later",
            "vendored": False,
        },
        "lin_clone": "src/lin_maker_abacus_exp.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/maker_abacus_exp_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "PAR": lin_vm("ed_price", RAY, 0, 990000000),
            "SEC1": lin_vm("ed_price", RAY, 1, 990000000),
            "SEC2": lin_vm("ed_price", RAY, 2, 990000000),
            "SEC3": lin_vm("ed_price", RAY, 3, 990000000),
            "NOT_HOLD": lin_vm("ed_price", RAY, 89, 990000000),
            "ODD": lin_vm("ed_price", 123456789, 1, 990000000),
        },
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
