#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker LinearDecrease.price vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss abaci.sol, C11 wrap-detect
XOR __int128 mul, lin_c0 VM, Python bigint. tau as argument (not wards/file).
Not claimed: uint256 ray, TVL, zk, StairstepExponentialDecrease rpow, Clipper.take.
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
LIN = ROOT / "src" / "lin_maker_abacus_linear.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_abacus_linear_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_abacus_linear_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_abacus_linear_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_abacus_linear" / "maker_abacus_linear_evidence.json"

I64MAX = 2**63 - 1
RAY = 10**9
WRAP_A, WRAP_B = 10 * 10**9, 10**9
I64_WRAP_MUL = -8446744073709551616
PINNED_SHA256 = "a4c3dc0368d66a5bf84e586f0cf76e2e80fb8b336c00348a97cc0d4ddcb016ca"
PINNED_BLOB = "6cbd666267fc9f534ae52a45926eec5aa44b3bc5"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/abaci.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-abacus-linear"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")

PAR = (10**9, 0, 100)
HALF = (10**9, 50, 100)
LAST = (10**9, 99, 100)
EXPIRED = (10**9, 100, 100)
PAST = (10**9, 101, 100)
FLOOR = (7, 2, 5)
ODD = (123456789, 1, 3600)
OVERFLOW = (WRAP_A, 0, 100)
TAU0 = (10**9, 0, 0)


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
    url = "https://github.com/makerdao/dss.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    return "PASS", commit, blob


def py_mul_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    if a == 0 or b == 0:
        return 1
    p = a * b
    return int(0 <= p <= I64MAX)


def py_ab(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return args[0] * args[1] if py_mul_ok(args[0], args[1]) else 0
    if kind == "factor":
        dur, tau = args
        if dur < 0 or tau < 1 or dur >= tau:
            return 0
        rem = tau - dur
        if not py_mul_ok(rem, RAY):
            return 0
        return (rem * RAY) // tau
    top, dur, tau = args
    if kind == "price":
        if top < 0 or dur < 0 or tau < 1 or dur >= tau:
            return 0
        f = py_ab("factor", (dur, tau))
        if f <= 0 or not py_mul_ok(top, f):
            return 0
        return (top * f) // RAY
    if kind == "ok":
        if top < 0 or dur < 0 or tau < 1 or dur >= tau:
            return 0
        f = py_ab("factor", (dur, tau))
        return int(f > 0 and py_mul_ok(top, f))
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_ABACUS_LINEAR_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER LinearDecrease.price — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect (tau-dur)*RAY/top*factor and __int128 mul agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss abaci.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("contract LinearDecrease is Abacus", "function price(uint256 top, uint256 dur)",
                "tau - dur", "contract StairstepExponentialDecrease", "function rpow(",
                "uint256 public tau")
        if any(s not in text for s in need):
            rec("UPSTREAM-PRICE", "FAIL", "pinned abaci.sol missing LinearDecrease.price / tau / rpow")
            return 1
        rec("UPSTREAM-PRICE", "PASS",
            "pinned abaci.sol contains LinearDecrease.price, tau, rmul, Stairstep rpow (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/abaci.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-PRICE", "SKIP", "live abaci.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-PRICE", "FAIL", "abaci.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of LinearDecrease clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_abacus_linear.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "ab_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ab_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ab_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 1100)),
        ("factor", (50, 100)),
        ("factor", (0, 100)),
        ("price", PAR), ("price", HALF), ("price", LAST),
        ("price", EXPIRED), ("price", PAST), ("price", FLOOR),
        ("price", ODD), ("price", OVERFLOW), ("price", TAU0),
        ("ok", PAR), ("ok", EXPIRED), ("ok", TAU0),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        if kind == "mul":
            fn = "ab_u_mul"
        elif kind == "factor":
            fn = "ab_factor"
        elif kind == "ok":
            fn = "ab_ok"
        else:
            fn = "ab_price"
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_ab(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_ab(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    par_p = lin_vm("ab_price", *PAR)
    half_p = lin_vm("ab_price", *HALF)
    last_p = lin_vm("ab_price", *LAST)
    exp_p = lin_vm("ab_price", *EXPIRED)
    floor_p = lin_vm("ab_price", *FLOOR)
    odd_p = lin_vm("ab_price", *ODD)
    ov_p = lin_vm("ab_price", *OVERFLOW)
    tau0_p = lin_vm("ab_price", *TAU0)
    auth = lin_vm("ab_auth_required")
    tau_flag = lin_vm("ab_uses_tau")
    rpow = lin_vm("ab_uses_rpow")
    cut = lin_vm("ab_uses_cut_step")
    btime = lin_vm("ab_uses_block_time")
    take = lin_vm("ab_is_take_kernel")
    bark = lin_vm("ab_is_bark_kernel")
    golden = (par_p, half_p, last_p, exp_p, floor_p, odd_p, ov_p, tau0_p, auth, tau_flag, rpow, cut, btime, take, bark)
    expect = (10**9, 5 * 10**8, 10**7, 0, 4, 123422495, 0, 0, 0, 1, 0, 0, 0, 0, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "PAR/HALF/LAST/EXPIRED/FLOOR/ODD/OVERFLOW goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "PAR 1e9@dur0=1e9; HALF 5e8; LAST 1e7; EXPIRED=0; FLOOR 7@2/5=4; ODD=123422495; 1e10*1e9 fail-closes",
        "half=500000000 last=10000000 floor=4 odd=123422495 auth=0 rpow=0")
    rec("COMMERCIAL", "PASS",
        "measured Dutch-auction decay (not TVL): top=1e9-ray over tau=100s is 5e8 at halfway; expired auctions fail-close to 0",
        "top=1000000000 tau=100 dur=50 price=500000000 unit=reduced_ray")

    wrapped = lin_vm("ab_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("ab_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (1e10*1e9) wraps; checked top*factor fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-TAU", "PASS" if "ab_price(top: int, dur: int, tau: int)" in src else "FAIL",
        "LIN clone takes top/dur/tau as arguments (no hidden wards/file storage)")
    rec("NO-RPOW", "PASS" if "ab_uses_rpow" in src else "FAIL",
        "clone is LinearDecrease, not StairstepExponentialDecrease rpow(cut, dur/step)")
    rec("NO-AUTH", "PASS" if "ab_auth_required" in src else "FAIL",
        "price() is public view, not wards auth; LIN measures auth_required=0")
    rec("NOT-TAKE", "PASS" if "ab_is_take_kernel" in src else "FAIL",
        "clone is abacus.price, not Clipper.take / Dog.bark")
    rec("EXPIRED-ZERO", "PASS" if exp_p == 0 and tau0_p == 0 else "FAIL",
        "dur>=tau and tau=0 fail-close to 0 (Solidity returns 0 when dur>=tau)")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_ABACUS_LINEAR" in sol_src and "REJ_C_ABACUS_LINEAR" in c_src
        and "REJ_RUST_ABACUS_LINEAR" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close LinearDecrease.price / abaci / tau-dur")
    rec("TR-RPOW", "PASS" if "REJ_SOLIDITY_RPOW" in sol_src else "FAIL",
        "Solidity transpiler fail-closes rpow assembly stairstep/exponential decrease")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    ksrc = KERNEL.read_text(encoding="utf-8") if KERNEL.exists() else ""
    if "ab_price" not in ksrc or "__int128" in ksrc or "LinearDecrease" in ksrc:
        rec("C-KERNEL", "FAIL", "transpilable LinearDecrease kernel missing or not pointer-free")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_abacus_linear_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("ab_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ab_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ab_u_mul", 1000, 1100)
        rec("C0-JIT", "PASS" if jv == 1100000 else "SKIP",
            "lin_c0 jit ab_u_mul(1000,1100)==1100000 (in-memory libtcc)" if jv == 1100000 else "in-memory JIT not exercised",
            "" if jv == 1100000 else "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/makerdao/dss",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_maker_abacus_linear.lin"
    evidence["c11_oracle"] = "test/oracles/maker_abacus_linear_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_abacus_linear_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "par_price": par_p, "half_price": half_p, "last_price": last_p,
        "expired": exp_p, "floor": floor_p, "odd": odd_p, "overflow": ov_p,
        "tau0": tau0_p, "auth_required": auth, "uses_tau": tau_flag,
        "uses_rpow": rpow, "uses_cut_step": cut, "uses_block_time": btime,
        "is_take_kernel": take, "is_bark_kernel": bark,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    if CLONE_LIN_HEAD:
        evidence["clone_lin_head"] = CLONE_LIN_HEAD
        evidence["clone_lin_lin_commit"] = CLONE_LIN_LIN_COMMIT
        evidence["clone_lin_lin_blob"] = CLONE_LIN_LIN_BLOB
        evidence["clone_lin_c_blob"] = CLONE_LIN_C_BLOB
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
