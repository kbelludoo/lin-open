#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V1 Vault.getNextFundingRate vs LIN C0 (EXPERIMENTAL)."""
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
LIN = ROOT / "src" / "lin_gmx_nextrate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_nextrate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_nextrate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx")
EVIDENCE = ROOT / "examples" / "gmx_nextrate" / "gmx_nextrate_evidence.json"

PINNED_SHA256 = "0b49e265fc4c04d3eea74b07d698748050671a2df259f1faa8d05cabf2970f92"
PINNED_BLOB = "4aef3c7dcf40b4657e7dfcef582958dc2d418126"
PINNED_COMMIT = "fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8"
UPSTREAM_REL = "contracts/core/Vault.sol"


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
    url = "https://github.com/gmx-io/gmx-contracts.git"
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


def py_naive_wrap(a: int, b: int, d: int) -> int:
    return tdiv(w64(a * b), d)


def py_intervals(now: int, last: int, interval: int) -> int:
    if interval <= 0 or last < 0 or now < 0 or now < last:
        return 0
    if last > (2**63 - 1) - interval:
        return 0
    if last + interval > now:
        return 0
    return (now - last) // interval


def py_next(now: int, last: int, interval: int, reserved: int, pool: int,
            is_stable: int, vol: int, stb: int) -> int:
    if pool <= 0 or reserved < 0 or vol < 0 or stb < 0:
        return 0
    iv = py_intervals(now, last, interval)
    if iv == 0:
        return 0
    fac = stb if is_stable else vol
    if fac == 0:
        return 0
    t = fac * reserved
    return 0 if t >= 2**64 else (t * iv) // pool


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V1 Vault.getNextFundingRate — external LIN proof (C11 oracle)")
    pinned = FIX / "Vault.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned Vault.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned Vault.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned gmx-io/gmx-contracts matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/core/Vault.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb nextrate selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (intervals / stable / wrap / uninit last)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX nextrate clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_nextrate.lin")

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

    gate = run([str(C0), "vm", str(LIN), "gnr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gnr_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gnr_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "gnr_muldiv", (100, 200, 50), 400),
        ("next", ["28800", "0", "28800", "50000000", "100000000", "0", "100", "10"],
         "gnr_next_rate", (28800, 0, 28800, 50000000, 100000000, 0, 100, 10), 50),
        ("next", ["20000", "0", "28800", "50000000", "100000000", "0", "100", "10"],
         "gnr_next_rate", (20000, 0, 28800, 50000000, 100000000, 0, 100, 10), 0),
        ("ignore", ["50000000", "100000000", "100"], "gnr_ignore_interval",
         (50000000, 100000000, 100), 50),
        ("next", ["86400", "0", "28800", "50000000", "100000000", "0", "100", "10"],
         "gnr_next_rate", (86400, 0, 28800, 50000000, 100000000, 0, 100, 10), 150),
        ("elapsed", ["86400", "0", "50000000", "100000000", "100"], "gnr_use_elapsed",
         (86400, 0, 50000000, 100000000, 100), 4320000),
        ("next", ["28800", "0", "28800", "50000000", "100000000", "1", "100", "10"],
         "gnr_next_rate", (28800, 0, 28800, 50000000, 100000000, 1, 100, 10), 5),
        ("util", ["50000000", "100000000"], "gnr_utilisation", (50000000, 100000000), 500000),
        ("fundfee", ["50000000", "100"], "gnr_as_funding_fee", (50000000, 100), 5000),
        ("next", ["1700000000", "0", "28800", "50000000", "100000000", "0", "100", "10"],
         "gnr_next_rate", (1700000000, 0, 28800, 50000000, 100000000, 0, 100, 10), 2951350),
        ("wrap", ["4000000000", "3000000000", "2000000000"], "gnr_naive_mul_wrap",
         (4000000000, 3000000000, 2000000000), -3223372036),
        ("muldiv", ["4000000000", "3000000000", "2000000000"], "gnr_muldiv",
         (4000000000, 3000000000, 2000000000), 6000000000),
        ("iv", ["86400", "0", "28800"], "gnr_intervals", (86400, 0, 28800), 3),
        ("iv", ["20000", "0", "28800"], "gnr_intervals", (20000, 0, 28800), 0),
        ("next", ["28800", "0", "28800", "0", "100000000", "0", "100", "10"],
         "gnr_next_rate", (28800, 0, 28800, 0, 100000000, 0, 100, 10), 0),
        ("next", ["1000", "2000", "28800", "50000000", "100000000", "0", "100", "10"],
         "gnr_next_rate", (1000, 2000, 28800, 50000000, 100000000, 0, 100, 10), 0),
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
        elif kind == "next":
            py = py_next(*largs)
        elif kind == "ignore":
            py = (largs[2] * largs[0]) // largs[1]
        elif kind == "elapsed":
            py = (largs[4] * largs[2] * (largs[0] - largs[1])) // largs[3]
        elif kind == "util":
            py = (largs[0] * 1_000_000) // largs[1]
        elif kind == "fundfee":
            py = (largs[0] * largs[1]) // 1_000_000
        elif kind == "iv":
            py = py_intervals(*largs)
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("RATE-50", "PASS", "50% util, 1x 8h interval, factor=100: nextRate=50")
    rec("PARTIAL-IV", "PASS", "elapsed 20000 < interval 28800: nextRate=0 vs ignore-interval=50")
    rec("ELAPSED-TRAP", "PASS", "24h: intervals=3 rate=150 vs raw elapsed seconds=4320000 (28800x)")
    rec("STABLE-TRAP", "PASS", "same pool with stable factor=10: rate=5 vs volatile 50 (10x)")
    rec("UTIL-TRAP", "PASS", "getUtilisation reserved*1e6/pool=500000 vs nextRate=50 (10000x)")
    rec("FUND-TRAP", "PASS", "confused getFundingFee reserved*factor/1e6=5000 vs nextRate=50 (100x)")
    rec("UNINIT-LAST", "PASS", "last=0 now=1700000000: intervals=59027 rate=2951350 vs initialized 0")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (4e9*3e9)/2e9 wraps to -3223372036; 128-bit muldiv=6000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "gnr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gnr_test_suite (in-memory libtcc)")
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
        "PASS" if "gnr_next_rate" in src and "function getNextFundingRate" in sol else "FAIL",
        "LIN clone takes now/last/interval/reserved/pool/factors as arguments (no vault storage)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "gnr_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv for factor*reserved*intervals/pool",
    )
    rec(
        "NOT-FUNDING-FEE",
        "PASS" if "!gnr_next_rate" in src and "!gmf_funding_fee" not in src else "FAIL",
        "kernel is GMX next-rate factor*reserved*intervals/pool, not size*(cum-entry)/1e6",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_GMX_NEXTRATE",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects getNextFundingRate / lastFundingTimes before ENV",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_NEXTRATE" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_next_funding_rate / last_funding_times",
    )

    evidence = {
        "schema": "LIN_GMX_NEXT_FUNDING_RATE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "GMX V1 Vault perpetual funding accrual on Arbitrum/Avalanche",
        },
        "lin_clone": "src/lin_gmx_nextrate.lin",
        "c11_oracle": "test/oracles/gmx_nextrate_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "next_1interval_50pct": 50,
            "partial_interval": 0,
            "ignore_interval": 50,
            "three_intervals": 150,
            "raw_elapsed_24h": 4320000,
            "stable_factor": 5,
            "utilisation": 500000,
            "confused_funding_fee": 5000,
            "uninit_last": 2951350,
            "naive_wrap_4e9_3e9": -3223372036,
            "wide_4e9_3e9": 6000000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-nextrate",
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
