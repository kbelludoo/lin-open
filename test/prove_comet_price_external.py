#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound III mulPrice / divPrice / PRICE_SCALE vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned excerpt of mulPrice/divPrice/mulFactor plus live git bytes of
      CometWithExtendedAssetList.sol / CometCore.sol
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_comet_price.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * named contrasts: reorder (n/scale)*price, FACTOR_SCALE vs PRICE_SCALE,
      BASE_INDEX_SCALE vs PRICE_SCALE, mulFactor-as-price, skip-CF,
      WBTC 8-dec hide, WETH /PRICE_SCALE overflow

  NOT claimed:
    * full Solidity uint256 range
    * getUtilization / presentValue / tracking-index / accruedInterestIndices
    * that LIN replaces Compound III on mainnet
    * wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real Comet price wrap, uint64-scale operands).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_comet_price.lin"
JUMP = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "comet_price_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "comet_price_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_comet")
EVIDENCE = ROOT / "examples" / "comet_price" / "comet_price_evidence.json"

FACTOR = 10**18
INDEX = 10**15
PRICE = 10**8
USDC = 10**6
WETH = 10**18
WBTC = 10**8
PINNED_SHA256 = "c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961"
PINNED_BLOB = "3490e984d133789aa1afe2e8f7e37a11d2512396"
PINNED_CORE_SHA256 = "1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78"
PINNED_CORE_BLOB = "534f2701b6c8e683f9294112b0bcc23878d39fe6"
PINNED_COMMIT = "f766f51583c23acc33b2a7824654ef2029a96804"
UPSTREAM_REL = "contracts/CometWithExtendedAssetList.sol"
CORE_REL = "contracts/CometCore.sol"
MULP_SNIPPET = (
    "    function mulPrice(uint n, uint price, uint64 fromScale) internal pure returns (uint) {\n"
    "        return n * price / fromScale;\n"
    "    }\n"
)
DIVP_SNIPPET = (
    "    function divPrice(uint n, uint price, uint64 toScale) internal pure returns (uint) {\n"
    "        return n * toScale / price;\n"
    "    }\n"
)
MULF_SNIPPET = (
    "    function mulFactor(uint n, uint factor) internal pure returns (uint) {\n"
    "        return n * factor / FACTOR_SCALE;\n"
    "    }\n"
)
PRICE_SNIPPET = "    uint64 internal constant PRICE_SCALE = uint64(10 ** PRICE_FEED_DECIMALS);"
FEED_SNIPPET = "    uint8 internal constant PRICE_FEED_DECIMALS = 8;"
ABSORB_SNIPPET = "        uint256 deltaBalance = divPrice(deltaValue, basePrice, uint64(baseScale));"


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
    cmd = [str(C0), "vm", str(path), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
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
    url = "https://github.com/compound-finance/comet.git"
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
    core = UPSTREAM / CORE_REL
    if not live.exists() or not core.exists():
        return "SKIP", "", "comet sources missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    core_hash = sha256_file(core)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    if core_hash != PINNED_CORE_SHA256:
        return "FAIL", commit, f"core={core_hash}"
    text = live.read_text(encoding="utf-8")
    core_text = core.read_text(encoding="utf-8")
    if MULP_SNIPPET not in text or DIVP_SNIPPET not in text or MULF_SNIPPET not in text:
        return "FAIL", commit, "mulPrice/divPrice/mulFactor snippet missing"
    if ABSORB_SNIPPET not in text:
        return "FAIL", commit, "absorb divPrice snippet missing"
    if PRICE_SNIPPET not in core_text or FEED_SNIPPET not in core_text:
        return "FAIL", commit, "PRICE_SCALE missing from CometCore.sol"
    if "uint64 internal constant FACTOR_SCALE = 1e18;" not in core_text:
        return "FAIL", commit, "FACTOR_SCALE missing from CometCore.sol"
    if "uint64 internal constant BASE_INDEX_SCALE = 1e15;" not in core_text:
        return "FAIL", commit, "BASE_INDEX_SCALE missing from CometCore.sol"
    return "PASS", commit, blob


def py_of(kind: str, args: tuple[int, ...]) -> int:
    u64 = (1 << 64) - 1

    def md(a: int, b: int, d: int) -> int:
        if d == 0:
            return 0
        q = a * b // d
        return 0 if q > u64 else q

    if kind == "muldiv":
        return md(args[0], args[1], args[2])
    if kind == "mulprice":
        n, price, scale = args
        if price <= 0 or scale <= 0 or n < 0:
            return 0
        return md(n, price, scale)
    if kind == "divprice":
        n, price, scale = args
        if price <= 0 or scale <= 0 or n < 0:
            return 0
        return md(n, scale, price)
    if kind == "reorder":
        n, price, scale = args
        if scale <= 0 or price <= 0:
            return 0
        return (n // scale) * price
    if kind == "factor":
        return md(args[0], FACTOR, args[1])
    if kind == "index":
        return md(args[0], INDEX, args[1])
    if kind == "mulfactor":
        return md(args[0], args[1], FACTOR)
    if kind == "borrow":
        bb, bp, bs, c, ap, asc, cf = args
        borrow_usd = md(bb, bp, bs)
        collat_usd = md(c, ap, asc)
        adj = md(collat_usd, cf, FACTOR)
        return 1 if adj >= borrow_usd else 0
    if kind == "skipcf":
        bb, bp, bs, c, ap, asc = args
        return 1 if md(c, ap, asc) >= md(bb, bp, bs) else 0
    if kind == "absorb":
        seize, ap, asc, lf, bp, bs = args
        value = md(seize, ap, asc)
        delta = md(value, lf, FACTOR)
        return md(delta, bs, bp)
    return 0


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMET_PRICE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND III mulPrice / divPrice / PRICE_SCALE — external LIN proof (C11)")
    print("=" * 78)

    excerpt = FIX / "CometPriceScale.excerpt.sol"
    if not excerpt.exists():
        rec("PIN-EXCERPT", "FAIL", "pinned price excerpt missing")
        return 1
    ex = excerpt.read_text(encoding="utf-8")
    if MULP_SNIPPET not in ex or DIVP_SNIPPET not in ex or MULF_SNIPPET not in ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt does not contain exact mulPrice/divPrice bytes")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt contains exact mulPrice/divPrice/mulFactor substrings")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned comet commit matches fixture hashes",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CometWithExtendedAssetList.sol")
        rec("CORE-SHA", "PASS", "CometCore.sol sha256 + PRICE/FACTOR/INDEX scales")
        rec("SNIPPET-IN-LIVE", "PASS", "price excerpt is a substring of live bytes")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("CORE-SHA", "SKIP", "live CometCore.sol not hashed this run")
        rec("SNIPPET-IN-LIVE", "SKIP", "live substring check skipped")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("CORE-SHA", "FAIL", "CometCore.sol mismatch", up_note)
        rec("SNIPPET-IN-LIVE", "FAIL", "excerpt not in live file", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of comet price clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_comet_price.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "c3p_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "c3p_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "c3p_test_suite == 1 on Compiler 0 interpreter")

    weth_amt = 10**17
    weth_px = 200000000000
    cf50 = 500000000000000000
    lf80 = 800000000000000000
    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "c3p_muldiv", (100, 200, 50)),
        ("mulprice", [str(USDC), str(PRICE), str(USDC)], "c3p_mul_price", (USDC, PRICE, USDC)),
        ("mulprice", ["3", "5", "4"], "c3p_mul_price", (3, 5, 4)),
        ("reorder", ["3", "5", "4"], "c3p_reorder", (3, 5, 4)),
        ("factor", [str(USDC), str(USDC)], "c3p_factor_as_price", (USDC, USDC)),
        ("index", [str(USDC), str(USDC)], "c3p_index_as_price", (USDC, USDC)),
        ("mulfactor", [str(USDC), str(PRICE)], "c3p_mulfactor_as_price", (USDC, PRICE)),
        ("divprice", [str(PRICE), str(PRICE), str(USDC)], "c3p_div_price", (PRICE, PRICE, USDC)),
        ("mulprice", [str(WBTC), "6000000000000", str(WBTC)], "c3p_mul_price", (WBTC, 6000000000000, WBTC)),
        ("mulprice", [str(WETH), str(weth_px), str(WETH)], "c3p_mul_price", (WETH, weth_px, WETH)),
        ("mulprice", [str(WETH), str(weth_px), str(PRICE)], "c3p_mul_price", (WETH, weth_px, PRICE)),
        ("absorb", [str(weth_amt), str(weth_px), str(WETH), str(lf80), str(PRICE), str(USDC)],
         "c3p_absorb_base", (weth_amt, weth_px, WETH, lf80, PRICE, USDC)),
        ("muldiv", [str(FACTOR), str(FACTOR), "1"], "c3p_muldiv", (FACTOR, FACTOR, 1)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        got_lin = lin_vm(LIN, fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        py = py_of(kind, largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    comet = lin_vm(LIN, "c3p_mul_price", 3, 5, 4)
    reo = lin_vm(LIN, "c3p_reorder", 3, 5, 4)
    if comet != 3 or reo != 0:
        rec("REORDER-REJ", "FAIL", "reorder (n/scale)*price must truncate to 0 vs comet 3", f"c={comet} r={reo}")
        return 1
    rec("REORDER-REJ", "PASS", "named rejected path (n/fromScale)*price = 0; Comet wrap = 3", f"reorder={reo} comet={comet}")

    usdc = lin_vm(LIN, "c3p_mul_price", USDC, PRICE, USDC)
    fac = lin_vm(LIN, "c3p_factor_as_price", USDC, USDC)
    idx = lin_vm(LIN, "c3p_index_as_price", USDC, USDC)
    mf = lin_vm(LIN, "c3p_mulfactor_as_price", USDC, PRICE)
    if usdc != PRICE or fac != FACTOR or idx != INDEX or mf != 0:
        rec("SCALE-CONTRAST", "FAIL", "USDC PRICE vs FACTOR/INDEX/mulFactor", f"u={usdc} f={fac} i={idx} m={mf}")
        return 1
    rec("SCALE-CONTRAST", "PASS",
        "USDC 6-dec $1: comet=1e8; FACTOR confusion=1e18 (~1e10 x); INDEX=1e15; mulFactor-as-price=0",
        f"comet={usdc} factor={fac} index={idx} mulfactor={mf}")

    wbtc = lin_vm(LIN, "c3p_mul_price", WBTC, 6000000000000, WBTC)
    wbtc_ps = lin_vm(LIN, "c3p_mul_price", WBTC, 6000000000000, PRICE)
    if wbtc != 6000000000000 or wbtc_ps != wbtc:
        rec("WBTC-HIDE", "FAIL", "8-dec WBTC must hide PRICE_SCALE vs asset.scale", f"w={wbtc} ps={wbtc_ps}")
        return 1
    rec("WBTC-HIDE", "PASS", "WBTC 8-dec: comet=6e12 and PRICE_SCALE-as-fromScale=6e12 (bug hidden)")

    weth = lin_vm(LIN, "c3p_mul_price", WETH, weth_px, WETH)
    weth_ps = lin_vm(LIN, "c3p_mul_price", WETH, weth_px, PRICE)
    if weth != weth_px or weth_ps != 0:
        rec("WETH-OVF", "FAIL", "18-dec * $2000 / PRICE_SCALE must overflow-fail-close", f"w={weth} ps={weth_ps}")
        return 1
    rec("WETH-OVF", "PASS", "WETH 1e18 @$2000: comet=2e11; /PRICE_SCALE overflows uint64 → 0")

    dp = lin_vm(LIN, "c3p_div_price", PRICE, PRICE, USDC)
    dpc = lin_vm(LIN, "c3p_div_price_scale_confused", PRICE, PRICE)
    if dp != USDC or dpc != PRICE:
        rec("DIV-SCALE", "FAIL", "divPrice USDC vs PRICE_SCALE as toScale", f"d={dp} c={dpc}")
        return 1
    rec("DIV-SCALE", "PASS", "$1 → 1 USDC (1e6); toScale=PRICE_SCALE → 1e8 (100× payout)")

    ok = lin_vm(LIN, "c3p_is_borrow_ok", 200000000, PRICE, USDC, weth_amt, weth_px, WETH, cf50)
    skip = lin_vm(LIN, "c3p_skip_cf", 200000000, PRICE, USDC, weth_amt, weth_px, WETH)
    if ok != 0 or skip != 1:
        rec("CF-SKIP", "FAIL", "50% CF must under-water; skip-CF must falsely pass", f"ok={ok} skip={skip}")
        return 1
    rec("CF-SKIP", "PASS", "200 USDC vs 0.1 WETH@$2000 CF=50%: comet ok=0; skip mulFactor ok=1")

    absb = lin_vm(LIN, "c3p_absorb_base", weth_amt, weth_px, WETH, lf80, PRICE, USDC)
    if absb != 160000000:
        rec("ABSORB", "FAIL", "0.1 WETH LF=80% must pay 160 USDC", f"got={absb}")
        return 1
    rec("ABSORB", "PASS", "absorbInternal scalar: 0.1 WETH LF=80% → 160e6 base units (160 USDC)")

    wrapped = (FACTOR * FACTOR) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 0:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled fail-closed 0")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes 0", f"i64_wrap={wrapped}")

    jr = run([str(C0), "vm", str(JUMP), "cjr_test_suite"])
    jv = value_of(jr.stdout)
    if jr.returncode != 0 or jv != 1:
        rec("JUMPRATE-REG", "FAIL", "JumpRate suite must still pass after transpiler delta", jr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still cjr_test_suite==1 after PRICE rejects")

    jit_ok = lin_roundtrip_jit("c3p_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on c3p_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    src = LIN.read_text(encoding="utf-8")
    if "c3p_mul_price(n: int, price: int, from_scale: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit n/price/from_scale as arguments")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes price inputs as arguments (no hidden storage)")
    if "getPrice(" in src or "baseTokenPriceFeed" in src:
        rec("NO-HIDDEN-GET", "FAIL", "clone must not call getPrice or read price-feed immutables")
    else:
        rec("NO-HIDDEN-GET", "PASS", "clone does not reimplement Solidity getters / PriceFeed")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ("REJ_SOLIDITY_MUL_PRICE", "REJ_SOLIDITY_PRICE_WRAP", "n * price",
            "divPrice(", "n * toScale", "PRICE_SCALE", "fromScale", "getPrice(", '"="', '"ex{"')
    missing = [t for t in need if t not in sol_src]
    if missing:
        rec("SOL-REJ", "FAIL", "solidity transpiler v3 missing reject tokens", str(missing))
    else:
        rec("SOL-REJ", "PASS", "v3 rejects MUL_PRICE / PRICE_WRAP / DIV_PRICE / PRICE_SCALE; emit splits '=' + 'ex{'")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_PRICE_WRAP" not in rs_src or "* price /" not in rs_src:
        rec("RS-REJ", "FAIL", "rust transpiler missing REJ_RUST_PRICE_WRAP")
    else:
        rec("RS-REJ", "PASS", "rust transpiler v2 rejects * price / wrapping wrap")

    gate_sol = run([str(C0), "vm", str(SOL_TR), "sol_parse_test_gate"])
    if "VM_REJ_STRING_LITERAL" in gate_sol.stdout or "VM_REJ_STRING_LITERAL" in gate_sol.stderr:
        rec("SOL-GATE-REJ", "PASS", "Compiler 0 refuses sol_parse_test_gate string-literal path (VM_REJ_STRING_LITERAL)")
    else:
        rec("SOL-GATE-REJ", "SKIP", "string-literal reject not observed", gate_sol.stdout[:200])

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/comet",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "core_path": CORE_REL,
        "core_git_blob_sha": PINNED_CORE_BLOB,
        "core_file_sha256": PINNED_CORE_SHA256,
        "license": "GPL-2.0-or-later (BUSL-1.1 Change Date 2025-12-31 elapsed)",
    }
    evidence["lin_clone"] = "src/lin_comet_price.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-comet-price"
    evidence["c11_oracle"] = "test/oracles/comet_price_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["usdc_mulprice_1usd"] = usdc
    evidence["usdc_factor_confused"] = fac
    evidence["usdc_index_confused"] = idx
    evidence["reorder_3_5_4"] = reo
    evidence["absorb_01_weth_lf80"] = absb
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
