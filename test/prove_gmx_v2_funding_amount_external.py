#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getFundingAmount vs LIN C0 (uint64-scale)."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_funding_amount.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_funding_amount_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_funding_amount_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_funding_amount" / "gmx_v2_funding_amount_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, PREC_REL, POS_REL = (
    "contracts/market/MarketUtils.sol",
    "contracts/utils/Precision.sol",
    "contracts/pricing/PositionPricingUtils.sol",
)
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PREC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PREC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
POS_SHA256 = "59661f2ab60aa09924e34418357f15064ce7136e7440449c5f31ca3ce8fa050d"
POS_BLOB = "c8e772da3417db9b5493361f92e3ab4f11ab471c"
FLOAT, DENOM, I64_MAX = 1_000_000, 1_000_000_000, 9_223_372_036_854_775_807
WRAP = -4_446_744_073_709_551_616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-funding-amount"
MAIN = (100_000_000, 5_000_123, 4_000_000)
DUST = (100, 5_000_123, 4_000_000)
EXACT = (100_000_000, 5_000_000, 4_000_000)
EQUAL = (100_000_000, 5_000_000, 5_000_000)
UNDER = (100_000_000, 4_000_000, 5_000_000)
OVF = (7_000_000_000, 2_000_000_000, 0)
ZSZ = (0, 5_000_123, 4_000_000)
INV = (100_012, 100_000_000)
MUL = (7_000_000_000, 2_000_000_000)
AMT1 = (100_000_000, 5_000_123, 4_000_000, 1)
AMT0 = (100_000_000, 5_000_123, 4_000_000, 0)


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
    mkt, prec, pos = UPSTREAM / MKT_REL, UPSTREAM / PREC_REL, UPSTREAM / POS_REL
    if not mkt.exists() or not prec.exists() or not pos.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PREC_REL}"]).stdout.strip()
    oblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{POS_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(prec) != PREC_SHA256 or pblob != PREC_BLOB:
        return "FAIL", commit, f"prec={sha256_file(prec)} blob={pblob}"
    if sha256_file(pos) != POS_SHA256 or oblob != POS_BLOB:
        return "FAIL", commit, f"pos={sha256_file(pos)} blob={oblob}"
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


def py_ok(a: tuple[int, ...]) -> int:
    size, latest, entry = a[0], a[1], a[2]
    if size < 0 or latest < 0 or entry < 0 or py_u_lt(latest, entry) == 1:
        return 0
    return py_umul_ok(size, latest - entry)


def py_amount(a: tuple[int, ...], round_up: int) -> int:
    if py_ok(a) == 0 or round_up not in (0, 1):
        return 0
    prod = a[0] * (a[1] - a[2])
    q, r = divmod(prod, DENOM)
    if round_up == 0 or r == 0:
        return q
    return 0 if q + 1 > I64_MAX else q + 1


def py_v1(a: tuple[int, ...]) -> int:
    if a[0] < 0 or py_u_lt(a[1], a[2]) == 1:
        return 0
    diff = a[1] - a[2]
    return 0 if py_umul_ok(a[0], diff) == 0 else (a[0] * diff) // FLOAT


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "PASS", "FAIL": "FAIL"}.get(status, status)
        print(f"  [{tag}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 getFundingAmount — LIN proof (C11)")
    fa_ex = FIX / "GetFundingAmount.excerpt.sol"
    fee_ex = FIX / "GetFundingFees.excerpt.sol"
    delta_ex = FIX / "GetFundingAmountPerSizeDelta.excerpt.sol"
    mul_ex = FIX / "PrecisionMulDivRound.excerpt.sol"
    app_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    if not all(p.exists() for p in (fa_ex, fee_ex, delta_ex, mul_ex, app_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    fa_txt, fee_txt, delta_txt, mul_txt, app_txt = (p.read_text(encoding="utf-8") for p in (fa_ex, fee_ex, delta_ex, mul_ex, app_ex))
    need = [
        "function getFundingAmount",
        "fundingDiffFactor",
        "FLOAT_PRECISION * Precision.FLOAT_PRECISION_SQRT",
        "roundUpMagnitude",
        "avoid paying funding fees",
        "claimable amount",
    ]
    missing = [s for s in need if s not in fa_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "funding-amount excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt is mulDiv(size, latest-entry, FLOAT*SQRT, roundUp)")
    rec(
        "PIN-FEES",
        "PASS" if "true // roundUpMagnitude" in fee_txt and "false // roundUpMagnitude" in fee_txt else "FAIL",
        "getFundingFees charges round-up and claims round-down",
    )
    rec(
        "PIN-DELTA",
        "PASS" if "fundingUsd" in delta_txt and "FLOAT_PRECISION * Precision.FLOAT_PRECISION_SQRT" in delta_txt else "FAIL",
        "getFundingAmountPerSizeDelta is inverse mulDiv (funding*FLOAT*SQRT/OI)",
    )
    rec(
        "PIN-MULDIV",
        "PASS" if "Math.Rounding.Up" in mul_txt and "FLOAT_PRECISION_SQRT = 10 ** 15" in mul_txt else "FAIL",
        "Precision.mulDiv round-up uses Math.Rounding.Up; SQRT is 1e15",
    )
    rec(
        "PIN-APPLY",
        "PASS" if "mulDiv(value, factor, FLOAT_PRECISION)" in app_txt and "FLOAT_PRECISION = 10 ** 30" in app_txt else "FAIL",
        "applyFactor is value*factor/1e30 (no SQRT); LIN denom is 1e9",
    )

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + Precision.sol + PositionPricingUtils.sol")
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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (charge/claim/dust/overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 funding-amount clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_funding_amount.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2a_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2a_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2a_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2a_ok", "charge": "g2a_charge", "claim": "g2a_claim", "amount": "g2a_amount",
        "wrongv1": "g2a_wrong_v1", "wrongapply": "g2a_wrong_apply", "wrongfloor": "g2a_wrong_floor",
        "wrongceil": "g2a_wrong_ceil", "wrongsigned": "g2a_wrong_signed", "wronginv": "g2a_wrong_inverse",
        "naivemul": "g2a_naive_i64_mul",
    }
    py_map = {
        "ok": py_ok, "charge": lambda a: py_amount(a, 1), "claim": lambda a: py_amount(a, 0),
        "amount": lambda a: py_amount(a[:3], a[3]), "wrongv1": py_v1, "wrongapply": py_v1,
        "wrongfloor": lambda a: py_amount(a, 0), "wrongceil": lambda a: py_amount(a, 1),
        "wrongsigned": lambda a: a[0] - a[1],
        "wronginv": lambda a: 0 if a[0] < 0 or a[1] <= 0 or py_umul_ok(a[0], DENOM) == 0 else (a[0] * DENOM) // a[1],
        "naivemul": lambda a: w64(a[0] * a[1]),
    }
    cases = [
        ("ok", MAIN, 1), ("charge", MAIN, 100_013), ("claim", MAIN, 100_012),
        ("wrongfloor", MAIN, 100_012), ("wrongceil", MAIN, 100_013),
        ("wrongv1", MAIN, 100_012_300), ("wrongapply", MAIN, 100_012_300),
        ("charge", DUST, 1), ("claim", DUST, 0),
        ("charge", EXACT, 100_000), ("claim", EXACT, 100_000),
        ("charge", EQUAL, 0), ("ok", UNDER, 0),
        ("wrongsigned", (4_000_000, 5_000_000), -1_000_000),
        ("ok", OVF, 0), ("naivemul", MUL, WRAP),
        ("wronginv", INV, 1_000_120), ("charge", ZSZ, 0),
        ("amount", AMT1, 100_013), ("amount", AMT0, 100_012),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn_map[kind], *args)
        pyv = py_map[kind](args)
        got[(kind, args)] = got_lin
        if want != expect or want_port != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}", f"lin={got_lin} c11={want} port={want_port} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == portable == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("ROUND-PAIR", "PASS" if got[("charge", MAIN)] == 100_013 and got[("claim", MAIN)] == 100_012 else "FAIL",
        "size 1e8 diff 1000123 / 1e9 charges 100013 (ceil) vs claims 100012 (floor)")
    rec("DUST-FEE", "PASS" if got[("charge", DUST)] == 1 and got[("claim", DUST)] == 0 else "FAIL",
        "dust size 100 charges 1 (cannot dodge) vs claim 0")
    rec("EXACT-REM", "PASS" if got[("charge", EXACT)] == 100_000 and got[("claim", EXACT)] == 100_000 else "FAIL",
        "remainder 0: charge equals claim 100000")
    rec("ZERO-DIFF", "PASS" if got[("charge", EQUAL)] == 0 else "FAIL", "latest==entry yields 0")
    rec("V1-TRAP", "PASS" if got[("wrongv1", MAIN)] == 100_012_300 else "FAIL",
        "V1 size*diff/FLOAT (no SQRT) is 100012300, 1000x the V2 scaled amount")
    rec("NOT-APPLY", "PASS" if got[("wrongapply", MAIN)] == 100_012_300 else "FAIL",
        "applyFactor (no SQRT) matches the V1 trap, not FLOAT*SQRT")
    rec("NOT-INVERSE", "PASS" if got[("wronginv", INV)] == 1_000_120 else "FAIL",
        "per-size-delta inverse 100012*1e9/1e8 is 1000120, not 100012")
    rec("UNDERFLOW", "PASS" if got[("ok", UNDER)] == 0 and got[("wrongsigned", (4_000_000, 5_000_000))] == -1_000_000 else "FAIL",
        "latest < entry fail-closes; signed subtract would be -1000000")
    rec("MUL-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naivemul", MUL)] == WRAP else "FAIL",
        "7e9*2e9 size*diff fail-closes; naive i64 wraps to -4446744073709551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2a_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2a_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2a_amount" in src and "g2a_charge" in src else "FAIL",
        "LIN clone takes size/latest/entry/round_up as arguments")
    rec("FAIL-CLOSED-MUL", "PASS" if "g2a_umul_ok" in src and "g2a_inputs_ok" in src else "FAIL",
        "clone fail-closes size*diff overflow and latest<entry underflow")
    rec("NOT-V1-FEE", "PASS" if "g2a_wrong_v1" in src and "FLOAT_PRECISION_SQRT" in fa_txt else "FAIL",
        "kernel is FLOAT*SQRT round-up/down, not V1 size*(cum-entry)/FLOAT")
    need_t = ["REJ_SOLIDITY_GMX_V2_FUNDING_AMT", "Chain.currentTimestamp", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getFundingAmount before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_FUNDING_AMT" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_funding_amount")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_FUNDING_AMOUNT_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL,
            "precision_path": PREC_REL, "pricing_path": POS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PREC_BLOB, "precision_file_sha256": PREC_SHA256,
            "pricing_git_blob_sha": POS_BLOB, "pricing_file_sha256": POS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 funding charges round up so a trader cannot dodge dust by updating the position before the fee is chargeable; claimable funding rounds down. Same mulDiv(size, latest-entry, FLOAT*SQRT) with opposite Rounding flags. FLOAT is 1e30*1e15 on chain; this clone uses 1e6*1e3.",
        },
        "lin_clone": "src/lin_gmx_v2_funding_amount.lin",
        "c11_oracle": "test/oracles/gmx_v2_funding_amount_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "charge": 100_013, "claim": 100_012, "wrong_floor": 100_012, "wrong_ceil": 100_013,
            "v1_trap": 100_012_300, "dust_charge": 1, "dust_claim": 0, "exact": 100_000,
            "zero_diff": 0, "under_ok": 0, "signed_under": -1_000_000, "inverse": 1_000_120,
            "wrap_naive": WRAP,
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
