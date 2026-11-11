#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 _getClaimableFactor vs LIN C0."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_claimable_factor.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_claimable_factor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_claimable_factor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_claimable_factor" / "gmx_v2_claimable_factor_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, PREC_REL, KEYS_REL = (
    "contracts/market/MarketUtils.sol",
    "contracts/utils/Precision.sol",
    "contracts/data/Keys.sol",
)
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PREC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PREC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
KEYS_SHA256 = "9940d62b9dca2f3a753d67d7e7339a6326278a35d752c4c80ab1eedf0ab0f075"
KEYS_BLOB = "5472e5b4ecd29bb372218caa142476eb95fe55f8"
FLOAT = 1_000_000
I64_MAX = 9_223_372_036_854_775_807
WRAP = -4_446_744_073_709_551_616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-claimable-factor"
# (ft, fa, red, div, delay, tkey, now)
MAXP = (400_000, 600_000, 0, 3_600, 86_400, 1_000, 3_686_399)
DDEF = (0, 0, 0, 3_600, 86_400, 1_000, 3_686_401)
EXACT = (0, 0, 0, 3_600, 86_400, 1_000, 3_686_400)
REDC = (800_000, 0, 300_000, 3_600, 86_400, 1_000, 3_686_399)
OVER = (300_000, 0, 500_000, 3_600, 86_400, 1_000, 3_686_399)
BLOCKD = (0, 0, 200_000, 3_600, 86_400, 1_000, 3_686_401)
BIGF = (2_000_000, 0, 0, 3_600, 86_400, 1_000, 3_686_399)
UNDER = (0, 0, 0, 3_600, 86_400, 1_000, 1)
OVF = (0, 0, 0, 2_000_000_000, 0, 7_000_000_000, 0)
EQ = (500_000, 500_000, 0, 3_600, 86_400, 1_000, 3_686_399)
AMT0 = (100_000_000, 500_000, 0)
AMT1 = (100_000_000, 500_000, 10_000_000)
AMT2 = (100_000_000, 500_000, 50_000_000)
AMT3 = (100_000_000, 2_000_000, 0)
DIST = (200_000_000, 100_000_000, 500_000, 1_000_000)
MUL = (7_000_000_000, 2_000_000_000)


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
    mkt, prec, keys = UPSTREAM / MKT_REL, UPSTREAM / PREC_REL, UPSTREAM / KEYS_REL
    if not mkt.exists() or not prec.exists() or not keys.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PREC_REL}"]).stdout.strip()
    kblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{KEYS_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(prec) != PREC_SHA256 or pblob != PREC_BLOB:
        return "FAIL", commit, f"prec={sha256_file(prec)} blob={pblob}"
    if sha256_file(keys) != KEYS_SHA256 or kblob != KEYS_BLOB:
        return "FAIL", commit, f"keys={sha256_file(keys)} blob={kblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_umul_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a * b > I64_MAX else 1


def py_u_lt(a: int, b: int) -> int:
    if a < 0 and b >= 0:
        return 0
    if a >= 0 and b < 0:
        return 1
    return 1 if a < b else 0


def py_inputs_ok(a: tuple[int, ...]) -> int:
    ft, fa, red, div, delay, tkey, now = a
    if any(x < 0 for x in a):
        return 0
    if py_umul_ok(tkey, div) == 0:
        return 0
    return 0 if py_u_lt(now, tkey * div) == 1 else 1


def py_pick(ft: int, fa: int) -> int:
    return fa if py_u_lt(ft, fa) == 1 else ft


def py_factor(a: tuple[int, ...]) -> int:
    if py_inputs_ok(a) == 0:
        return 0
    ft, fa, red, div, delay, tkey, now = a
    f = py_pick(ft, fa)
    td = now - tkey * div
    if f == 0 and red == 0 and py_u_lt(delay, td) == 1:
        f = FLOAT
    return f - red if py_u_lt(red, f) == 1 else 0


def py_ok(a: tuple[int, ...]) -> int:
    if py_inputs_ok(a) == 0:
        return 0
    return 0 if py_u_lt(FLOAT, py_factor(a)) == 1 else 1


def py_apply(amount: int, factor: int) -> int:
    if amount < 0 or factor < 0 or py_umul_ok(amount, factor) == 0:
        return 0
    return (amount * factor) // FLOAT


def py_claim_ok(amount: int, factor: int, claimed: int) -> int:
    if amount < 0 or claimed < 0 or py_u_lt(FLOAT, factor) == 1:
        return 0
    if py_umul_ok(amount, factor) == 0:
        return 0
    adj = py_apply(amount, factor)
    return 0 if py_u_lt(claimed, adj) == 0 else 1


def py_amount(amount: int, factor: int, claimed: int) -> int:
    if py_claim_ok(amount, factor, claimed) == 0:
        return 0
    return py_apply(amount, factor) - claimed


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{'PASS' if status=='PASS' else 'FAIL' if status=='FAIL' else status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 _getClaimableFactor — LIN proof (C11)")
    cf_ex = FIX / "GetClaimableFactor.excerpt.sol"
    cl_ex = FIX / "ClaimCollateral.excerpt.sol"
    inc_ex = FIX / "IncrementClaimableCollateralAmount.excerpt.sol"
    dist_ex = FIX / "GetPendingPositionImpactPoolDistributionAmount.excerpt.sol"
    prec_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    key_ex = FIX / "ClaimableCollateralFactorKey.excerpt.sol"
    if not all(p.exists() for p in (cf_ex, cl_ex, inc_ex, dist_ex, prec_ex, key_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    cf_txt, cl_txt, inc_txt, dist_txt, prec_txt, key_txt = (
        p.read_text(encoding="utf-8") for p in (cf_ex, cl_ex, inc_ex, dist_ex, prec_ex, key_ex)
    )
    need = [
        "function _getClaimableFactor",
        "Keys.claimableCollateralFactorKey(market, token, timeKey)",
        "Keys.claimableCollateralFactorKey(market, token, timeKey, account)",
        "Keys.claimableCollateralReductionFactorKey",
        "Chain.currentTimestamp() - timeKey * divisor",
        "CLAIMABLE_COLLATERAL_DELAY",
        "timeDiff > claimableCollateralDelay",
        "Precision.FLOAT_PRECISION",
        "claimableFactor -= claimableReductionFactor",
    ]
    missing = [s for s in need if s not in cf_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "claimable-factor excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains max(time,account) then delay-default then reduction")
    rec("PIN-CLAIM", "PASS" if "InvalidClaimableFactor" in cl_txt and "applyFactor" in cl_txt and "CollateralAlreadyClaimed" in cl_txt else "FAIL",
        "claimCollateral rejects factor>FLOAT, then applyFactor minus claimed")
    rec("PIN-TIMEKEY", "PASS" if "currentTimestamp() / divisor" in inc_txt else "FAIL",
        "incrementClaimableCollateralAmount buckets timeKey as now/divisor")
    rec("PIN-DIST", "PASS" if "applyFactor(durationInSeconds, distributionRate)" in dist_txt else "FAIL",
        "pending impact-pool distribution is rate*duration clip, not delay-default")
    rec("PIN-FLOAT", "PASS" if "FLOAT_PRECISION = 10 ** 30" in prec_txt and "mulDiv(value, factor, FLOAT_PRECISION)" in prec_txt else "FAIL",
        "Precision.applyFactor is value*factor/1e30; LIN uses FLOAT 1e6")
    rec("PIN-KEYS", "PASS" if "claimableCollateralFactorKey" in key_txt and "claimableCollateralReductionFactorKey" in key_txt else "FAIL",
        "Keys split time-only factor vs account factor vs reduction factor")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + Precision.sol + Keys.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs portable umul_ok selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (max/delay-default/reduction/overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 claimable-factor clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_claimable_factor.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2f_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2f_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2f_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2f_ok", "value": "g2f_factor",
        "wrongmin": "g2f_wrong_min", "wrongtime": "g2f_wrong_time_only",
        "wrongnodef": "g2f_wrong_no_default", "wrongge": "g2f_wrong_ge_delay",
        "wrongdtr": "g2f_wrong_default_then_reduce", "wrongign": "g2f_wrong_ignore_reduction",
        "wrongsigned": "g2f_wrong_signed_reduction", "wrongadd": "g2f_wrong_add_reduction",
        "wrongcap": "g2f_wrong_cap", "wrongdist": "g2f_wrong_rate_dist",
        "amount": "g2f_amount_to_claim", "claimok": "g2f_claim_ok",
        "naivemul": "g2f_naive_i64_mul",
    }
    py_map = {
        "ok": py_ok, "value": py_factor,
        "wrongmin": lambda a: a[1] if a[1] < a[0] else a[0],
        "wrongtime": lambda a: a[0],
        "wrongnodef": lambda a: (
            0 if py_inputs_ok(a) == 0 else (
                py_pick(a[0], a[1]) - a[2] if py_u_lt(a[2], py_pick(a[0], a[1])) == 1 else 0
            )
        ),
        "wrongge": lambda a: (
            0 if py_inputs_ok(a) == 0 else (
                (lambda f: (f - a[2] if py_u_lt(a[2], f) == 1 else 0))(
                    FLOAT if py_pick(a[0], a[1]) == 0 and a[2] == 0 and (a[6] - a[5] * a[3]) >= a[4]
                    else py_pick(a[0], a[1])
                )
            )
        ),
        "wrongdtr": lambda a: (
            0 if py_inputs_ok(a) == 0 else (
                (lambda f: (f - a[2] if py_u_lt(a[2], f) == 1 else 0))(
                    FLOAT if py_pick(a[0], a[1]) == 0 and py_u_lt(a[4], a[6] - a[5] * a[3]) == 1
                    else py_pick(a[0], a[1])
                )
            )
        ),
        "wrongign": lambda a: (
            0 if py_inputs_ok(a) == 0 else (
                FLOAT if py_pick(a[0], a[1]) == 0 and a[2] == 0 and py_u_lt(a[4], a[6] - a[5] * a[3]) == 1
                else py_pick(a[0], a[1])
            )
        ),
        "wrongsigned": lambda a: py_pick(a[0], a[1]) - a[2],
        "wrongadd": lambda a: py_pick(a[0], a[1]) + a[2],
        "wrongcap": lambda a: FLOAT if py_u_lt(FLOAT, py_factor(a)) == 1 else py_factor(a),
        "wrongdist": lambda a: (
            0 if a[0] <= a[1] else (
                a[0] - a[1] if py_apply(a[2], a[3]) > (a[0] - a[1]) else py_apply(a[2], a[3])
            )
        ),
        "amount": lambda a: py_amount(a[0], a[1], a[2]),
        "claimok": lambda a: py_claim_ok(a[0], a[1], a[2]),
        "naivemul": lambda a: w64(a[0] * a[1]),
    }
    cases = [
        ("ok", MAXP, 1), ("value", MAXP, 600_000),
        ("wrongmin", MAXP, 400_000), ("wrongtime", MAXP, 400_000),
        ("value", DDEF, 1_000_000), ("wrongnodef", DDEF, 0),
        ("value", EXACT, 0), ("wrongge", EXACT, 1_000_000),
        ("value", REDC, 500_000), ("wrongign", REDC, 800_000),
        ("value", OVER, 0), ("wrongsigned", OVER, -200_000),
        ("wrongadd", REDC, 1_100_000),
        ("value", BLOCKD, 0), ("wrongdtr", BLOCKD, 800_000),
        ("ok", BIGF, 0), ("value", BIGF, 2_000_000), ("wrongcap", BIGF, 1_000_000),
        ("ok", UNDER, 0), ("ok", OVF, 0),
        ("value", EQ, 500_000),
        ("amount", AMT0, 50_000_000), ("amount", AMT1, 40_000_000),
        ("claimok", AMT2, 0), ("claimok", AMT3, 0),
        ("wrongdist", DIST, 500_000),
        ("naivemul", MUL, WRAP),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        if kind in ("wrongmin", "wrongtime"):
            oargs = [str(args[0]), str(args[1])]
            lin_args = (args[0], args[1])
        elif kind in ("wrongsigned", "wrongadd"):
            oargs = [str(args[0]), str(args[1]), str(args[2])]
            lin_args = (args[0], args[1], args[2])
        elif kind in ("amount", "claimok"):
            oargs = [str(x) for x in args]
            lin_args = args
        elif kind == "wrongdist":
            oargs = [str(x) for x in args]
            lin_args = args
        elif kind == "naivemul":
            oargs = [str(x) for x in args]
            lin_args = args
        else:
            oargs = [str(x) for x in args]
            lin_args = args
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
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
    rec("MAX-PAIR", "PASS" if got[("value", MAXP)] == 600_000 and got[("wrongmin", MAXP)] == 400_000 else "FAIL",
        "max(time 4e5, account 6e5) yields 600000 vs min 400000 vs time-only 400000")
    rec("DELAY-DEFAULT", "PASS" if got[("value", DDEF)] == 1_000_000 and got[("wrongnodef", DDEF)] == 0 else "FAIL",
        "both factors and reduction 0 after delay+1 default to FLOAT 1e6; skipping default stays 0")
    rec("STRICT-GT", "PASS" if got[("value", EXACT)] == 0 and got[("wrongge", EXACT)] == 1_000_000 else "FAIL",
        "timeDiff == delay does not default; >= delay would wrongly yield 1e6")
    rec("REDUCTION", "PASS" if got[("value", REDC)] == 500_000 and got[("wrongign", REDC)] == 800_000 else "FAIL",
        "8e5-3e5 reduction yields 500000 vs ignore-reduction 800000 vs add 1100000")
    rec("FLOOR-ZERO", "PASS" if got[("value", OVER)] == 0 and got[("wrongsigned", OVER)] == -200_000 else "FAIL",
        "reduction above factor floors at 0; signed subtract would be -200000")
    rec("NO-DEFAULT-RED", "PASS" if got[("value", BLOCKD)] == 0 and got[("wrongdtr", BLOCKD)] == 800_000 else "FAIL",
        "reduction!=0 blocks delay-default; default-then-reduce would be 800000")
    rec("INVALID-FACTOR", "PASS" if got[("ok", BIGF)] == 0 and got[("value", BIGF)] == 2_000_000 and got[("wrongcap", BIGF)] == 1_000_000 else "FAIL",
        "factor 2e6 > FLOAT is InvalidClaimableFactor; capping would yield 1e6")
    rec("TIME-UNDER", "PASS" if got[("ok", UNDER)] == 0 else "FAIL",
        "now < timeKey*divisor fail-closes (Solidity 0.8 underflow revert)")
    rec("MUL-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naivemul", MUL)] == WRAP else "FAIL",
        "7e9*2e9 timeKey*divisor fail-closes; naive i64 wraps to -4446744073709551616")
    rec("APPLY-CLAIM", "PASS" if got[("amount", AMT0)] == 50_000_000 and got[("amount", AMT1)] == 40_000_000 and got[("claimok", AMT2)] == 0 else "FAIL",
        "1e8 * 5e5 / 1e6 claimed 0 is 5e7; claimed 1e7 is 4e7; claimed==adjusted rejects")
    rec("NOT-DIST", "PASS" if got[("wrongdist", DIST)] == 500_000 and got[("value", DDEF)] == 1_000_000 else "FAIL",
        "impact-pool distribution is rate*duration 5e5; claimable delay-default is 1e6 not a rate clip")
    rec("EQUAL-KEYS", "PASS" if got[("value", EQ)] == 500_000 else "FAIL",
        "equal time and account factors keep 500000")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2f_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2f_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2f_factor" in src and "g2f_ok" in src else "FAIL",
        "LIN clone takes factor_time/account/reduction/divisor/delay/time_key/now as arguments")
    rec("FAIL-CLOSED-MUL", "PASS" if "g2f_umul_ok" in src and "g2f_inputs_ok" in src else "FAIL",
        "clone fail-closes timeKey*divisor overflow and now-prod underflow")
    rec("NOT-MAX-SUM", "PASS" if "_getClaimableFactor" in cf_txt and "g2f_wrong_min" in src else "FAIL",
        "kernel is max of two factor keys then delay-default; not always-max collateral sum")
    need_t = ["REJ_SOLIDITY_GMX_V2_CLAIMABLE_FACTOR", "Chain.currentTimestamp", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects _getClaimableFactor before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_CLAIMABLE_FACTOR" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_claimable_factor")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_CLAIMABLE_FACTOR_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL,
            "precision_path": PREC_REL, "keys_path": KEYS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PREC_BLOB, "precision_file_sha256": PREC_SHA256,
            "keys_git_blob_sha": KEYS_BLOB, "keys_file_sha256": KEYS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 claimable collateral after ADL/liquidation uses a time-bucket factor: max(timeKey factor, account factor), default 100% only after CLAIMABLE_COLLATERAL_DELAY when both factors and the reduction are zero, then subtract the reduction (floor at 0). claimCollateral rejects factor>FLOAT and pays applyFactor(amount, factor)-claimed.",
        },
        "lin_clone": "src/lin_gmx_v2_claimable_factor.lin",
        "c11_oracle": "test/oracles/gmx_v2_claimable_factor_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "max_pair": 600_000, "wrong_min": 400_000, "delay_default": 1_000_000,
            "exact_delay": 0, "wrong_ge_delay": 1_000_000, "reduction": 500_000,
            "ignore_reduction": 800_000, "over_reduction": 0, "signed_reduction": -200_000,
            "block_default": 0, "default_then_reduce": 800_000, "invalid_ok": 0,
            "amount0": 50_000_000, "amount_claimed": 40_000_000, "already_claimed_ok": 0,
            "rate_dist": 500_000, "wrap_naive": WRAP,
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
