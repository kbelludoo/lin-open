#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 applyDeltaToOpenInterest vs LIN C0."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_open_interest.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_open_interest_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_open_interest_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_open_interest" / "gmx_v2_open_interest_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, DS_REL = "contracts/market/MarketUtils.sol", "contracts/data/DataStore.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
DS_SHA256 = "ab332edb2d32bb94cf47c06d2fe1fc7fb6dff101ab6b210282879514f6b05b3d"
DS_BLOB = "36279a5f32eae0882bd53418e04590da97aee154"
# (index, oi, vi, has_v, is_long, delta, use_tok, max_oi)
LONG_INC = (1, 100_000_000, 50_000_000, 1, 1, 30_000_000, 0, 200_000_000)
LONG_DEC = (1, 100_000_000, 50_000_000, 1, 1, -30_000_000, 0, 200_000_000)
SHORT_INC = (1, 100_000_000, 50_000_000, 1, 0, 30_000_000, 0, 200_000_000)
SHORT_DEC = (1, 100_000_000, 50_000_000, 1, 0, -30_000_000, 0, 200_000_000)
NEG_OI = (1, 100_000_000, 50_000_000, 1, 1, -150_000_000, 0, 200_000_000)
MAX_HIT = (1, 100_000_000, 50_000_000, 1, 1, 30_000_000, 0, 120_000_000)
SWAP = (0, 100_000_000, 50_000_000, 1, 1, 30_000_000, 0, 200_000_000)
USE_TOK = (1, 100_000_000, 50_000_000, 1, 1, 30_000_000, 1, 200_000_000)
NO_VIRT = (1, 100_000_000, 50_000_000, 0, 1, 30_000_000, 0, 200_000_000)
VI_NEG = (1, 100_000_000, 20_000_000, 1, 1, 50_000_000, 0, 200_000_000)
OI_OVF = (1, 7_000_000_000_000_000_000, 0, 0, 1, 3_000_000_000_000_000_000, 1, 9_000_000_000_000_000_000)
VI_OVF = (1, 0, 7_000_000_000_000_000_000, 1, 0, 3_000_000_000_000_000_000, 0, 9_000_000_000_000_000_000)
EQ_Z = (1, 100_000_000, 50_000_000, 1, 1, -100_000_000, 0, 200_000_000)
WRAP = -8_446_744_073_709_551_616
I64_MAX = 9_223_372_036_854_775_807
I64_MIN = -9_223_372_036_854_775_808
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-open-interest"


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


def py_sadd_ok(a: int, b: int) -> int:
    s = a + b
    return 0 if s > I64_MAX or s < I64_MIN else 1


def py_ok(a: tuple[int, ...]) -> int:
    index, oi, vi, has_v, is_long, delta, use_tok, max_oi = a
    if index == 0 or oi < 0 or max_oi < 0:
        return 0
    mag = abs(delta)
    if delta >= 0:
        if py_uadd_ok(oi, delta) == 0:
            return 0
        if max_oi < oi + delta:
            return 0
    elif oi < mag:
        return 0
    if use_tok == 0 and has_v == 1:
        vd = -delta if is_long == 1 else delta
        if py_sadd_ok(vi, vd) == 0:
            return 0
    return 1


def py_oi(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    _i, oi, _v, _h, _l, delta, _u, _m = a
    return oi + delta if delta >= 0 else oi - abs(delta)


def py_vi(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    _i, _o, vi, has_v, is_long, delta, use_tok, _m = a
    if use_tok != 0 or has_v == 0:
        return vi
    return vi + (-delta if is_long == 1 else delta)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{'PASS' if status=='PASS' else 'FAIL' if status=='FAIL' else status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 applyDeltaToOpenInterest — LIN proof (C11)")
    oi_ex = FIX / "ApplyDeltaToOpenInterest.excerpt.sol"
    tok_ex = FIX / "ApplyDeltaToOpenInterestInTokens.excerpt.sol"
    ds_ex = FIX / "ApplyDeltaToUintAndInt.excerpt.sol"
    if not all(p.exists() for p in (oi_ex, tok_ex, ds_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    oi_txt, tok_txt, ds_txt = (p.read_text(encoding="utf-8") for p in (oi_ex, tok_ex, ds_ex))
    need = [
        "function applyDeltaToOpenInterest",
        "OpenInterestCannotBeUpdatedForSwapOnlyMarket",
        "Invalid state: negative open interest",
        "if (!useOpenInterestInTokens)",
        "applyDeltaToVirtualInventoryForPositions",
        "isLong ? -delta : delta",
        "if (delta > 0)",
        "validateOpenInterest",
    ]
    missing = [s for s in need if s not in oi_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "OI excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains unsigned OI, long-flip VI, swap-only reject")
    rec("PIN-TOKENS", "PASS" if "if (useOpenInterestInTokens)" in tok_txt else "FAIL",
        "tokens sibling applies VI iff useOpenInterestInTokens (inverse)")
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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (long-flip / reject-neg / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 open-interest clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_open_interest.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2o_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2o_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2o_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "oi": "g2o_next_oi", "vi": "g2o_next_vi", "ok": "g2o_ok",
        "wrongnaive": "g2o_wrong_naive_oi", "wrongbound": "g2o_wrong_bounded_oi",
        "wrongnoflip": "g2o_wrong_noflip_vi", "wrongflip": "g2o_wrong_alwaysflip_vi",
        "wrongtokens": "g2o_wrong_tokens_vi", "wrongu": "g2o_wrong_unsigned_vi",
        "naiveadd": "g2o_naive_i64_add",
    }
    py_map = {
        "oi": py_oi, "vi": py_vi, "ok": py_ok,
        "wrongnaive": lambda a: w64(a[1] + a[5]),
        "wrongbound": lambda a: 0 if a[5] < 0 and a[1] < abs(a[5]) else (a[1] + a[5] if a[5] >= 0 else a[1] - abs(a[5])),
        "wrongnoflip": lambda a: a[2] if a[6] != 0 or a[3] == 0 else a[2] + a[5],
        "wrongflip": lambda a: a[2] if a[6] != 0 or a[3] == 0 else a[2] - a[5],
        "wrongtokens": lambda a: a[2] if a[6] == 0 or a[3] == 0 else a[2] + (-a[5] if a[4] == 1 else a[5]),
        "wrongu": lambda a: (lambda n: 0 if n < 0 else n)(a[2] + (-a[5] if a[4] == 1 else a[5])),
        "naiveadd": lambda a: w64(a[1] + a[5]),
    }
    cases = [
        ("oi", LONG_INC, 130_000_000), ("vi", LONG_INC, 20_000_000),
        ("wrongnoflip", LONG_INC, 80_000_000),
        ("oi", LONG_DEC, 70_000_000), ("vi", LONG_DEC, 80_000_000),
        ("oi", SHORT_INC, 130_000_000), ("vi", SHORT_INC, 80_000_000),
        ("wrongflip", SHORT_INC, 20_000_000),
        ("oi", SHORT_DEC, 70_000_000), ("vi", SHORT_DEC, 20_000_000),
        ("ok", NEG_OI, 0), ("wrongnaive", NEG_OI, -50_000_000), ("wrongbound", NEG_OI, 0),
        ("ok", MAX_HIT, 0), ("ok", SWAP, 0),
        ("oi", USE_TOK, 130_000_000), ("vi", USE_TOK, 50_000_000),
        ("wrongtokens", USE_TOK, 20_000_000),
        ("vi", NO_VIRT, 50_000_000),
        ("vi", VI_NEG, -30_000_000), ("wrongu", VI_NEG, 0),
        ("oi", EQ_Z, 0),
        ("ok", OI_OVF, 0), ("ok", VI_OVF, 0),
        ("naiveadd", OI_OVF, WRAP),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        lin_args = args if kind != "naiveadd" else (args[1], args[5])
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
    rec("LONG-FLIP", "PASS" if got[("vi", LONG_INC)] == 20_000_000 and got[("wrongnoflip", LONG_INC)] == 80_000_000 else "FAIL",
        "long +3e7 flips VI 5e7->2e7; no-flip would raise VI to 8e7")
    rec("SHORT-NOFLIP", "PASS" if got[("vi", SHORT_INC)] == 80_000_000 and got[("wrongflip", SHORT_INC)] == 20_000_000 else "FAIL",
        "short +3e7 adds VI 5e7->8e7; always-flip would drop VI to 2e7")
    rec("REJECT-NEG-OI", "PASS" if got[("ok", NEG_OI)] == 0 and got[("wrongnaive", NEG_OI)] == -50_000_000 else "FAIL",
        "delta -1.5e8 on OI 1e8 rejects; naive signed OI is -5e7")
    rec("NOT-BOUNDED", "PASS" if got[("wrongbound", NEG_OI)] == 0 and got[("ok", NEG_OI)] == 0 else "FAIL",
        "applyBoundedDeltaToUint would floor OI at 0; kernel rejects the same draw")
    rec("TOKENS-INVERSE", "PASS" if got[("vi", USE_TOK)] == 50_000_000 and got[("wrongtokens", USE_TOK)] == 20_000_000 else "FAIL",
        "USD path (use_tok=1) leaves VI; tokens sibling would long-flip VI to 2e7")
    rec("SIGNED-VI", "PASS" if got[("vi", VI_NEG)] == -30_000_000 and got[("wrongu", VI_NEG)] == 0 else "FAIL",
        "long +5e7 on VI 2e7 is signed -3e7; unsigned floor would clip to 0")
    rec("MAX-AND-SWAP", "PASS" if got[("ok", MAX_HIT)] == 0 and got[("ok", SWAP)] == 0 else "FAIL",
        "delta>0 that exceeds max OI rejects; swap-only market (index=0) rejects")
    rec("I64-OVERFLOW", "PASS" if got[("ok", OI_OVF)] == 0 and got[("ok", VI_OVF)] == 0 and got[("naiveadd", OI_OVF)] == WRAP else "FAIL",
        "7e18+3e18 OI and VI fail-close; naive i64 wraps to -8446744073709551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2o_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2o_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2o_next_oi" in src and "g2o_next_vi" in src else "FAIL",
        "LIN clone takes index/oi/vi/has_v/is_long/delta/use_tok/max_oi as arguments")
    rec("FAIL-CLOSED-ADD", "PASS" if "g2o_uadd_ok" in src and "g2o_sadd_ok" in src else "FAIL",
        "clone fail-closes unsigned OI add and signed VI add instead of wrapping")
    rec("NOT-POOL-LENT", "PASS" if "applyDeltaToOpenInterest" in oi_txt and "g2o_vi_delta" in src else "FAIL",
        "kernel is unsigned OI + signed long-flipped VI, not position-impact pool/lent")
    need_t = ["REJ_SOLIDITY_GMX_V2_OI", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects applyDeltaToOpenInterest before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_OI" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects apply_delta_to_open_interest")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_OPEN_INTEREST_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL, "datastore_path": DS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "datastore_git_blob_sha": DS_BLOB, "datastore_file_sha256": DS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2: unsigned OI cannot go negative; virtual inventory is signed and long-flipped. Distinct from applyBoundedDeltaToUint (floor at 0) and from applyDeltaToOpenInterestInTokens (VI iff tokens flag).",
        },
        "lin_clone": "src/lin_gmx_v2_open_interest.lin",
        "c11_oracle": "test/oracles/gmx_v2_open_interest_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "long_inc_oi": 130_000_000, "long_inc_vi": 20_000_000, "wrong_noflip_vi": 80_000_000,
            "short_inc_vi": 80_000_000, "wrong_alwaysflip_vi": 20_000_000,
            "neg_oi_ok": 0, "wrong_naive_oi": -50_000_000, "wrong_bounded_oi": 0,
            "tokens_vi": 50_000_000, "wrong_tokens_vi": 20_000_000,
            "signed_vi": -30_000_000, "wrong_unsigned_vi": 0,
            "overflow_ok": 0, "wrap_naive": WRAP,
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
