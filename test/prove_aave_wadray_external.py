#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 WadRayMath (MIT after BUSL Change Date) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of WadRayMath.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_aave_wadray.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / Aave RAY=1e27 range (RAY does not fit i64/u64)
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL savings

Class: EXPERIMENTAL (real Aave wad half-up algorithm, i64-positive operands).
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
LIN = ROOT / "src" / "lin_aave_wadray.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_wadray_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_wadray_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3")
EVIDENCE = ROOT / "examples" / "aave_wadray" / "aave_wadray_evidence.json"

WAD = 10**18
HALF = WAD // 2
PINNED_SHA256 = "fae5b995ec613cc213050c99ea6352c9c18ceebba106d03b1726cfa8f1f0124e"
PINNED_BLOB = "f61fe87f2f2748144cd4d113c848e649c41a4e5d"
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
UPSTREAM_REL = "contracts/protocol/libraries/math/WadRayMath.sol"
I64MAX = 2**63 - 1


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


def py_wad_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    q = (a * b + HALF) // WAD
    return 0 if q > I64MAX else q


def py_wad_div(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = (a * WAD + b // 2) // b
    return 0 if q > I64MAX else q


def py_floor_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    q = (a * b) // WAD
    return 0 if q > I64MAX else q


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_WADRAY_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 WADRAY — external LIN proof (i64-positive, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "WadRayMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned WadRayMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned WadRayMath.sol sha256 matches manifest")

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
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of WadRayMath.sol")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
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
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Aave wad clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_wadray.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3 (0.5eN + RAY reject)")

    chk3 = run([str(C0), "check", str(RS_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk3.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2 (Aave wad reject)")

    gate = run([str(C0), "vm", str(LIN), "awr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "awr_test_suite via lin_c0 vm", f"rc={gate.returncode} value={gv}\n{gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "awr_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("wadmul", ["1000000000000000000", "1000000000000000000"], "awr_wad_mul", (WAD, WAD)),
        ("wadmul", ["3", str(HALF)], "awr_wad_mul", (3, HALF)),
        ("waddiv", ["2", "3"], "awr_wad_div", (2, 3)),
        ("waddiv", ["1", "3"], "awr_wad_div", (1, 3)),
        ("wadmul", ["0", str(WAD)], "awr_wad_mul", (0, WAD)),
        ("waddiv", [str(WAD), str(2 * WAD)], "awr_wad_div", (WAD, 2 * WAD)),
        ("wadmul", [str(3 * WAD), str(3 * WAD)], "awr_wad_mul", (3 * WAD, 3 * WAD)),
        ("wadmul", [str(4 * WAD), str(3 * WAD)], "awr_wad_mul", (4 * WAD, 3 * WAD)),
        ("floor_mul", ["3", str(HALF)], "awr_wrong_floor_mul", (3, HALF)),
        ("floor_div", ["2", "3"], "awr_wrong_floor_div", (2, 3)),
        ("sraymul", ["3", "500000000"], "awr_sray_mul", (3, 500000000)),
        ("wad2ray", ["1"], "awr_wad_to_ray", (1,)),
        ("wad2ray", [str(WAD)], "awr_wad_to_ray", (WAD,)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1]) if kind != "wad2ray" else want
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "wadmul":
            py = py_wad_mul(largs[0], largs[1])
        elif kind == "waddiv":
            py = py_wad_div(largs[0], largs[1])
        elif kind == "floor_mul":
            py = py_floor_mul(largs[0], largs[1])
        elif kind == "floor_div":
            py = (largs[0] * WAD) // largs[1]
        elif kind == "sraymul":
            py = (largs[0] * largs[1] + 500000000) // 1000000000
        else:
            py = 0 if largs[0] * 10**9 > I64MAX else largs[0] * 10**9
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    half_up = lin_vm("awr_wad_mul", 3, HALF)
    floor = lin_vm("awr_wrong_floor_mul", 3, HALF)
    if half_up != 2 or floor != 1:
        rec("HALF-UP", "FAIL", "wadMul(3, HALF_WAD) half-up vs floor", f"half={half_up} floor={floor}")
        return 1
    rec("HALF-UP", "PASS", "wadMul(3, 0.5e18)=2 half-up vs floor mulWad=1 (Solady-style)")

    d_up = lin_vm("awr_wad_div", 2, 3)
    d_floor = lin_vm("awr_wrong_floor_div", 2, 3)
    if d_up != 666666666666666667 or d_floor != 666666666666666666:
        rec("DIV-HALF-UP", "FAIL", "wadDiv(2,3) half-up vs floor", f"up={d_up} floor={d_floor}")
        return 1
    rec("DIV-HALF-UP", "PASS", "wadDiv(2,3)=666...667 half-up vs floor 666...666")

    wide = lin_vm("awr_wad_mul", 3 * WAD, 3 * WAD)
    naive = lin_vm("awr_naive_i64_mul", 3 * WAD, 3 * WAD)
    if wide != 9000000000000000000 or naive == wide:
        rec("I64-WRAP", "FAIL", "128-bit wadMul vs naive i64 3e18*3e18", f"wide={wide} naive={naive}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e18*3e18) wraps; 128-bit half-up wadMul does not",
        f"i64_wrap={naive} wadmul={wide}",
    )

    if lin_vm("awr_ray_fits") != 0:
        rec("RAY-U64", "FAIL", "awr_ray_fits must be 0: Aave RAY=1e27 > uint64")
        return 1
    rec("RAY-U64", "PASS", "RAY=1e27 is unrepresentable in i64/u64 (awr_ray_fits=0)")

    if lin_vm("awr_wad_to_ray", WAD) != 0 or lin_vm("awr_wad_to_ray_ok", WAD) != 0:
        rec("WAD2RAY-1W", "FAIL", "native wadToRay(1 WAD)=1e27 must fail-closed")
        return 1
    rec("WAD2RAY-1W", "PASS", "wadToRay(1e18) fail-closed (1e27 does not fit i64); naive wraps")

    jit_ok = lin_roundtrip_jit("awr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on awr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("awr_wad_mul", 3, HALF)
        if jv == 2:
            rec("C0-JIT", "PASS", "lin_c0 jit awr_wad_mul(3,HALF)==2 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "assembly" not in sol or "HALF_WAD" not in sol or "0.5e18" not in sol:
        rec("UPSTREAM-YUL", "FAIL", "pinned WadRayMath.sol missing Yul half-up wadMul")
    else:
        rec("UPSTREAM-YUL", "PASS", "upstream wadMul is Yul (a*b+HALF_WAD)/WAD; LIN is explicit 128-bit")
    if "awr_muldiv_add_part" in src and "_lia_ushr" in src:
        rec("WIDE-HALFUP", "PASS", "clone uses 128-bit (a*b+add)/d; naive i64 a*b wraps on 3e18*3e18")
    else:
        rec("WIDE-HALFUP", "FAIL", "128-bit half-up muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_AAVE_WADRAY" in sol_src and "0.5e18" in sol_src and "REJ_SOLIDITY_RAY_GT_U64" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3 expands 0.5eN and rejects Aave RAY/Yul wadMul")
    else:
        rec("SOL-EMIT", "FAIL", "v3 Aave wad/RAY reject or 0.5eN expand missing")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_AAVE_WADRAY" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 rejects wad_mul / HALF_WAD")
    else:
        rec("RS-EMIT", "FAIL", "Rust Aave wad reject missing")

    # C0 VM rejects string literals (VM_REJ_STRING_LITERAL). Transpiler gates
    # are `lin_c0 check` plus source assertions; they are not executed on C0 VM.
    if "sol_parse_test_gate" in sol_src and "REJ_SOLIDITY_AAVE_WADRAY" in sol_src:
        rec(
            "SOL-GATE",
            "PASS",
            "sol_parse_test_gate source asserts Aave wad/RAY rejections (C0 check-only; strings are not C0-VM)",
        )
    else:
        rec("SOL-GATE", "FAIL", "sol_parse_test_gate missing Aave assertions")

    if 'sol_expand_exp("0.5e18")' in sol_src and "500000000000000000" in sol_src:
        rec("SOL-EXPAND", "PASS", "sol_from_sol_gate asserts 0.5e18 -> 500000000000000000 (HALF_WAD)")
    else:
        rec("SOL-EXPAND", "FAIL", "0.5e18 HALF_WAD expand assertion missing")

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
    evidence["lin_clone"] = "src/lin_aave_wadray.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-aave-wadray"
    evidence["c11_oracle"] = "test/oracles/aave_wadray_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "wadMul_3_HALF": 2,
        "floorMul_3_HALF": 1,
        "wadDiv_2_3": 666666666666666667,
        "floorDiv_2_3": 666666666666666666,
        "wadMul_3W_3W": 9000000000000000000,
        "naive_i64_3W_3W": 5595889181738926080,
        "ray_fits": 0,
        "wadToRay_1W": 0,
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
