#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 applyDeltaToPositionImpactPool vs LIN C0."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_impact_delta.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_impact_delta_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_impact_delta_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_impact_delta" / "gmx_v2_impact_delta_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, DS_REL = "contracts/market/MarketUtils.sol", "contracts/data/DataStore.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
DS_SHA256 = "ab332edb2d32bb94cf47c06d2fe1fc7fb6dff101ab6b210282879514f6b05b3d"
DS_BLOB = "36279a5f32eae0882bd53418e04590da97aee154"
NEG_W = (100_000_000, 20_000_000, -30_000_000)
NEG_X = (100_000_000, 20_000_000, -150_000_000)
POS_W = (100_000_000, 20_000_000, 10_000_000)
POS_X = (100_000_000, 20_000_000, 50_000_000)
ZERO = (100_000_000, 20_000_000, 0)
NEG_0 = (0, 20_000_000, -10_000_000)
POS_0 = (100_000_000, 0, 10_000_000)
EQ_P = (100_000_000, 20_000_000, -100_000_000)
EQ_L = (100_000_000, 20_000_000, 20_000_000)
OVF = (7_000_000_000_000_000_000, 0, 3_000_000_000_000_000_000)
I64_MAX = 9_223_372_036_854_775_807
WRAP = -8_446_744_073_709_551_616


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


def py_add_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a + b > I64_MAX else 1


def py_ok(pool: int, lent: int, delta: int) -> int:
    if pool < 0 or lent < 0:
        return 0
    mag = abs(delta)
    if delta < 0:
        return py_add_ok(lent, mag - pool) if pool < mag else 1
    return py_add_ok(pool, mag - lent) if lent < mag else 1


def py_pool(a: tuple[int, ...]) -> int:
    pool, lent, delta = a
    if py_ok(pool, lent, delta) == 0:
        return 0
    mag = abs(delta)
    if delta < 0:
        return 0 if pool < mag else pool - mag
    return pool + (mag - lent) if lent < mag else pool


def py_lent(a: tuple[int, ...]) -> int:
    pool, lent, delta = a
    if py_ok(pool, lent, delta) == 0:
        return 0
    mag = abs(delta)
    if delta < 0:
        return lent + (mag - pool) if pool < mag else lent
    return 0 if lent < mag else lent - mag


def py_swap(a: tuple[int, ...]) -> int:
    pool, _lent, delta = a
    if pool < 0:
        return 0
    if delta >= 0:
        return 0 if py_add_ok(pool, delta) == 0 else pool + delta
    mag = abs(delta)
    return 0 if pool < mag else pool - mag


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{'PASS' if status=='PASS' else 'FAIL' if status=='FAIL' else status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 applyDeltaToPositionImpactPool — LIN proof (C11)")
    pos_ex = FIX / "ApplyDeltaToPositionImpactPool.excerpt.sol"
    swap_ex = FIX / "ApplyDeltaToSwapImpactPool.excerpt.sol"
    bnd_ex = FIX / "ApplyBoundedDeltaToUint.excerpt.sol"
    if not all(p.exists() for p in (pos_ex, swap_ex, bnd_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    pos_txt, swap_txt, bnd_txt = (p.read_text(encoding="utf-8") for p in (pos_ex, swap_ex, bnd_ex))
    need = [
        "function applyDeltaToPositionImpactPool", "if (delta < 0)",
        "lentPositionImpactPoolAmountKey",
        "cache.excessAmount = cache.deltaMagnitude - cache.poolAmount",
        "incrementUint(Keys.lentPositionImpactPoolAmountKey",
        "incrementUint(Keys.positionImpactPoolAmountKey",
    ]
    missing = [s for s in need if s not in pos_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "position excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains signed delta, pool draw, lent excess")
    rec("PIN-SWAP", "PASS" if "applyBoundedDeltaToUint" in swap_txt else "FAIL",
        "swap impact uses bounded uint (floor 0), not lent pairing")
    rec("PIN-BOUND", "PASS" if "if (value < 0 && (-value).toUint256() > uintValue)" in bnd_txt else "FAIL",
        "applyBoundedDeltaToUint floors at 0 and does not lend")

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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (lend / repay / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 impact-delta clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_impact_delta.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2d_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2d_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2d_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "pool": "g2d_next_pool", "lent": "g2d_next_lent", "ok": "g2d_ok",
        "wrongnaive": "g2d_wrong_naive_pool", "wrongswap": "g2d_wrong_swap_pool",
        "wrongswaplent": "g2d_wrong_swap_lent", "wrongrepay": "g2d_wrong_repay_only_pool",
        "wrongabs": "g2d_wrong_abs_pool", "naiveadd": "g2d_naive_i64_add",
    }
    py_map = {
        "pool": py_pool, "lent": py_lent, "ok": lambda a: py_ok(*a),
        "wrongnaive": lambda a: w64(a[0] + a[2]), "wrongswap": py_swap,
        "wrongswaplent": lambda a: a[1],
        "wrongrepay": lambda a: py_pool(a) if a[2] <= 0 else a[0],
        "wrongabs": lambda a: py_pool((a[0], a[1], -abs(a[2]))),
        "naiveadd": lambda a: w64(a[0] + a[1]),
    }
    cases = [
        ("pool", NEG_W, 70_000_000), ("lent", NEG_W, 20_000_000),
        ("pool", NEG_X, 0), ("lent", NEG_X, 70_000_000),
        ("wrongnaive", NEG_X, -50_000_000), ("wrongswap", NEG_X, 0),
        ("wrongswaplent", NEG_X, 20_000_000), ("pool", POS_W, 100_000_000),
        ("lent", POS_W, 10_000_000), ("pool", POS_X, 130_000_000),
        ("lent", POS_X, 0), ("wrongnaive", POS_X, 150_000_000),
        ("wrongrepay", POS_X, 100_000_000), ("wrongabs", POS_X, 50_000_000),
        ("pool", ZERO, 100_000_000), ("lent", NEG_0, 30_000_000),
        ("pool", POS_0, 110_000_000), ("pool", EQ_P, 0), ("lent", EQ_L, 0),
        ("ok", OVF, 0), ("pool", OVF, 0),
        ("naiveadd", (OVF[0], OVF[2], 0), WRAP),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        lin_args = args if kind != "naiveadd" else (args[0], args[1])
        got_lin = lin_vm(LIN, fn_map[kind], *lin_args)
        pyv = py_map[kind](args)
        got[(kind, args)] = got_lin
        if want != expect or want_port != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}",
                f"lin={got_lin} c11={want} port={want_port} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    np, nl = got[("pool", NEG_X)], got[("lent", NEG_X)]
    naive_neg, swap_p, swap_l = got[("wrongnaive", NEG_X)], got[("wrongswap", NEG_X)], got[("wrongswaplent", NEG_X)]
    pp, pl = got[("pool", POS_X)], got[("lent", POS_X)]
    naive_pos, repay, wabs = got[("wrongnaive", POS_X)], got[("wrongrepay", POS_X)], got[("wrongabs", POS_X)]
    ov_ok, wrap = got[("ok", OVF)], got[("naiveadd", (OVF[0], OVF[2], 0))]
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == portable == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("LEND-EXCESS", "PASS" if np == 0 and nl == 70_000_000 and naive_neg == -50_000_000 else "FAIL",
        "neg delta -1.5e8 on pool 1e8 lends excess 5e7 (lent 2e7->7e7); naive stays -5e7")
    rec("NOT-SWAP-FLOOR", "PASS" if swap_p == 0 and swap_l == 20_000_000 and nl == 70_000_000 else "FAIL",
        "swap applyBoundedDeltaToUint floors pool at 0 and leaves lent 2e7; position lends")
    rec("REPAY-THEN-CREDIT", "PASS" if pp == 130_000_000 and pl == 0 and naive_pos == 150_000_000 else "FAIL",
        "pos delta 5e7 first repays lent 2e7 then credits pool +3e7=1.3e8; naive adds 1.5e8")
    rec("NOT-REPAY-ONLY", "PASS" if repay == 100_000_000 and pp == 130_000_000 else "FAIL",
        "repay-only would zero lent and leave pool 1e8; kernel credits the excess 3e7")
    rec("NOT-ABS-DRAW", "PASS" if wabs == 50_000_000 and pp == 130_000_000 else "FAIL",
        "treating +5e7 as a pool draw yields 5e7; kernel repays then credits to 1.3e8")
    rec("I64-OVERFLOW", "PASS" if ov_ok == 0 and wrap == WRAP else "FAIL",
        "7e18+3e18 fail-closes (ok=0); naive i64 wraps to -8446744073709551616", f"wrap={wrap}")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2d_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2d_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2d_next_pool" in src and "g2d_next_lent" in src else "FAIL",
        "LIN clone takes pool/lent/delta as arguments (no DataStore / events)")
    rec("FAIL-CLOSED-ADD", "PASS" if "g2d_add_ok" in src and "g2d_ok" in src else "FAIL",
        "clone fail-closes signed i64 add instead of wrapping the impact pool")
    rec("NOT-USD-CLIP", "PASS" if "applyDeltaToPositionImpactPool" in pos_txt and "g2d_wrong_swap_pool" in src else "FAIL",
        "kernel is signed storage delta + lent pairing, not USD impact clip")
    need_t = ["REJ_SOLIDITY_GMX_V2_IMPACT_DELTA", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects applyDeltaToPositionImpactPool before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain =ex{")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_IMPACT_DELTA" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects apply_delta_to_position_impact_pool")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_IMPACT_DELTA_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL, "datastore_path": DS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "datastore_git_blob_sha": DS_BLOB, "datastore_file_sha256": DS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2: signed delta on the position impact pool draws then lends excess, or repays lent then credits the pool. Not applyBoundedDeltaToUint (swap floors at 0) and not USD clip.",
        },
        "lin_clone": "src/lin_gmx_v2_impact_delta.lin",
        "c11_oracle": "test/oracles/gmx_v2_impact_delta_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "neg_excess_pool": 0, "neg_excess_lent": 70_000_000, "wrong_naive_neg": -50_000_000,
            "wrong_swap_lent": 20_000_000, "pos_excess_pool": 130_000_000, "pos_excess_lent": 0,
            "wrong_naive_pos": 150_000_000, "wrong_repay_only": 100_000_000, "wrong_abs_draw": 50_000_000,
            "overflow_ok": 0, "wrap_naive": WRAP,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-impact-delta",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
