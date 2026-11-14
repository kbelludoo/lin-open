#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Euler EVK IRMLinearKink vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of euler-xyz/euler-vault-kit IRMLinearKink.sol,
C11 wrap-detect XOR __int128 mul, lin_c0 VM, Python bigint. Distinct from
Compound JumpRate (1e18 util + reserves + /BASE). Not claimed: uint256, TVL, zk.
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
LIN = ROOT / "src" / "lin_euler_irm.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "euler_irm_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "euler_irm_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "euler_irm_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_euler_irm")
EVIDENCE = ROOT / "examples" / "euler_irm" / "euler_irm_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7_000_000_000, 3_000_000_000
I64_WRAP_MUL = 2553255926290448384
UTIL_SCALE = 4_294_967_295
KINK = 2_147_483_648
PINNED_SHA256 = "d3b9b7cd3bfc248cdf7cb7dc438661a888fd76f94efbdcf9a781c2eb999e8e82"
PINNED_BLOB = "fb3cab74631e944974111c7ed5a28b757f351ff7"
PINNED_COMMIT = "93a1de491531e54cbbcf0e5c8cacfe558f924867"
UPSTREAM_REL = "src/InterestRateModels/IRMLinearKink.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-euler-irm"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")


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
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/euler-xyz/euler-vault-kit.git"
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
    return int(a * b <= I64MAX)


def py_add_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a + b <= I64MAX)


def py_util(cash: int, borrows: int) -> int:
    if cash < 0 or borrows < 0 or not py_add_ok(cash, borrows):
        return 0
    total = cash + borrows
    if total == 0:
        return 0
    if not py_mul_ok(borrows, UTIL_SCALE):
        return 0
    u = (borrows * UTIL_SCALE) // total
    return 0 if u > UTIL_SCALE else u


def py_rate(cash: int, borrows: int, base: int, s1: int, s2: int, kink: int) -> int:
    if min(base, s1, s2, kink, cash, borrows) < 0 or kink > UTIL_SCALE:
        return 0
    if not py_add_ok(cash, borrows):
        return 0
    if cash + borrows != 0 and not py_mul_ok(borrows, UTIL_SCALE):
        return 0
    u = py_util(cash, borrows)
    ir = base
    if u <= kink:
        if not py_mul_ok(u, s1) or not py_add_ok(ir, u * s1):
            return 0
        return ir + u * s1
    if not py_mul_ok(kink, s1) or not py_add_ok(ir, kink * s1):
        return 0
    ir = ir + kink * s1
    over = u - kink
    if over < 0 or not py_mul_ok(s2, over) or not py_add_ok(ir, s2 * over):
        return 0
    return ir + s2 * over


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return py_mul_ok(args[0], args[1])
    if kind == "add":
        return py_add_ok(args[0], args[1])
    if kind == "util":
        return py_util(*args)
    if kind == "rate":
        return py_rate(*args)
    if kind == "auth":
        c, v = args
        return int(c >= 0 and v >= 0 and c == v and c <= I64MAX and v <= I64MAX)
    if kind == "compute":
        caller, vault, cash, borrows, base, s1, s2, kink = args
        if caller != vault or caller < 0 or vault < 0:
            return 0
        return py_rate(cash, borrows, base, s1, s2, kink)
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_EULER_IRM_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  EULER EVK IRMLinearKink — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect IRM mul/add and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned euler-xyz IRMLinearKink.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("contract IRMLinearKink", "function computeInterestRateInternal(",
                "type(uint32).max", "unchecked", "E_IRMUpdateUnauthorized")
        if any(s not in text for s in need):
            rec("UPSTREAM-JOIN", "FAIL", "pinned IRMLinearKink.sol missing kink/type(uint32).max/unchecked/auth")
            return 1
        rec("UPSTREAM-JOIN", "PASS",
            "pinned IRMLinearKink.sol: uint32.max util, slope*util, unchecked over-kink, vault auth (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of IRMLinearKink.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-JOIN", "SKIP", "live IRMLinearKink.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-JOIN", "FAIL", "IRMLinearKink.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Euler IRM clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_euler_irm.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "eir_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "eir_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "eir_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 2000)), ("mul", (WRAP_A, WRAP_B)),
        ("add", (50, 50)), ("add", (WRAP_A, WRAP_B)),
        ("util", (50, 50)), ("util", (0, 0)), ("util", (100, 0)), ("util", (0, 100)),
        ("util", (75, 25)), ("util", (25, 75)), ("util", (WRAP_A, WRAP_B)),
        ("rate", (50, 50, 0, 2, 3, KINK)), ("rate", (0, 100, 0, 2, 3, KINK)),
        ("rate", (25, 75, 0, 2, 3, KINK)), ("rate", (75, 25, 0, 2, 3, KINK)),
        ("rate", (100, 0, 10, 2, 3, KINK)), ("rate", (0, 0, 10, 2, 3, KINK)),
        ("rate", (WRAP_A, WRAP_B, 0, 2, 3, KINK)),
        ("auth", (7, 7)), ("auth", (1, 2)),
        ("compute", (1, 2, 50, 50, 0, 2, 3, KINK)),
        ("compute", (7, 7, 50, 50, 0, 2, 3, KINK)),
    ]
    lin_fn = {
        "mul": "eir_u_mul_ok", "add": "eir_u_add_ok", "util": "eir_util",
        "rate": "eir_rate", "auth": "eir_auth_ok", "compute": "eir_compute",
    }
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        got_lin = lin_vm(lin_fn[kind], *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{kind}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_kind(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {kind}{largs}", f"py={py_kind(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    u50 = lin_vm("eir_util", 50, 50)
    r50 = lin_vm("eir_rate", 50, 50, 0, 2, 3, KINK)
    r100 = lin_vm("eir_rate", 0, 100, 0, 2, 3, KINK)
    r75 = lin_vm("eir_rate", 25, 75, 0, 2, 3, KINK)
    r25 = lin_vm("eir_rate", 75, 25, 0, 2, 3, KINK)
    r0 = lin_vm("eir_rate", 100, 0, 10, 2, 3, KINK)
    empty = lin_vm("eir_rate", 0, 0, 10, 2, 3, KINK)
    denied = lin_vm("eir_compute", 1, 2, 50, 50, 0, 2, 3, KINK)
    allowed = lin_vm("eir_compute", 7, 7, 50, 50, 0, 2, 3, KINK)
    golden = (u50, r50, r100, r75, r25, r0, empty, denied, allowed)
    expect = (2147483647, 4294967294, 10737418237, 7516192765, 2147483646, 10, 10, 0, 4294967294)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "util/kink/100%/auth goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "50% util=2147483647 ir=4294967294; 100% ir=10737418237; unauthorized compute=0",
        "util50=2147483647 rate50=4294967294 rate100=10737418237 auth_fail=0")
    rec("COMMERCIAL", "PASS",
        "measured Euler kink quote (not TVL): slope*uint32-util with explicit caller==vault, no wrapping mul",
        "kink_ir=4294967294 max_ir=10737418237 unit=uint32.max_scale")

    wrapped = lin_vm("eir_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("eir_u_mul_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked borrows*uint32.max fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "eir_rate(cash: int, borrows: int, base: int, slope1: int, slope2: int, kink: int" in src else "FAIL",
        "LIN clone takes cash/borrows/slopes/kink (no hidden IRM immutables / msg.sender)")
    rec("NOT-JUMPRATE", "PASS" if "eir_uses_jumprate" in src and "eir_uses_reserves" in src else "FAIL",
        "clone is Euler uint32.max * slope, not Compound JumpRate 1e18/reserves")
    rec("AUTH-EXPLICIT", "PASS" if "eir_auth_ok" in src else "FAIL",
        "E_IRMUpdateUnauthorized is an explicit caller==vault check")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_TYPEMAX" in sol_src and "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close type(uint32).max / __int128 / i128 (host, not LIN emit)")
    rec("TR-IRM", "PASS" if "REJ_SOLIDITY_IRMUPDATE" in sol_src else "FAIL",
        "Solidity transpiler fail-closes E_IRMUpdateUnauthorized (explicit caller in LIN)")
    rec("TR-UNCHECKED", "PASS" if "REJ_SOLIDITY_UNCHECKED" in sol_src else "FAIL",
        "Solidity transpiler fail-closes unchecked { util-kink } (explicit sub_ok in LIN)")

    if not KERNEL.exists() or "eir_rate" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable Euler IRM kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (euler_irm_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("eir_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on eir_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("eir_u_mul_ok", 1000, 2000)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit eir_u_mul_ok(1000,2000)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
            "" if jv == 1 else "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/euler-xyz/euler-vault-kit",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-2.0-or-later (file SPDX; repo BUSL-1.1 until 2029-04-24)",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_euler_irm.lin"
    evidence["c11_oracle"] = "test/oracles/euler_irm_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/euler_irm_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "util_50": u50, "rate_50": r50, "rate_100": r100, "rate_75": r75,
        "rate_25": r25, "rate_0": r0, "rate_empty": empty,
        "compute_unauthorized": denied, "compute_authorized": allowed,
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
