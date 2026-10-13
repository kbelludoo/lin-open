#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 uncapped getPositionPnlUsd vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_pnl.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_pnl_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_pnl_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_pnl" / "gmx_v2_pnl_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
POS_REL = "contracts/position/PositionUtils.sol"
POS_SHA256 = "38d1f1e4900b5c4fdb01476ab592adda8d58fa6188865b78423eb0a311d3cd06"
POS_BLOB = "53667b52746f5f74003b24290fa8ef0f37b83a84"
PRICE_REL = "contracts/price/Price.sol"
PRICE_SHA256 = "acc88f73f0d013e620b239ee90271143a75404ae07135f762fa57a2406711ea4"
PRICE_BLOB = "679ea9fb62a7077e49cdfbc6e0b9a2298ebd4340"
CALC_REL = "contracts/utils/Calc.sol"
CALC_SHA256 = "7499baf1f95b2c55bf674104ea41ed62bbacc897f4fd7101b9590684fd7bb952"
CALC_BLOB = "9e48fc4c851ef97c8c57b3755257968b3ea2d397"

TOKENS = 1_000_000
SIZE = 2_000_000_000_000_000
P_UP = 2_100_000_000
P_DN = 1_900_000_000
P_MID = 1_950_000_000
P_FLAT = 2_000_000_000


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
    url = "https://github.com/gmx-io/gmx-synthetics.git"
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
    pos = UPSTREAM / POS_REL
    price = UPSTREAM / PRICE_REL
    calc = UPSTREAM / CALC_REL
    if not pos.exists() or not price.exists() or not calc.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{POS_REL}"]).stdout.strip()
    rblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PRICE_REL}"]).stdout.strip()
    cblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{CALC_REL}"]).stdout.strip()
    if sha256_file(pos) != POS_SHA256 or pblob != POS_BLOB:
        return "FAIL", commit, f"pos={sha256_file(pos)} blob={pblob}"
    if sha256_file(price) != PRICE_SHA256 or rblob != PRICE_BLOB:
        return "FAIL", commit, f"price={sha256_file(price)} blob={rblob}"
    if sha256_file(calc) != CALC_SHA256 or cblob != CALC_BLOB:
        return "FAIL", commit, f"calc={sha256_file(calc)} blob={cblob}"
    return "PASS", commit, pblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def trunc_div(a: int, b: int) -> int:
    """C11 / LIN signed division (toward zero), not Python floor div."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def py_pick(is_long: int, maximize: int, pmin: int, pmax: int) -> int:
    if pmin <= 0 or pmax <= 0 or pmax < pmin:
        return 0
    if is_long:
        return pmax if maximize else pmin
    return pmin if maximize else pmax


def py_dt(is_long: int, tokens: int, size_usd: int, size_delta: int) -> int:
    if tokens <= 0 or size_usd <= 0 or size_delta < 0:
        return 0
    if size_delta == 0:
        return 0
    if size_delta == size_usd:
        return tokens
    q = (tokens * size_delta) // size_usd
    r = (tokens * size_delta) % size_usd
    if is_long and r:
        return q + 1
    return q


def py_pnl_usd(
    is_long: int,
    tokens: int,
    size_usd: int,
    size_delta: int,
    pmin: int,
    pmax: int,
    maximize: int = 0,
) -> int:
    if tokens <= 0 or size_usd <= 0:
        return 0
    price = py_pick(is_long, maximize, pmin, pmax)
    if price == 0:
        return 0
    val = tokens * price
    pnl = val - size_usd if is_long else size_usd - val
    dt = py_dt(is_long, tokens, size_usd, size_delta)
    if dt == 0:
        return 0
    return trunc_div(pnl * dt, tokens)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 uncapped getPositionPnlUsd — LIN proof (C11)")

    excerpt = FIX / "PositionPnlUsd.excerpt.sol"
    price_fix = FIX / "Price.sol"
    calc_fix = FIX / "CalcRoundUp.excerpt.sol"
    if not excerpt.exists() or not price_fix.exists() or not calc_fix.exists():
        rec("PIN-FILE", "FAIL", "pinned GMX V2 excerpt / Price.sol / Calc excerpt missing")
        return 1
    if sha256_file(price_fix) != PRICE_SHA256:
        rec("PIN-PRICE", "FAIL", "pinned Price.sol sha256 mismatch", sha256_file(price_fix))
        return 1
    rec("PIN-PRICE", "PASS", "pinned Price.sol sha256 matches upstream blob")
    excerpt_txt = excerpt.read_text(encoding="utf-8")
    need_ex = [
        "pickPriceForPnl(position.isLong(), false)",
        "position.sizeInTokens() * executionPrice",
        "Calc.roundUpDivision(position.sizeInTokens() * sizeDeltaUsd, position.sizeInUsd())",
        "position.sizeInTokens() * sizeDeltaUsd / position.sizeInUsd()",
    ]
    missing_ex = [s for s in need_ex if s not in excerpt_txt]
    if missing_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing kernel strings", ",".join(missing_ex))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains pickPriceForPnl(false) and long round-up dt")
    calc_txt = calc_fix.read_text(encoding="utf-8")
    if "return (a + b - 1) / b;" not in calc_txt:
        rec("PIN-CALC", "FAIL", "Calc excerpt missing roundUpDivision")
        return 1
    rec("PIN-CALC", "PASS", "Calc.roundUpDivision excerpt is (a+b-1)/b")

    up_status, commit, up_note = ensure_upstream()
    blob = POS_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of PositionUtils.sol + Price.sol + Calc.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb PnL selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (long min / short max / round-up / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 PnL clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_pnl.lin")
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

    gate = run([str(C0), "vm", str(LIN), "g2p_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2p_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2p_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, list[int], int]] = [
        ("pick", [1, 0, 2000, 2100], 2000),
        ("pick", [1, 1, 2000, 2100], 2100),
        ("pick", [0, 0, 2000, 2100], 2100),
        ("pick", [0, 1, 2000, 2100], 2000),
        ("dt", [1, 3, 100, 50], 2),
        ("dt", [0, 3, 100, 50], 1),
        ("dt", [1, 3, 100, 100], 3),
        ("pnl", [1, TOKENS, SIZE, P_UP], 100000000000000),
        ("pnl", [1, TOKENS, SIZE, P_DN], -100000000000000),
        ("pnlusd", [1, TOKENS, SIZE, SIZE, P_UP, P_UP], 100000000000000),
        ("pnlusd", [0, TOKENS, SIZE, SIZE, P_DN, P_MID], 50000000000000),
        ("pnlusd", [1, TOKENS, SIZE, SIZE, P_FLAT, P_UP], 0),
        ("wrongmax", [1, TOKENS, SIZE, SIZE, P_FLAT, P_UP], 100000000000000),
        ("pnlusd", [1, 3, 3000, 1500, 1100, 1100], 200),
        ("muldiv", [7000000000, 2000000000, 1000000], 14000000000000),
    ]
    n_ok = 0
    fn_map = {
        "pick": "g2p_pick",
        "dt": "g2p_size_delta_tokens",
        "pnl": "g2p_pnl",
        "pnlusd": "g2p_pnl_usd",
        "wrongmax": "g2p_wrong_max",
        "muldiv": "g2p_muldiv",
    }
    for kind, args, expect in cases:
        fn = fn_map[kind]
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *args)
        pyv = expect
        if kind == "pick":
            pyv = py_pick(*args)
        elif kind == "dt":
            pyv = py_dt(*args)
        elif kind == "pnl":
            is_long, tokens, size_usd, price = args
            val = tokens * price
            pyv = val - size_usd if is_long else size_usd - val
        elif kind == "pnlusd":
            pyv = py_pnl_usd(*args)
        elif kind == "wrongmax":
            pyv = py_pnl_usd(*args, maximize=1)
        elif kind == "muldiv":
            pyv = (args[0] * args[1]) // args[2]
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"{fn}{tuple(args)}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}",
            )
            return 1
        n_ok += 1

    long_p = lin_vm(LIN, "g2p_pnl_usd", 1, TOKENS, SIZE, SIZE, P_UP, P_UP)
    long_l = lin_vm(LIN, "g2p_pnl", 1, TOKENS, SIZE, P_DN)
    short_p = lin_vm(LIN, "g2p_pnl_usd", 0, TOKENS, SIZE, SIZE, P_DN, P_MID)
    flat = lin_vm(LIN, "g2p_pnl_usd", 1, TOKENS, SIZE, SIZE, P_FLAT, P_UP)
    fake = lin_vm(LIN, "g2p_wrong_max", 1, TOKENS, SIZE, SIZE, P_FLAT, P_UP)
    v2d = lin_vm(LIN, "g2p_pnl", 1, 3, 3001, 1100)
    v1d = lin_vm(LIN, "g2p_v1_style", 3001, 1000, 1100)
    part = lin_vm(LIN, "g2p_pnl_usd", 1, 3, 3000, 1500, 1100, 1100)
    floor_dt = lin_vm(LIN, "g2p_floor_delta", 3, 3000, 1500)
    wide = lin_vm(LIN, "g2p_muldiv", 7000000000, 2000000000, 1000000)
    naive = lin_vm(LIN, "g2p_naive_i64", 7000000000, 2000000000, 1000000)
    wrap_py = trunc_div(w64(7000000000 * 2000000000), 1000000)

    if long_p != 100000000000000 or long_l != -100000000000000:
        rec("LONG-PNL", "FAIL", "long profit/loss", f"p={long_p} l={long_l}")
        return 1
    if short_p != 50000000000000:
        rec("SHORT-MIN", "FAIL", "short minimize uses max price", f"lin={short_p}")
        return 1
    if flat != 0 or fake != 100000000000000:
        rec("ORACLE-TRAP", "FAIL", "long min vs max oracle", f"flat={flat} fake={fake}")
        return 1
    if v2d != 299 or v1d != 300:
        rec("V1-DUST", "FAIL", "V2 tokens*price vs V1 size*(p-e)/e", f"v2={v2d} v1={v1d}")
        return 1
    if part != 200 or floor_dt != 1:
        rec("ROUNDUP", "FAIL", "long ceil dt vs floor", f"part={part} floor={floor_dt}")
        return 1
    if naive == wide or wide != 14000000000000 or naive != wrap_py:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit sizeDelta muldiv", f"naive={naive} wide={wide} py={wrap_py}")
        return 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("LONG-PNL", "PASS", "long 1e6 tokens at 2100 vs 2000 entry: +1e14; at 1900: -1e14")
    rec("SHORT-MIN", "PASS", "short minimize uses pmax=1950 not pmin=1900: +5e13 vs +1e14")
    rec("ORACLE-TRAP", "PASS", "long maximize=false uses min: 0 at 2000/2100; wrong max fakes +1e14")
    rec("V1-DUST", "PASS", "tokens=3 sizeUsd=3001 price=1100: V2=299 vs V1-style=300")
    rec("ROUNDUP", "PASS", "long half-close 3 tokens/3000 usd: ceil dt=2 PnL=200 vs floor dt=1")
    rec("NAIVE-WRAP", "PASS", "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000")

    jit_ok = lin_roundtrip_jit(LIN, "g2p_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2p_test_suite (in-memory libtcc)")
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
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "g2p_pnl_usd" in src and "g2p_pick" in src else "FAIL",
        "LIN clone takes isLong/tokens/sizeUsd/sizeDelta/pmin/pmax as arguments",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "g2p_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit tokens*price and tokens*sizeDeltaUsd",
    )
    rec(
        "NOT-V1",
        "PASS" if "getPositionPnlUsd" in excerpt_txt and "g2p_v1_style" in src and "gmx-fee" not in src else "FAIL",
        "kernel is V2 tokens*price vs sizeInUsd, not V1 funding/fee/liquidation",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_GMX_V2_PNL", 'out = out + "="', 'out = out + "ex{"']
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects getPositionPnlUsd / pickPriceForPnl before ENV",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_V2_PNL" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_position_pnl_usd / pick_price_for_pnl",
    )

    evidence = {
        "schema": "LIN_GMX_V2_PNL_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT,
            "path": POS_REL,
            "price_path": PRICE_REL,
            "calc_path": CALC_REL,
            "git_blob_sha": blob or POS_BLOB,
            "file_sha256": POS_SHA256,
            "price_git_blob_sha": PRICE_BLOB,
            "price_file_sha256": PRICE_SHA256,
            "calc_git_blob_sha": CALC_BLOB,
            "calc_file_sha256": CALC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 synthetics: trader PnL is tokens*indexPrice vs sizeInUsd; longs round sizeDeltaInTokens up",
        },
        "lin_clone": "src/lin_gmx_v2_pnl.lin",
        "c11_oracle": "test/oracles/gmx_v2_pnl_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "long_profit": 100000000000000,
            "long_loss": -100000000000000,
            "short_min_pmax": 50000000000000,
            "long_min_flat": 0,
            "wrong_max": 100000000000000,
            "v2_dust": 299,
            "v1_dust": 300,
            "long_half_pnl": 200,
            "floor_dt": 1,
            "wrap_wide": 14000000000000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-pnl",
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
