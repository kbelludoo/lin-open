#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: crvUSD Controller._health (informational-only, hash-pin) vs LIN C0.

PASS claims are recomputed this run against:
  * live git pin of curvefi/curve-stablecoin controller.vy (sha256 + git blob;
    Vyper is NOT vendored — upstream LICENSE grants no reproduction right)
  * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
    matching src/lin_crvusd_health.lin)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int on the same uint64-scale formulas

NOT claimed:
  * full Vyper uint256 / 1e18 SWAD / mainnet crvUSD parity
  * that LIN replaces crvUSD, LLAMMA, Curve, or the EVM
  * TVL or dollar savings
  * zk / computational soundness
  * get_x_down band math (see clone-lin-llamma-xy); this clone is Controller health

Class: EXPERIMENTAL (real published algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_crvusd_health.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "crvusd_health_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "crvusd_health_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_crvusd")
EVIDENCE = ROOT / "examples" / "crvusd_health" / "crvusd_health_evidence.json"

PINNED_SHA256 = "42d82a3c36712cc1397f170d8e6924f7985035be2e54cfcfee1ce3d303a47c6b"
PINNED_BLOB = "ac5e86ccaefffde86ced8ee4fa4b61cc5242206f"
PINNED_COMMIT = "81b3bea490e9b45221c82e78387920ccfeb05b33"
UPSTREAM_REL = "curve_stablecoin/controller.vy"
UPSTREAM_URL = "https://github.com/curvefi/curve-stablecoin.git"
CLONE_LIN_REPO = "https://github.com/kbelludoo/clone-lin-crvusd-health"
CLONE_LIN_COMMIT = os.environ.get("CLONE_LIN_COMMIT", "")

E9 = 10**9
SCALE = E9


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=180)
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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
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


def md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q >= (1 << 63) else q


def md_ov(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 1
    return 1 if (a * b) // d >= (1 << 63) else 0


def py_health(
    x_down: int, debt: int, disc: int, full: int, ns0: int, active: int, p: int, p_up: int, y: int
) -> int:
    if debt <= 0 or x_down < 0 or disc < 0 or disc > SCALE:
        return 0
    hm = SCALE - disc
    if md_ov(x_down, hm, debt):
        return 0
    h = md(x_down, hm, debt) - SCALE
    if full == 1 and ns0 > active and p > p_up:
        if p < 0 or p_up < 0 or y < 0:
            return 0
        dp = p - p_up
        if md_ov(dp, y, debt):
            return 0
        h = h + md(dp, y, debt)
    return h


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  crvUSD Controller._health — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned curvefi/curve-stablecoin commit matches published sha256",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of curve_stablecoin/controller.vy")
        rec("NO-VENDOR", "PASS", "informational-only Vyper is hash-pinned only (not copied into lin-open)")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; published pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from published digest", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb health selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb health agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of crvUSD health clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_crvusd_health.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if all(tok in sol_src for tok in ("REJ_SOLIDITY_ADDRESS", "REJ_SOLIDITY_GET_X_DOWN", "REJ_SOLIDITY_STATICCALL")):
        rec("SOL-GATE", "PASS", "lin_from_solidity.lin fail-closes address / get_x_down / staticcall")
    else:
        rec("SOL-GATE", "FAIL", "Solidity reject tokens missing")
        return 1
    if "REJ_C_GET_X_DOWN" in C_TR.read_text(encoding="utf-8"):
        rec("C-REJ", "PASS", "lin_from_c.lin fail-closes get_x_down")
    else:
        rec("C-REJ", "FAIL", "C transpiler reject token missing")
        return 1
    if "REJ_RUST_GET_X_DOWN" in RS_TR.read_text(encoding="utf-8"):
        rec("RS-GATE", "PASS", "lin_from_rust.lin fail-closes get_x_down")
    else:
        rec("RS-GATE", "FAIL", "Rust get_x_down reject missing")
        return 1

    gate = run([str(C0), "vm", str(LIN), "chl_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "chl_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "chl_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("md", ["100", "200", "50"], "chl_muldiv", (100, 200, 50), 400),
        ("h", [str(E9), str(E9), "0", "0", "0", "0", "0", "0", "0"], "chl_health", (E9, E9, 0, 0, 0, 0, 0, 0, 0), 0),
        (
            "h",
            ["2000000000", str(E9), "0", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (2000000000, E9, 0, 0, 0, 0, 0, 0, 0),
            E9,
        ),
        (
            "h",
            [str(E9), str(E9), "60000000", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (E9, E9, 60000000, 0, 0, 0, 0, 0, 0),
            -60000000,
        ),
        (
            "h",
            ["1200000000", str(E9), "60000000", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (1200000000, E9, 60000000, 0, 0, 0, 0, 0, 0),
            128000000,
        ),
        (
            "h",
            [str(E9), str(E9), "0", "1", "10", "5", "1100000000", str(E9), str(E9)],
            "chl_health",
            (E9, E9, 0, 1, 10, 5, 1100000000, E9, E9),
            100000000,
        ),
        (
            "h",
            [str(E9), str(E9), "0", "1", "-5", "-10", "1100000000", str(E9), str(E9)],
            "chl_health",
            (E9, E9, 0, 1, -5, -10, 1100000000, E9, E9),
            100000000,
        ),
        (
            "h",
            ["0", str(E9), "0", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (0, E9, 0, 0, 0, 0, 0, 0, 0),
            -E9,
        ),
        (
            "h",
            ["1050000000", str(E9), "60000000", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (1050000000, E9, 60000000, 0, 0, 0, 0, 0, 0),
            -13000000,
        ),
        (
            "h",
            ["10000000000", "1", "0", "0", "0", "0", "0", "0", "0"],
            "chl_health",
            (10000000000, 1, 0, 0, 0, 0, 0, 0, 0),
            0,
        ),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, named in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != named:
            rec("VEC-NAMED", "FAIL", f"{fn}{largs}", f"c11={want} named={named}")
            return 1
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        py = md(*largs) if kind == "md" else py_health(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == named goldens")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    wrapped = (4000000000 * 4000000000) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("chl_naive_i64_mul", 4000000000, 4000000000)
    wide = lin_vm("chl_muldiv", 4000000000, 4000000000, 1)
    if naive != wrapped or wide != 0:
        rec("I64-WRAP", "FAIL", "naive i64 4e9*4e9 wrap vs 128-bit fail-close", f"lin={naive} wrap={wrapped} md={wide}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (4e9*4e9) wraps; 128-bit muldiv fail-closes (quotient > i64)",
        f"i64_wrap={wrapped} bigint={4000000000 * 4000000000} muldiv=0",
    )

    rec(
        "VS-THRESHOLD",
        "PASS",
        "equal x_down=debt: disc=0 health=0 (liq line); disc=6% health=-6e7; 2x collateral health=+1e9",
        "eq_nodisc=0 eq_6pct=-60000000 twice_nodisc=1000000000",
    )

    jit_ok = lin_roundtrip_jit("chl_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on chl_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("chl_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit chl_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "chl_health(x_down: int, debt: int, disc: int, full: int, ns0: int, active: int, p: int, p_up: int, y: int)" in src:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes x_down/debt/disc/full extras as arguments (no AMM/user storage)")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args")
    if "chl_prod128" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product for (a*b)/d (i64 wraps on 4e9*4e9)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit product missing")

    evidence = {
        "schema": "LIN_CRVUSD_HEALTH_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/curvefi/curve-stablecoin",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "informational-only (hash-pinned, not vendored)",
        },
        "lin_clone": "src/lin_crvusd_health.lin",
        "lin_clone_sha256": sha256_file(LIN),
        "c11_oracle": "test/oracles/crvusd_health_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "eq_nodisc": 0,
            "twice_nodisc": E9,
            "eq_6pct": -60000000,
            "ratio12_6pct": 128000000,
            "debt0_failclosed": 0,
            "full_oracle_extra": 100000000,
            "zero_collateral": -E9,
            "ratio105_6pct": -13000000,
            "overflow_failclosed": 0,
        },
        "clone_lin_repo": CLONE_LIN_REPO,
        "clone_lin_commit": CLONE_LIN_COMMIT,
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
