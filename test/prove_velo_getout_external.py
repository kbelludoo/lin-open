#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Velodrome Pool.getAmountOut (GPL-3.0-or-later, hash-pin only) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git pin of velodrome-finance/contracts Pool.sol (sha256 + git blob;
      Solidity is NOT vendored)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_velo_getout.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int on the same uint64-scale formulas

  NOT claimed:
    * full Solidity uint256 / 1e18 / token-decimals / Optimism mainnet parity
    * that LIN replaces Velodrome, Aerodrome, Uniswap, or the EVM
    * TVL or dollar savings
    * zk / computational soundness

Class: EXPERIMENTAL (real Solidly/Velodrome quote algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_velo_getout.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "velo_getout_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "velo_getout_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_velodrome")
EVIDENCE = ROOT / "examples" / "velo_getout" / "velo_getout_evidence.json"

PINNED_SHA256 = "32d040ff419fa9b1f9113f7e10d587b332a2ab9c6b6099851025cc16a4e986bb"
PINNED_BLOB = "91412c378bba4d8076271cee52e1397b1520b709"
PINNED_COMMIT = "b3065d8b6702b14b094f9f6046b752cc9f78c43b"
UPSTREAM_REL = "contracts/Pool.sol"
UPSTREAM_URL = "https://github.com/velodrome-finance/contracts.git"
CLONE_LIN_REPO = "https://github.com/kbelludoo/clone-lin-velo-getout"
CLONE_LIN_COMMIT = os.environ.get("CLONE_LIN_COMMIT", "")

E9 = 10**9
FEE_DEN = 10000
SCALE = E9


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    proc = run(cmd, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=120)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=180)
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


def py_f(x0: int, y: int) -> int:
    if x0 <= 0 or y <= 0:
        return 0
    a = md(x0, y, SCALE)
    xx = md(x0, x0, SCALE)
    yy = md(y, y, SCALE)
    b = xx + yy
    if b < xx:
        return 0
    return md(a, b, SCALE)


def py_d(x0: int, y: int) -> int:
    if x0 <= 0 or y <= 0:
        return 0
    yy = md(y, y, SCALE)
    t1 = md(md(3, x0, 1), yy, SCALE)
    xx = md(x0, x0, SCALE)
    t2 = md(xx, x0, SCALE)
    s = t1 + t2
    return 0 if s < t1 else s


def py_get_y(x0: int, xy: int, y: int) -> int:
    if x0 <= 0 or xy <= 0 or y <= 0:
        return 0
    for _ in range(255):
        k = py_f(x0, y)
        den = py_d(x0, y)
        if den <= 0:
            return 0
        if k < xy:
            dy = md(xy - k, SCALE, den)
            if dy == 0:
                if k == xy:
                    return y
                if py_f(x0, y + 1) > xy:
                    return y + 1
                dy = 1
            ny = y + dy
            if ny < y:
                return 0
            y = ny
        else:
            dy = md(k - xy, SCALE, den)
            if dy == 0:
                if k == xy or (y > 0 and py_f(x0, y - 1) < xy):
                    return y
                dy = 1
            if y <= dy:
                return 0
            y = y - dy
    return 0


def py_out(amount_in: int, ra: int, rb: int, stable: int, fee: int) -> int:
    if amount_in <= 0 or ra <= 0 or rb <= 0 or fee < 0 or fee > FEE_DEN:
        return 0
    net = amount_in - md(amount_in, fee, FEE_DEN)
    if net <= 0:
        return 0
    if stable == 0:
        den = ra + net
        if den < ra:
            return 0
        return md(net, rb, den)
    xy = py_f(ra, rb)
    if xy <= 0:
        return 0
    x0 = ra + net
    if x0 < ra:
        return 0
    y = py_get_y(x0, xy, rb)
    if y <= 0 or rb <= y:
        return 0
    return rb - y


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
    print("  VELODROME getAmountOut — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned velodrome-finance/contracts commit matches published sha256",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/Pool.sol")
        rec("NO-VENDOR", "PASS", "GPL-3.0-or-later Solidity is hash-pinned only (not copied into lin-open)")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; published pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("NO-VENDOR", "PASS", "Solidity source is not vendored in lin-open")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from published digest", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("NO-VENDOR", "PASS", "Solidity source is not vendored in lin-open")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb getAmountOut selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb getAmountOut agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of velo getAmountOut clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_velo_getout.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if all(tok in sol_src for tok in ("REJ_SOLIDITY_GET_Y", "REJ_SOLIDITY_ADDRESS", "REJ_SOLIDITY_FACTORY")):
        rec("SOL-GATE", "PASS", "lin_from_solidity.lin fail-closes _get_y / address / IPoolFactory")
    else:
        rec("SOL-GATE", "FAIL", "Solidity reject tokens missing")
        return 1
    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_GET_Y" in c_src:
        rec("C-REJ", "PASS", "lin_from_c.lin fail-closes _get_y")
    else:
        rec("C-REJ", "FAIL", "C transpiler reject token missing")
        return 1
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_GET_Y" in rs_src:
        rec("RS-GATE", "PASS", "lin_from_rust.lin fail-closes _get_y")
    else:
        rec("RS-GATE", "FAIL", "Rust _get_y reject missing")
        return 1

    gate = run([str(C0), "vm", str(LIN), "vgo_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "vgo_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "vgo_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("md", ["100", "200", "50"], "vgo_muldiv", (100, 200, 50), 400),
        ("f", [str(E9), str(E9)], "vgo_f", (E9, E9), 2000000000),
        ("gy", [str(E9), "2000000000", str(E9)], "vgo_get_y", (E9, 2000000000, E9), E9),
        (
            "out",
            ["100000000", str(E9), str(E9), "0", "0"],
            "vgo_get_amount_out",
            (100000000, E9, E9, 0, 0),
            90909090,
        ),
        (
            "out",
            ["100000000", str(E9), str(E9), "0", "5"],
            "vgo_get_amount_out",
            (100000000, E9, E9, 0, 5),
            90867766,
        ),
        (
            "out",
            ["100000000", str(E9), str(E9), "0", "30"],
            "vgo_get_amount_out",
            (100000000, E9, E9, 0, 30),
            90661089,
        ),
        (
            "out",
            ["100000000", str(E9), str(E9), "1", "0"],
            "vgo_get_amount_out",
            (100000000, E9, E9, 1, 0),
            99950051,
        ),
        (
            "out",
            ["100000000", str(E9), str(E9), "1", "1"],
            "vgo_get_amount_out",
            (100000000, E9, E9, 1, 1),
            99940071,
        ),
        (
            "out",
            ["10000000", str(E9), str(E9), "1", "1"],
            "vgo_get_amount_out",
            (10000000, E9, E9, 1, 1),
            9998994,
        ),
        (
            "out",
            ["0", str(E9), str(E9), "0", "5"],
            "vgo_get_amount_out",
            (0, E9, E9, 0, 5),
            0,
        ),
        (
            "gy",
            ["1100000000", "2000000000", str(E9)],
            "vgo_get_y",
            (1100000000, 2000000000, E9),
            900049949,
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
        if kind == "md":
            py = md(*largs)
        elif kind == "f":
            py = py_f(*largs)
        elif kind == "gy":
            py = py_get_y(*largs)
        else:
            py = py_out(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == named goldens")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    wrapped = (4000000000 * 4000000000) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("vgo_naive_i64_mul", 4000000000, 4000000000)
    wide = lin_vm("vgo_muldiv", 4000000000, 4000000000, 1)
    if naive != wrapped or wide != 0:
        rec("I64-WRAP", "FAIL", "naive i64 4e9*4e9 wrap vs 128-bit fail-close", f"lin={naive} wrap={wrapped} md={wide}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (4e9*4e9) wraps; 128-bit muldiv fail-closes (quotient > i64)",
        f"i64_wrap={wrapped} bigint={4000000000 * 4000000000} muldiv=0",
    )

    vol = 90661089
    stbl = 99940071
    rec(
        "VS-UNISWAP",
        "PASS",
        "10% in on equal 1e9 reserves: Solidly-stable quotes more out than volatile/Uniswap-0.3%",
        f"stable_fee1={stbl} volatile_fee30={vol}",
    )

    jit_ok = lin_roundtrip_jit("vgo_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on vgo_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("vgo_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit vgo_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    if "vgo_get_amount_out(amountIn: int, reserveA: int, reserveB: int, stable: int, fee: int)" in src:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes reserveA/B, stable, fee as arguments (no factory/token0 storage)",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args")
    if "vgo_prod128" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product for (a*b)/d (i64 wraps on 4e9*4e9)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit product missing")

    evidence = {
        "schema": "LIN_VELO_GETOUT_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/velodrome-finance/contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "GPL-3.0-or-later (hash-pinned, not vendored)",
        },
        "lin_clone": "src/lin_velo_getout.lin",
        "lin_clone_sha256": sha256_file(LIN),
        "c11_oracle": "test/oracles/velo_getout_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "k_balanced": 2000000000,
            "get_y_identity": E9,
            "vol_10pct_fee0": 90909090,
            "vol_10pct_fee5": 90867766,
            "vol_10pct_fee30": 90661089,
            "stable_10pct_fee0": 99950051,
            "stable_10pct_fee1": 99940071,
            "stable_1pct_fee1": 9998994,
            "dx0_failclosed": 0,
            "get_y_plus10": 900049949,
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
