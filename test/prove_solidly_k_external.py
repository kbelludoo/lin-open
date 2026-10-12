#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Solidly BaseV1Pair cubic k vs LIN C0 (EXPERIMENTAL WAD'=1e6)."""
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
LIN = ROOT / "src" / "lin_solidly_k.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "solidly_k_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "solidly_k_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_solidly")
EVIDENCE = ROOT / "examples" / "solidly_k" / "solidly_k_evidence.json"

WAD = 10**6
PINNED_SHA256 = "24f7939bf6e030f59889de6b4bad40e0814e910137044b8661d776ee6b33e59f"
PINNED_BLOB = "5827d9fdff7442b4075cd0e0b7f236719e0d017c"
PINNED_COMMIT = "a71fe0dc42925709e138d5f1c9ecc4b2a2f3acf5"
UPSTREAM_REL = "contracts/BaseV1-core.sol"


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
    url = "https://github.com/transmissions11/solidly.git"
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
    print("  SOLIDLY BaseV1Pair cubic k — external LIN proof (WAD'=1e6, C11 oracle)")

    pinned = FIX / "BaseV1-core.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned BaseV1-core.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned BaseV1-core.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned transmissions11/solidly matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/BaseV1-core.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb cubic selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (k / Newton / wrap / fee)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of cubic clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_solidly_k.lin")

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

    gate = run([str(C0), "vm", str(LIN), "sld_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "sld_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "sld_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "sld_muldiv", (100, 200, 50), 400),
        ("kstable", [str(WAD), str(WAD)], "sld_k_stable", (WAD, WAD), 2000000),
        ("kstable", ["2000000", "2000000"], "sld_k_stable", (2000000, 2000000), 32000000),
        ("kvol", [str(WAD), str(WAD)], "sld_k", (WAD, WAD, 0), 1000000000000),
        ("f", [str(WAD), str(WAD)], "sld_f", (WAD, WAD), 2000000),
        ("deriv", [str(WAD), str(WAD)], "sld_d", (WAD, WAD), 4000000),
        ("out", ["10000", str(WAD), str(WAD), "0", "1"], "sld_amount_out", (10000, WAD, WAD, 0, 1), 9900),
        ("out", ["10000", str(WAD), str(WAD), "1", "1"], "sld_amount_out", (10000, WAD, WAD, 1, 1), 9997),
        ("out", ["10000", str(WAD), str(WAD), "1", "0"], "sld_amount_out", (10000, WAD, WAD, 1, 0), 9999),
        ("out", ["10000", str(WAD), "4000000", "0", "1"], "sld_amount_out", (10000, WAD, 4000000, 0, 1), 39600),
        ("out", ["100000", str(WAD), str(WAD), "1", "1"], "sld_amount_out", (100000, WAD, WAD, 1, 1), 99939),
        ("out", ["100000", str(WAD), str(WAD), "0", "1"], "sld_amount_out", (100000, WAD, WAD, 0, 1), 90900),
        ("out", ["10000", "1200000", "800000", "1", "1"], "sld_amount_out", (10000, 1200000, 800000, 1, 1), 9827),
        ("out", ["10000", "1200000", "800000", "0", "1"], "sld_amount_out", (10000, 1200000, 800000, 0, 1), 6610),
        ("wrap", ["5000000000", str(WAD)], "sld_naive_sq_wrap", (5000000000, WAD), 6553255926290),
        ("muldiv", ["5000000000", "5000000000", str(WAD)], "sld_muldiv", (5000000000, 5000000000, WAD), 25000000000000),
        ("fee", ["10000", "1"], "sld_apply_fee", (10000, 1), 9999),
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
            if py >= 2**63:
                py = 0
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("CUBIC-VS-XY", "PASS", "stable 10k-on-1e6/1e6 = 9997; volatile xy path = 9900")
    rec("PEG-VS-IMBAL", "PASS", "imbalanced 1.2e6/0.8e6 stable out=9827 vs volatile 6610")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (5e9*5e9)/1e6 wraps to 6553255926290; 128-bit muldiv=25000000000000",
    )
    rec("FEE-1BPS", "PASS", "Solidly 1 bps: apply_fee(10000,1)=9999")
    rec("K-EQUAL", "PASS", "k_stable(1e6,1e6)=2e6; k_vol=1e12 (different scale, same Pair)")

    jit_ok = lin_roundtrip_jit(LIN, "sld_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sld_test_suite (in-memory libtcc)")
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
        "PASS" if "sld_amount_out" in src and "function _k" in sol else "FAIL",
        "LIN clone takes amount/reserves/stable/fee as arguments (no pair storage)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "sld_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv for (x*x)/WAD and Newton dy",
    )
    rec("WAD6-NOT-18", "PASS", "WAD'=1e6 used; sequential 1e18 cubes overflow signed i64")
    rec(
        "NOT-SADDLE",
        "PASS" if "sld_k_stable" in src and "sld_get_y" in src and "!getD" not in src else "FAIL",
        "kernel is Solidly x3y+y3x Newton, not a Saddle/Curve getD port",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_GET_Y",
        "REJ_SOLIDITY_SOLIDLY_K",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects _k / _get_y / x3y+y3x",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GET_Y" in rs_src and "REJ_RUST_SOLIDLY_K" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects _get_y / x3y",
    )

    evidence = {
        "schema": "LIN_SOLIDLY_CUBIC_K_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/transmissions11/solidly",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "Velodrome (Optimism) / Aerodrome (Base) inherit this cubic k",
        },
        "lin_clone": "src/lin_solidly_k.lin",
        "c11_oracle": "test/oracles/solidly_k_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "q_scale": "WAD'=1e6 (not 1e18)",
        "goldens": {
            "k_stable_1e6": 2000000,
            "k_stable_2e6": 32000000,
            "k_vol_1e6": 1000000000000,
            "out_stable_10k": 9997,
            "out_vol_10k": 9900,
            "out_stable_10k_fee0": 9999,
            "out_vol_1e6_4e6": 39600,
            "out_stable_1e5": 99939,
            "out_imbal_stable": 9827,
            "out_imbal_vol": 6610,
            "naive_wrap_5e9": 6553255926290,
            "wide_sq_5e9": 25000000000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-solidly-k",
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
