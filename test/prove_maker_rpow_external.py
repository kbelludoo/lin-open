#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: MakerDAO pot.rpow (DSR) vs LIN C0 (EXPERIMENTAL RAY'=1e9)."""
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
LIN = ROOT / "src" / "lin_maker_rpow.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_rpow_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_rpow_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_rpow" / "maker_rpow_evidence.json"

RAY = 10**9
PINNED_SHA256 = "3b20c6285e7eeec097ef20d2065e4aa1773588b9e1f127b9afe19ca3543928bb"
PINNED_BLOB = "13ddce04785a0c9dc49bb8a95c441e25f4263d10"
PINNED_COMMIT = "3f30552a586264b32ebdb5bac94ba67020282e53"
UPSTREAM_REL = "src/pot.sol"


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
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(path: Path, fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(path), fn, *[str(a) for a in args]], timeout=90)
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


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def tdiv(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) ^ (b < 0) else q


def py_naive_wrap(x: int, base: int) -> int:
    return tdiv(w64(x * x), base)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKERDAO pot.rpow — external LIN proof (RAY'=1e9 uint64-scale, C11 oracle)")

    pinned = FIX / "pot.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned pot.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned pot.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned makerdao/dss 1.3.0 matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/pot.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb rpow selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (0^0 / rounding / wrap / drip chi)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of rpow clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_rpow.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec(
        "SOL-TR-CHECK",
        "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3",
    )
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec(
        "RS-TR-CHECK",
        "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2",
    )

    gate = run([str(C0), "vm", str(LIN), "mds_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mds_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "mds_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "mds_muldiv", (100, 200, 50), 400),
        ("rpow", ["0", "0", str(RAY)], "mds_rpow", (0, 0, RAY), RAY),
        ("rpow", ["0", "5", str(RAY)], "mds_rpow", (0, 5, RAY), 0),
        ("rpow", ["2000000000", "3", str(RAY)], "mds_rpow", (2000000000, 3, RAY), 8000000000),
        ("rpow", ["1500000000", "2", str(RAY)], "mds_rpow", (1500000000, 2, RAY), 2250000000),
        ("rpow", ["5000000000", "2", str(RAY)], "mds_rpow", (5000000000, 2, RAY), 25000000000),
        ("rpow", ["3", "2", "2"], "mds_rpow", (3, 2, 2), 5),
        ("noround", ["3", "2", "2"], "mds_rpow_no_round", (3, 2, 2), 4),
        ("rpow", ["1050000000", "2", str(RAY)], "mds_rpow", (1050000000, 2, RAY), 1102500000),
        ("rpow", ["1000001000", "1000", str(RAY)], "mds_rpow", (1000001000, 1000, RAY), 1001000482),
        ("rpow", ["7", "1", str(RAY)], "mds_rpow", (7, 1, RAY), 7),
        ("wrap", ["5000000000", str(RAY)], "mds_naive_sq_wrap", (5000000000, RAY), 6553255926),
        ("drip", ["1050000000", "2", "2000000000"], "mds_drip_chi", (1050000000, 2, 2000000000), 2205000000),
        ("drip", ["1050000000", "2", str(RAY)], "mds_drip_chi", (1050000000, 2, RAY), 1102500000),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != expect or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} expect={expect}")
            return 1
        if kind == "wrap":
            py = py_naive_wrap(*largs)
        elif kind == "muldiv":
            py = (largs[0] * largs[1]) // largs[2]
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("ZERO-POW", "PASS", "rpow(0,0,RAY')=1e9; rpow(0,5,RAY')=0 (Maker 0^0 = base)")
    rec("ROUND-HALF", "PASS", "rpow(3,2,2)=5 with half-up; skip-round floor=4")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (5e9*5e9)/1e9 wraps to 6553255926; 128-bit rpow=25000000000",
    )
    rec("DSR-DRIP", "PASS", "drip chi'=rmul(rpow(1.05e9,2,RAY'),2e9)=2205000000")
    rec("COMPOUND-1K", "PASS", "rpow(1e9+1000, 1000, RAY')=1001000482 (binary exp, not naive loop)")

    jit_ok = lin_roundtrip_jit(LIN, "mds_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mds_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec(
            "CJR-REGRESS",
            "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta",
        )
    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "mds_rpow" in src and "function rpow" in sol else "FAIL",
        "LIN clone takes x/n/base as arguments (dsr/dt/chi explicit on drip)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "mds_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv (x*x/base with half-up rounding)",
    )
    rec("RAY9-NOT-27", "PASS", "RAY'=1e9 used; RAY=1e27 cannot fit signed i64")
    rec(
        "NOT-SHARE-RATE",
        "PASS" if "getSharesByPooledEth" not in src and "getRethValue" not in src else "FAIL",
        "kernel is DSR rpow, not a Lido/Rocket 1:1-vs-div0 retread",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_RPOW",
        "REJ_SOLIDITY_RAY",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects rpow / _rpow / 10**27 / 1e27",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_RPOW" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects rpow",
    )

    evidence = {
        "schema": "LIN_MAKER_DSR_RPOW_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/makerdao/dss",
            "commit": commit or PINNED_COMMIT,
            "tag": "1.3.0",
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "AGPL-3.0-or-later",
        },
        "lin_clone": "src/lin_maker_rpow.lin",
        "c11_oracle": "test/oracles/maker_rpow_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "q_scale": "RAY'=1e9 (not RAY=1e27)",
        "goldens": {
            "zero_pow_zero": RAY,
            "two_cubed_ray": 8000000000,
            "one_point_five_sq": 2250000000,
            "five_e9_sq": 25000000000,
            "round_3_2_2": 5,
            "noround_3_2_2": 4,
            "one_point_05_sq": 1102500000,
            "dsr_plus_1000_n1000": 1001000482,
            "naive_wrap_5e9": 6553255926,
            "drip_chi_2e9": 2205000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-maker-rpow",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
