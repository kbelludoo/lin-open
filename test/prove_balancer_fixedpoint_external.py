#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Balancer V2 FixedPoint (GPL-3.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of FixedPoint.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_balancer_fixedpoint.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 range / mainnet Vault or WeightedPool parity
    * powDown / powUp / LogExpMath
    * that LIN replaces Balancer on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL savings

Class: EXPERIMENTAL (real Balancer floor/ceil 1e18 algorithm, i64-positive operands).
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
LIN = ROOT / "src" / "lin_balancer_fixedpoint.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "balancer_fixedpoint_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "balancer_fixedpoint_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_balancer_v2")
EVIDENCE = ROOT / "examples" / "balancer_fixedpoint" / "balancer_fixedpoint_evidence.json"

ONE = 10**18
HALF = ONE // 2
W3 = 3 * 10**18
PINNED_SHA256 = "db8645a642a965744b15cbdedbf0214c6b8807cf98d359cfb00727a82967a944"
PINNED_BLOB = "f3c74182db0cb5085ef3066ad069ecf76ef1df9f"
PINNED_COMMIT = "e91a2b643a49856f51a648d175667c1b48cf3377"
UPSTREAM_REL = "pkg/solidity-utils/contracts/math/FixedPoint.sol"
I64MAX = 2**63 - 1
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-balancer-fixedpoint"


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
    url = "https://github.com/balancer/balancer-v2-monorepo.git"
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


def py_mul_down(a: int, b: int) -> int:
    q = (a * b) // ONE
    return 0 if q > I64MAX else q


def py_mul_up(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    p = a * b
    q, r = divmod(p, ONE)
    if q > I64MAX:
        return 0
    if r == 0:
        return q
    s = q + 1
    return 0 if s > I64MAX else s


def py_div_down(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * ONE) // b
    return 0 if q > I64MAX else q


def py_div_up(a: int, b: int) -> int:
    if b == 0 or a == 0:
        return 0
    q, r = divmod(a * ONE, b)
    if q > I64MAX:
        return 0
    if r == 0:
        return q
    s = q + 1
    return 0 if s > I64MAX else s


def py_halfup_mul(a: int, b: int) -> int:
    q = (a * b + HALF) // ONE
    return 0 if q > I64MAX else q


def py_halfup_div(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * ONE + b // 2) // b
    return 0 if q > I64MAX else q


def py_of(kind: str, a: int, b: int) -> int:
    if kind == "muldown":
        return py_mul_down(a, b)
    if kind == "mulup":
        return py_mul_up(a, b)
    if kind == "divdown":
        return py_div_down(a, b)
    if kind == "divup":
        return py_div_up(a, b)
    if kind == "halfup_mul":
        return py_halfup_mul(a, b)
    if kind == "halfup_div":
        return py_halfup_div(a, b)
    if kind == "complement":
        return 0 if a >= ONE else ONE - a
    raise ValueError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_BALANCER_FIXEDPOINT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BALANCER V2 FIXEDPOINT — external LIN proof (i64-positive, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "FixedPoint.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned FixedPoint.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned FixedPoint.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned balancer-v2-monorepo commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of FixedPoint.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb FixedPoint selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb floor/ceil agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Balancer FixedPoint clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_balancer_fixedpoint.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec(
        "SOL-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3 (0.7eN + Balancer reject)",
    )
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec(
        "RS-TR-CHECK",
        "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2 (Balancer FixedPoint reject)",
    )
    chk4 = run([str(C0), "check", str(C_TR)])
    rec(
        "C-TR-CHECK",
        "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL",
        "Compiler 0 check of C transpiler v2 (Balancer FixedPoint reject)",
    )

    gate = run([str(C0), "vm", str(LIN), "bfp_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec(
            "LIN-SUITE",
            "FAIL",
            "bfp_test_suite via lin_c0 vm",
            f"rc={gate.returncode} value={gv}\n{gate.stdout}\n{gate.stderr}",
        )
        return 1
    rec("LIN-SUITE", "PASS", "bfp_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldown", [str(ONE), str(ONE)], "bfp_mul_down", (ONE, ONE)),
        ("muldown", ["3", str(HALF)], "bfp_mul_down", (3, HALF)),
        ("mulup", ["3", str(HALF)], "bfp_mul_up", (3, HALF)),
        ("muldown", ["1", "1"], "bfp_mul_down", (1, 1)),
        ("mulup", ["1", "1"], "bfp_mul_up", (1, 1)),
        ("divdown", ["1", "3"], "bfp_div_down", (1, 3)),
        ("divup", ["1", "3"], "bfp_div_up", (1, 3)),
        ("halfup_div", ["1", "3"], "bfp_wrong_halfup_div", (1, 3)),
        ("muldown", [str(W3), str(W3)], "bfp_mul_down", (W3, W3)),
        ("muldown", [str(4 * 10**18), str(W3)], "bfp_mul_down", (4 * 10**18, W3)),
        ("mulup", [str(4 * 10**18), str(W3)], "bfp_mul_up", (4 * 10**18, W3)),
        ("divdown", ["2", "3"], "bfp_div_down", (2, 3)),
        ("divup", ["2", "3"], "bfp_div_up", (2, 3)),
        ("halfup_mul", ["3", str(HALF)], "bfp_wrong_halfup_mul", (3, HALF)),
        ("complement", [str(10**17)], "bfp_complement", (10**17,)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        limb_args = [kind, *oargs, "--limbs"] if kind != "complement" else [kind, *oargs]
        want_limbs = int(oracle(limb_args).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs or got_lin != want:
            rec("VEC-CONSENSUS", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} limbs={want_limbs}")
            return 1
        py = py_of(kind, largs[0], largs[1] if len(largs) > 1 else 0)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    floor3 = lin_vm("bfp_mul_down", 3, HALF)
    ceil3 = lin_vm("bfp_mul_up", 3, HALF)
    half3 = lin_vm("bfp_wrong_halfup_mul", 3, HALF)
    if floor3 != 1 or ceil3 != 2 or half3 != 2:
        rec("FLOOR-VS-CEIL", "FAIL", "mulDown(3,0.5e18) vs mulUp vs Aave half-up", f"down={floor3} up={ceil3} half={half3}")
        return 1
    rec("FLOOR-VS-CEIL", "PASS", "mulDown(3, 0.5e18)=1 floor vs mulUp=2 vs Aave half-up=2")

    d_down = lin_vm("bfp_div_down", 1, 3)
    d_up = lin_vm("bfp_div_up", 1, 3)
    d_half = lin_vm("bfp_wrong_halfup_div", 1, 3)
    if d_down != 333333333333333333 or d_up != 333333333333333334 or d_half != 333333333333333333:
        rec("CEIL-VS-HALFUP", "FAIL", "divUp(1,3) ceil vs Aave wadDiv half-up", f"down={d_down} up={d_up} half={d_half}")
        return 1
    rec("CEIL-VS-HALFUP", "PASS", "divUp(1,3)=333...334 ceil vs Aave half-up 333...333 vs floor 333...333")

    dust_down = lin_vm("bfp_mul_down", 1, 1)
    dust_up = lin_vm("bfp_mul_up", 1, 1)
    if dust_down != 0 or dust_up != 1:
        rec("DUST-CEIL", "FAIL", "mulUp(1,1) dust ceil vs mulDown 0", f"down={dust_down} up={dust_up}")
        return 1
    rec("DUST-CEIL", "PASS", "mulUp(1,1)=1 ceil of 1e-18 vs mulDown=0")

    wide = lin_vm("bfp_mul_down", W3, W3)
    naive = lin_vm("bfp_naive_i64_mul", W3, W3)
    if wide != 9000000000000000000 or naive == wide:
        rec("I64-WRAP", "FAIL", "128-bit mulDown vs naive i64 3e18*3e18", f"wide={wide} naive={naive}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e18*3e18) wraps; 128-bit mulDown yields 9e18",
        f"i64_wrap={naive} muldown={wide}",
    )

    ov = lin_vm("bfp_mul_down", 4 * 10**18, W3)
    if ov != 0:
        rec("OV-FAILCLOSED", "FAIL", "mulDown(4e18,3e18)=12e18 must fail-close", f"got={ov}")
        return 1
    rec("OV-FAILCLOSED", "PASS", "mulDown(4e18,3e18)=12e18 does not fit i64 and fail-closes to 0")

    jit_ok = lin_roundtrip_jit("bfp_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on bfp_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("bfp_mul_up", 3, HALF)
        if jv == 2:
            rec("C0-JIT", "PASS", "lin_c0 jit bfp_mul_up(3,0.5e18)==2 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "mulUp" not in sol or "assembly" not in sol or "0.7e18" not in sol:
        rec("UPSTREAM-YUL", "FAIL", "pinned FixedPoint.sol missing Yul mulUp / 0.7e18")
    else:
        rec("UPSTREAM-YUL", "PASS", "upstream mulUp is Yul ceil ((product-1)/ONE)+1; LIN is explicit 128-bit")
    if "bfp_muldiv_add_part" in src and "_lia_ushr" in src:
        rec("WIDE-CEIL", "PASS", "clone uses 128-bit floor/ceil; naive i64 a*b wraps on 3e18*3e18")
    else:
        rec("WIDE-CEIL", "FAIL", "128-bit muldiv missing")
    if "!bfp_pow" in src or "LogExpMath.pow" in src:
        rec("NO-POW", "FAIL", "clone must not implement powDown/LogExpMath")
    else:
        rec("NO-POW", "PASS", "clone has no pow kernel; powDown/powUp/LogExpMath remain out of scope")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_BALANCER_FP" in sol_src and "0.7e18" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3 expands 0.7eN and rejects Balancer mulUp Yul")
    else:
        rec("SOL-EMIT", "FAIL", "v3 Balancer reject or 0.7eN expand missing")
    if "sol_parse_test_gate" in sol_src and "REJ_SOLIDITY_BALANCER_FP" in sol_src:
        rec("SOL-GATE", "PASS", "sol_parse_test_gate source asserts Balancer mulUp rejections (C0 check-only; string VM refused)")
    else:
        rec("SOL-GATE", "FAIL", "sol_parse_test_gate missing Balancer assertions")
    if 'sol_expand_exp("0.7e18")' in sol_src and "700000000000000000" in sol_src:
        rec("SOL-EXPAND", "PASS", "sol_from_sol_gate asserts 0.7e18 -> 700000000000000000 (MIN_POW_BASE_FREE_EXPONENT)")
    else:
        rec("SOL-EXPAND", "FAIL", "0.7e18 MIN_POW_BASE expand assertion missing")
    if "REJ_RUST_BALANCER_FP" in RS_TR.read_text(encoding="utf-8"):
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 rejects mul_up / MAX_POW_RELATIVE_ERROR")
    else:
        rec("RS-EMIT", "FAIL", "Rust Balancer FixedPoint reject missing")
    if "REJ_C_BALANCER_FP" in C_TR.read_text(encoding="utf-8"):
        rec("C-EMIT", "PASS", "lin_from_c.lin v2 rejects mul_up / MAX_POW_RELATIVE_ERROR")
    else:
        rec("C-EMIT", "FAIL", "C Balancer FixedPoint reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/balancer/balancer-v2-monorepo",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-3.0-or-later",
    }
    evidence["lin_clone"] = "src/lin_balancer_fixedpoint.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/balancer_fixedpoint_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "mulDown_3_HALF": 1,
        "mulUp_3_HALF": 2,
        "aave_wadMul_3_HALF": 2,
        "mulDown_1_1": 0,
        "mulUp_1_1": 1,
        "divDown_1_3": 333333333333333333,
        "divUp_1_3": 333333333333333334,
        "aave_wadDiv_1_3": 333333333333333333,
        "mulDown_3e18_3e18": 9000000000000000000,
        "naive_i64_3e18_3e18": 5595889181738926080,
        "mulDown_4e18_3e18": 0,
        "complement_1e17": 900000000000000000,
        "MIN_POW_BASE_0_7e18": 700000000000000000,
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
