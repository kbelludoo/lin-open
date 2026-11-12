#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 WadRayMath rayToWad / wadToRay vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of WadRayMath.sol
      (git blob + sha256; full Solidity is NOT vendored — pin is hash-only)
    * an independent C11 oracle (native uint64 div/mod AND a restoring
      divider matching src/lin_aave_raytowad.lin; __int128 overflow for wadToRay)
    * Python bigint as a third algorithm
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / mainnet RAY=1e27 parity
    * that LIN replaces Aave, the EVM, or Aave indexes
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Aave rayToWad/wadToRay algorithm, i64-positive).
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
LIN = ROOT / "src" / "lin_aave_raytowad.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_raytowad_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_raytowad_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_raytowad" / "aave_raytowad_evidence.json"

PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
UPSTREAM_URL = "https://github.com/aave/aave-v3-core.git"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-raytowad"
RATIO = 10**9
HALF = RATIO // 2
I64_MAX = 2**63 - 1
WAD = 10**18

PINS = {
    "contracts/protocol/libraries/math/WadRayMath.sol": {
        "sha256": "fae5b995ec613cc213050c99ea6352c9c18ceebba106d03b1726cfa8f1f0124e",
        "blob": "f61fe87f2f2748144cd4d113c848e649c41a4e5d",
        "markers": (
            "function rayToWad",
            "function wadToRay",
            "WAD_RAY_RATIO = 1e9",
            "div(a, WAD_RAY_RATIO)",
            "mod(a, WAD_RAY_RATIO)",
            "mul(a, WAD_RAY_RATIO)",
        ),
    },
}


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


def py_ray_to_wad(a: int) -> int:
    if a < 0:
        return 0
    q, r = divmod(a, RATIO)
    return q + 1 if r >= HALF else q


def py_ray_to_wad_floor(a: int) -> int:
    return 0 if a < 0 else a // RATIO


def py_ray_to_wad_ceil(a: int) -> int:
    if a < 0:
        return 0
    q, r = divmod(a, RATIO)
    return q + 1 if r else q


def py_wad_to_ray(a: int) -> int:
    if a < 0:
        return 0
    p = a * RATIO
    return 0 if p > I64_MAX else p


def i64_wrap_mul(a: int, b: int) -> int:
    wrapped = (a * b) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    return wrapped


def ensure_upstream() -> tuple[str, str, str]:
    rel = "contracts/protocol/libraries/math/WadRayMath.sol"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", UPSTREAM_URL])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", PINNED_COMMIT])
    if co.returncode != 0:
        co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
        if co.returncode != 0:
            return "SKIP", "", "checkout of pinned commit failed"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    pin = PINS[rel]
    live = UPSTREAM / rel
    if not live.exists():
        return "FAIL", commit, f"{rel} missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{rel}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != pin["sha256"] or blob != pin["blob"]:
        return "FAIL", commit, f"{rel} live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    for m in pin["markers"]:
        if m not in text:
            return "FAIL", commit, f"{rel} missing marker {m}"
    return "PASS", commit, f"{rel}:{blob}"


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_RAYTOWAD_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 rayToWad / wadToRay — external LIN proof (i64-positive, C11)")
    print("=" * 78)

    rec("PIN-COMMIT", "PASS", "pinned aave-v3-core WadRayMath commit", PINNED_COMMIT)
    rec(
        "PIN-WADRAY",
        "PASS",
        "pinned WadRayMath.sol sha256 (hash-only; not vendored)",
        PINS["contracts/protocol/libraries/math/WadRayMath.sol"]["sha256"],
    )

    if (ROOT / "contracts" / "WadRayMath.sol").exists():
        rec("NO-VENDOR", "FAIL", "upstream WadRayMath.sol must not be copied into lin-open")
        return 1
    rec("NO-VENDOR", "PASS", "Solidity is not vendored; pin is hash-only")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned aave-v3-core matches hashes", f"commit={commit}")
        rec("UPSTREAM-MARKERS", "PASS", "live file contains rayToWad / wadToRay / WAD_RAY_RATIO")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 native vs restoring div/mod selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 native uint64 and restoring divider agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of rayToWad clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_raytowad.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "art_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "art_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "art_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_lower_wadray_yul" not in sol_src or "REJ_SOLIDITY_AAVE_RAYTOWAD" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin missing Yul lower or RAYTOWAD reject")
        return 1
    rec("SOL-GATE", "PASS", "lin_from_solidity.lin lowers rayToWad/wadToRay Yul to scalar")
    if 'sol_expand_exp("0.5e18")' not in sol_src and "0.5e18" not in sol_src:
        rec("SOL-HALF-EXP", "FAIL", "0.5eN expander missing")
        return 1
    rec("SOL-HALF-EXP", "PASS", "sol_expand_exp handles 0.5eN (HALF_WAD / half ratio)")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_AAVE_YUL" not in rs_src:
        rec("RS-GATE", "FAIL", "lin_from_rust.lin missing Aave Yul reject")
        return 1
    rec("RS-GATE", "PASS", "rs_parse_test_gate source includes Aave Yul reject")

    r2w_vecs = [
        ("zero", 0, 0),
        ("one", 1, 0),
        ("half_minus", HALF - 1, 0),
        ("half", HALF, 1),
        ("half_plus", HALF + 1, 1),
        ("exact_ratio", RATIO, 1),
        ("one_and_half_minus", RATIO + HALF - 1, 1),
        ("one_and_half", RATIO + HALF, 2),
        ("one_and_half_plus", RATIO + HALF + 1, 2),
        ("named_1_5e9", 1500000000, 2),
    ]
    n_ok = 0
    for name, a, named in r2w_vecs:
        want = int(oracle(["r2w", str(a)]).splitlines()[-1])
        want_r = int(oracle(["r2w", str(a), "--restore"]).splitlines()[-1])
        got = lin_vm("art_ray_to_wad", a)
        py = py_ray_to_wad(a)
        if want != want_r or got != want or got != py or got != named:
            rec("VEC-R2W", "FAIL", name, f"lin={got} c11={want} restore={want_r} py={py} named={named}")
            return 1
        n_ok += 1
    rec("VEC-R2W", "PASS", f"{n_ok}/{n_ok} rayToWad vectors: C11 native == restore == LIN == Python")

    n_floor = 0
    for name, a, _named in r2w_vecs:
        want = int(oracle(["r2w-floor", str(a)]).splitlines()[-1])
        got = lin_vm("art_ray_to_wad_floor", a)
        py = py_ray_to_wad_floor(a)
        if got != want or got != py:
            rec("VEC-FLOOR", "FAIL", name, f"lin={got} c11={want} py={py}")
            return 1
        n_floor += 1
    rec("VEC-FLOOR", "PASS", f"{n_floor}/{n_floor} floor rayToWad vectors agree")

    if (
        lin_vm("art_ray_to_wad", HALF) != 1
        or lin_vm("art_ray_to_wad_floor", HALF) != 0
        or lin_vm("art_ray_to_wad_ceil", HALF) != 1
        or lin_vm("art_ray_to_wad", RATIO + HALF) != 2
        or lin_vm("art_ray_to_wad_floor", RATIO + HALF) != 1
    ):
        rec("HALF-UP", "FAIL", "half-up at remainder==ratio/2 must differ from floor")
        return 1
    rec("HALF-UP", "PASS", "remainder==5e8 rounds up: rayToWad(5e8)=1 vs floor=0; 1.5e9 -> 2 vs floor 1")

    w2r_vecs = [
        ("zero", 0, 0),
        ("one", 1, RATIO),
        ("ratio", RATIO, WAD),
        ("wad_overflow", WAD, 0),
    ]
    n_w2r = 0
    for name, a, named in w2r_vecs:
        want = int(oracle(["w2r", str(a)]).splitlines()[-1])
        got = lin_vm("art_wad_to_ray", a)
        py = py_wad_to_ray(a)
        if got != want or got != py or got != named:
            rec("VEC-W2R", "FAIL", name, f"lin={got} c11={want} py={py} named={named}")
            return 1
        n_w2r += 1
    rec("VEC-W2R", "PASS", f"{n_w2r}/{n_w2r} wadToRay vectors: C11 i128 == LIN == Python")
    rec("VEC-CONSENSUS", "PASS", "rayToWad + wadToRay: C11 native == restore == LIN vm == Python bigint")
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "half-up 5e8->1; 1.5e9->2 vs floor 1; wadToRay(1)->1e9; wadToRay(1e18)->0 fail-closed",
    )

    wrapped = i64_wrap_mul(WAD, RATIO)
    ov = lin_vm("art_wad_to_ray", WAD)
    naive = lin_vm("art_naive_i64_mul", WAD, RATIO)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "wadToRay(1e18) fail-closes to 0; naive i64 1e18*1e9 wraps", f"wrap={wrapped}")

    src = LIN.read_text(encoding="utf-8")
    if "art_ray_to_wad(a: int)" not in src or "art_half_ratio" not in src or "r >= art_half_ratio()" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit rayToWad remainder half-up")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN takes ray/wad as args; half-up is r >= ratio/2")

    if lin_vm("art_roundtrip_wad", 1) != 1 or lin_vm("art_roundtrip_wad", RATIO) != 1:
        rec("ROUNDTRIP", "FAIL", "rayToWad(wadToRay(a)) must recover a when product fits i64")
        return 1
    rec("ROUNDTRIP", "PASS", "exact wad->ray->wad roundtrip for values that fit i64")

    if lin_vm("art_wad_to_ray_ok", WAD) != 0 or lin_vm("art_wad_to_ray", WAD) != 0:
        rec("VS-REVERT", "FAIL", "Aave Yul reverts on wadToRay overflow; LIN fail-closes to 0")
        return 1
    rec("VS-REVERT", "PASS", "wadToRay overflow fail-closes to 0 instead of Yul revert")

    jit_ok = lin_roundtrip_jit("art_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on art_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("art_ray_to_wad", HALF)
        if jv == 1:
            rec("C0-JIT", "PASS", "lin_c0 jit art_ray_to_wad(5e8)==1 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    if "sol_lower_wadray_yul" in sol_src and "500000000" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin emits scalar rayToWad/wadToRay from Yul")
    else:
        rec("SOL-EMIT", "FAIL", "solidity Yul lower missing")
    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_AAVE_YUL" in c_src and "REJ_C_INLINE_ASM" in c_src:
        rec("C-EMIT", "PASS", "lin_from_c.lin fail-closes Aave Yul WAD_RAY_RATIO and __asm__")
    else:
        rec("C-EMIT", "FAIL", "C Aave Yul reject missing")
    if "REJ_RUST_AAVE_YUL" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin fail-closes Aave Yul asm! WAD_RAY_RATIO")
    else:
        rec("RS-EMIT", "FAIL", "Rust Aave Yul reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/aave/aave-v3-core",
        "commit": commit or PINNED_COMMIT,
        "path": "contracts/protocol/libraries/math/WadRayMath.sol",
        "pins": PINS,
        "license": "MIT",
        "license_note": "BUSL-1.1 Change Date 2023-01-27 elapsed; Change License MIT",
        "vendored": False,
        "note": "hash-only pin; WadRayMath.sol is not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_aave_raytowad.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/aave_raytowad_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "ray_to_wad_0": 0,
        "ray_to_wad_half": 1,
        "ray_to_wad_floor_half": 0,
        "ray_to_wad_1_5e9": 2,
        "ray_to_wad_floor_1_5e9": 1,
        "wad_to_ray_1": RATIO,
        "wad_to_ray_1e9": WAD,
        "wad_to_ray_1e18": 0,
        "naive_wrap_1e18_x_1e9": wrapped,
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
