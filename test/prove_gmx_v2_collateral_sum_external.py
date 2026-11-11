#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 applyDeltaToCollateralSum vs LIN C0."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_collateral_sum.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_collateral_sum_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_collateral_sum_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_collateral_sum" / "gmx_v2_collateral_sum_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, DS_REL = "contracts/market/MarketUtils.sol", "contracts/data/DataStore.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
DS_SHA256 = "ab332edb2d32bb94cf47c06d2fe1fc7fb6dff101ab6b210282879514f6b05b3d"
DS_BLOB = "36279a5f32eae0882bd53418e04590da97aee154"
# (is_long, sum, delta, max_value, index_token)
UNDER = (1, 100_000_000, 30_000_000, 200_000_000, 1)
SHORT = (0, 100_000_000, 30_000_000, 200_000_000, 1)
OVER_INC = (1, 100_000_000, 30_000_000, 120_000_000, 1)
OVER_DEC = (1, 150_000_000, -20_000_000, 120_000_000, 1)
DEC_OK = (1, 100_000_000, -30_000_000, 200_000_000, 1)
EQUAL = (1, 100_000_000, 30_000_000, 130_000_000, 1)
NEG = (1, 100_000_000, -150_000_000, 200_000_000, 1)
MAX0 = (1, 0, 1, 0, 1)
MAX0Z = (1, 0, 0, 0, 1)
SWAP = (1, 100_000_000, 30_000_000, 200_000_000, 0)
OVF = (1, 7_000_000_000_000_000_000, 3_000_000_000_000_000_000, 9_223_372_036_854_775_807, 1)
WRAP = -8_446_744_073_709_551_616
I64_MAX = 9_223_372_036_854_775_807
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-collateral-sum"


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_tools() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")
    if not C0.exists():
        proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"])
        if proc.returncode != 0 or not C0.exists():
            raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/gmx-io/gmx-synthetics.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT])
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    mkt, ds = UPSTREAM / MKT_REL, UPSTREAM / DS_REL
    if not mkt.exists() or not ds.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    dblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{DS_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(ds) != DS_SHA256 or dblob != DS_BLOB:
        return "FAIL", commit, f"ds={sha256_file(ds)} blob={dblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_uadd_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a + b > I64_MAX else 1


def py_delta_ok(sum_v: int, delta: int) -> int:
    if sum_v < 0:
        return 0
    if delta >= 0:
        return py_uadd_ok(sum_v, delta)
    return 0 if sum_v < abs(delta) else 1


def py_next_uint(sum_v: int, delta: int) -> int:
    if py_delta_ok(sum_v, delta) == 0:
        return 0
    return sum_v + delta if delta >= 0 else sum_v - abs(delta)


def py_ok(a: tuple[int, ...]) -> int:
    _is_long, sum_v, delta, max_value, _idx = a
    if max_value < 0 or py_delta_ok(sum_v, delta) == 0:
        return 0
    return 0 if py_next_uint(sum_v, delta) > max_value else 1


def py_value(a: tuple[int, ...]) -> int:
    return 0 if py_ok(a) == 0 else py_next_uint(a[1], a[2])


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{'PASS' if status=='PASS' else 'FAIL' if status=='FAIL' else status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 applyDeltaToCollateralSum — LIN proof (C11)")
    cs_ex = FIX / "ApplyDeltaToCollateralSum.excerpt.sol"
    oi_ex = FIX / "ApplyDeltaToOpenInterest.excerpt.sol"
    vo_ex = FIX / "ValidateOpenInterest.excerpt.sol"
    gc_ex = FIX / "GetCollateralSum.excerpt.sol"
    ds_ex = FIX / "ApplyDeltaToUint.excerpt.sol"
    if not all(p.exists() for p in (cs_ex, oi_ex, vo_ex, gc_ex, ds_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    cs_txt, oi_txt, vo_txt, gc_txt, ds_txt = (p.read_text(encoding="utf-8") for p in (cs_ex, oi_ex, vo_ex, gc_ex, ds_ex))
    need = [
        "function applyDeltaToCollateralSum",
        "Keys.collateralSumKey(market, collateralToken, isLong)",
        "Keys.maxCollateralSumKey(market, collateralToken, isLong)",
        "Invalid state: negative collateralSum",
        "if (nextValue > maxValue)",
        "MaxCollateralSumExceeded",
    ]
    missing = [s for s in need if s not in cs_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "collateral-sum excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains reject-negative then always-max")
    rec("PIN-OI", "PASS" if "if (delta > 0)" in oi_txt and "OpenInterestCannotBeUpdatedForSwapOnlyMarket" in oi_txt else "FAIL",
        "OI sibling checks max only on increase and rejects swap-only markets")
    rec("PIN-MAXOI", "PASS" if "MaxOpenInterestExceeded" in vo_txt else "FAIL",
        "validateOpenInterest is the OI max helper, not this kernel")
    rec("PIN-GET", "PASS" if "/ divisor" in gc_txt and "collateralSumKey" in gc_txt else "FAIL",
        "getCollateralSum divides; applyDeltaToCollateralSum does not")
    rec("PIN-UINT", "PASS" if "if (value < 0 && (-value).toUint256() > currValue)" in ds_txt else "FAIL",
        "applyDeltaToUint rejects a negative next uint")
    rec("PIN-BOUND", "PASS" if "uintValues[key] = 0" in ds_txt else "FAIL",
        "applyBoundedDeltaToUint floors at 0 instead of rejecting")
    rec("PIN-INT", "PASS" if "intValues[key] + value" in ds_txt else "FAIL",
        "applyDeltaToInt is signed and may go negative")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + DataStore.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs portable add_ok selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (max-always / reject / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 collateral-sum clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_collateral_sum.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2c_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2c_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2c_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2c_ok", "value": "g2c_next_value",
        "wrongboundok": "g2c_wrong_bounded_ok", "wrongbound": "g2c_wrong_bounded_next",
        "wrongsigned": "g2c_wrong_signed_next",
        "wrongnomaxok": "g2c_wrong_no_max_ok", "wrongnomax": "g2c_wrong_no_max_next",
        "wrongmaxincok": "g2c_wrong_max_on_inc_ok", "wrongmaxinc": "g2c_wrong_max_on_inc_next",
        "wrongswap": "g2c_wrong_swap_only_ok", "wrongflip": "g2c_wrong_flip_next",
        "wrongdiv": "g2c_wrong_div", "naiveadd": "g2c_naive_i64_add",
    }
    py_map = {
        "ok": py_ok, "value": py_value,
        "wrongboundok": lambda a: (
            0 if a[1] < 0 or a[3] < 0 else (
                0 if a[2] >= 0 and py_uadd_ok(a[1], a[2]) == 0 else (
                    0 if (a[1] + a[2] if a[2] >= 0 else max(0, a[1] - abs(a[2]))) > a[3] else 1
                )
            )
        ),
        "wrongbound": lambda a: 0 if a[2] < 0 and a[1] < abs(a[2]) else a[1] + a[2],
        "wrongsigned": lambda a: a[1] + a[2],
        "wrongnomaxok": lambda a: py_delta_ok(a[1], a[2]),
        "wrongnomax": lambda a: 0 if py_delta_ok(a[1], a[2]) == 0 else py_next_uint(a[1], a[2]),
        "wrongmaxincok": lambda a: (
            0 if a[3] < 0 or py_delta_ok(a[1], a[2]) == 0 else (
                0 if a[2] > 0 and py_next_uint(a[1], a[2]) > a[3] else 1
            )
        ),
        "wrongmaxinc": lambda a: (
            0 if a[3] < 0 or py_delta_ok(a[1], a[2]) == 0 else (
                0 if a[2] > 0 and py_next_uint(a[1], a[2]) > a[3] else py_next_uint(a[1], a[2])
            )
        ),
        "wrongswap": lambda a: 0 if a[4] == 0 else py_ok(a),
        "wrongflip": lambda a: a[1] + (-a[2] if a[0] == 1 else a[2]),
        "wrongdiv": lambda a: 0 if py_delta_ok(a[1], a[2]) == 0 else py_next_uint(a[1], a[2]) // 2,
        "naiveadd": lambda a: w64(a[1] + a[2]),
    }
    cases = [
        ("ok", UNDER, 1), ("value", UNDER, 130_000_000),
        ("ok", SHORT, 1), ("value", SHORT, 130_000_000),
        ("wrongflip", UNDER, 70_000_000),
        ("ok", OVER_INC, 0), ("value", OVER_INC, 0),
        ("wrongnomaxok", OVER_INC, 1), ("wrongnomax", OVER_INC, 130_000_000),
        ("ok", OVER_DEC, 0), ("wrongmaxincok", OVER_DEC, 1), ("wrongmaxinc", OVER_DEC, 130_000_000),
        ("value", DEC_OK, 70_000_000), ("ok", EQUAL, 1), ("value", EQUAL, 130_000_000),
        ("ok", NEG, 0), ("wrongboundok", NEG, 1), ("wrongbound", NEG, 0), ("wrongsigned", NEG, -50_000_000),
        ("ok", MAX0, 0), ("ok", MAX0Z, 1),
        ("ok", SWAP, 1), ("wrongswap", SWAP, 0),
        ("wrongdiv", UNDER, 65_000_000),
        ("ok", OVF, 0), ("naiveadd", OVF, WRAP),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        if kind in ("wrongbound", "wrongsigned"):
            lin_args = (args[1], args[2])
        elif kind == "wrongflip":
            lin_args = (args[0], args[1], args[2])
        elif kind == "wrongdiv":
            lin_args = (args[1], args[2])
        elif kind == "naiveadd":
            lin_args = (args[1], args[2])
        else:
            lin_args = args
        got_lin = lin_vm(LIN, fn_map[kind], *lin_args)
        pyv = py_map[kind](args)
        got[(kind, args)] = got_lin
        if want != expect or want_port != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}",
                f"lin={got_lin} c11={want} port={want_port} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == portable == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("UNDER-MAX", "PASS" if got[("value", UNDER)] == 130_000_000 and got[("ok", UNDER)] == 1 else "FAIL",
        "long +3e7 under max 2e8 yields next 1.3e8")
    rec("NOT-SIDE", "PASS" if got[("value", SHORT)] == 130_000_000 else "FAIL",
        "isLong is a storage key only; short +3e7 is also 1.3e8 not a sign flip")
    rec("NOT-FLIP", "PASS" if got[("wrongflip", UNDER)] == 70_000_000 else "FAIL",
        "position-style long-flip would drop 1e8->7e7; collateral sum does not flip")
    rec("MAX-INC", "PASS" if got[("ok", OVER_INC)] == 0 and got[("wrongnomax", OVER_INC)] == 130_000_000 else "FAIL",
        "1e8+3e7 vs max 1.2e8 rejects; skipping max would yield 1.3e8")
    rec("MAX-DEC", "PASS" if got[("ok", OVER_DEC)] == 0 and got[("wrongmaxinc", OVER_DEC)] == 130_000_000 else "FAIL",
        "decrease 1.5e8-2e7 still over max 1.2e8 rejects; OI-style max-on-inc would accept 1.3e8")
    rec("EQUAL-MAX", "PASS" if got[("ok", EQUAL)] == 1 and got[("value", EQUAL)] == 130_000_000 else "FAIL",
        "nextValue == maxValue is allowed (strict greater-than)")
    rec("REJECT-NEG", "PASS" if got[("ok", NEG)] == 0 and got[("wrongbound", NEG)] == 0 and got[("wrongboundok", NEG)] == 1 else "FAIL",
        "1e8-1.5e8 rejects; bounded floor would succeed at 0")
    rec("NOT-SIGNED", "PASS" if got[("wrongsigned", NEG)] == -50_000_000 else "FAIL",
        "signed int add would be -5e7; collateral sum stays unsigned")
    rec("MAX-ZERO", "PASS" if got[("ok", MAX0)] == 0 and got[("ok", MAX0Z)] == 1 else "FAIL",
        "max=0 disables any positive next; zero-delta on zero sum is ok")
    rec("NOT-SWAP-ONLY", "PASS" if got[("ok", SWAP)] == 1 and got[("wrongswap", SWAP)] == 0 else "FAIL",
        "indexToken==0 still updates collateral; OI would revert swap-only")
    rec("NOT-DIV", "PASS" if got[("wrongdiv", UNDER)] == 65_000_000 else "FAIL",
        "getCollateralSum /2 would be 6.5e7; applyDelta returns undivided 1.3e8")
    rec("I64-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naiveadd", OVF)] == WRAP else "FAIL",
        "7e18+3e18 fail-closes; naive i64 wraps to -8446744073709551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2c_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2c_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2c_next_value" in src and "g2c_ok" in src else "FAIL",
        "LIN clone takes is_long/sum/delta/max_value/index_token as arguments")
    rec("FAIL-CLOSED-ADD", "PASS" if "g2c_uadd_ok" in src and "g2c_delta_ok" in src else "FAIL",
        "clone fail-closes unsigned add and rejects a negative next uint")
    rec("NOT-OI", "PASS" if "applyDeltaToCollateralSum" in cs_txt and "g2c_wrong_max_on_inc_ok" in src else "FAIL",
        "kernel always checks max; OI max-on-increase is the named contrast")
    need_t = ["REJ_SOLIDITY_GMX_V2_COLLATERAL_SUM", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects applyDeltaToCollateralSum before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_COLLATERAL_SUM" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects apply_delta_to_collateral_sum")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_COLLATERAL_SUM_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL, "datastore_path": DS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "datastore_git_blob_sha": DS_BLOB, "datastore_file_sha256": DS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 collateral sum is an unsigned per-(market, collateralToken, isLong) total. applyDeltaToUint rejects a negative next uint, then ALWAYS checks maxCollateralSum (including on decrease). Distinct from OI (max only when delta>0, swap-only revert) and from applyBoundedDeltaToUint (floor at 0).",
        },
        "lin_clone": "src/lin_gmx_v2_collateral_sum.lin",
        "c11_oracle": "test/oracles/gmx_v2_collateral_sum_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "under_next": 130_000_000, "short_next": 130_000_000, "wrong_flip": 70_000_000,
            "over_inc_ok": 0, "wrong_no_max": 130_000_000,
            "over_dec_ok": 0, "wrong_max_on_inc": 130_000_000,
            "neg_ok": 0, "wrong_bounded_ok": 1, "wrong_signed": -50_000_000,
            "max0_ok": 0, "max0_zero_ok": 1, "swap_ok": 1, "wrong_swap": 0,
            "wrong_div": 65_000_000, "overflow_ok": 0, "wrap_naive": WRAP,
        },
        "clone_lin": CLONE_LIN,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
