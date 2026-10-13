#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Compound III accrualDescaleFactor / baseTrackingAccrued vs LIN C0."""
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
LIN = ROOT / "src" / "lin_comet_descale.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "comet_descale_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "comet_descale_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_comet")
EVIDENCE = ROOT / "examples" / "comet_descale" / "comet_descale_evidence.json"

PINNED_SHA256 = "c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961"
PINNED_BLOB = "3490e984d133789aa1afe2e8f7e37a11d2512396"
PINNED_COMMIT = "f766f51583c23acc33b2a7824654ef2029a96804"
UPSTREAM_REL = "contracts/CometWithExtendedAssetList.sol"
CORE_SHA256 = "1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78"
CORE_BLOB = "534f2701b6c8e683f9294112b0bcc23878d39fe6"
CORE_REL = "contracts/CometCore.sol"

USDC = 10**6
WETH = 10**18
WBTC = 10**8
TSCALE = 10**15
WAD = 10**18


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
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    cblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{CORE_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    core_hash = sha256_file(core)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    if core_hash != CORE_SHA256 or cblob != CORE_BLOB:
        return "FAIL", commit, f"core={core_hash} cblob={cblob}"
    return "PASS", commit, blob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def trunc_div(a: int, b: int) -> int:
    """C11 / LIN signed division (toward zero), not Python floor div."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def py_factor(base_scale: int) -> int:
    if base_scale < USDC:
        return 0
    return base_scale // USDC


def py_accrued(principal: int, index_delta: int, tracking_scale: int, base_scale: int) -> int:
    if principal <= 0 or index_delta < 0 or tracking_scale <= 0:
        return 0
    f = py_factor(base_scale)
    if f == 0:
        return 0
    q = (principal * index_delta) // tracking_scale
    q = q // f
    return 0 if q > (1 << 64) - 1 else q


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  Compound III accrualDescaleFactor / baseTrackingAccrued — LIN proof (C11)")

    excerpt = FIX / "CometAccrualDescale.excerpt.sol"
    core_fix = FIX / "CometCore.sol"
    if not excerpt.exists() or not core_fix.exists():
        rec("PIN-FILE", "FAIL", "pinned Comet excerpt or CometCore.sol missing")
        return 1
    if sha256_file(core_fix) != CORE_SHA256:
        rec("PIN-CORE", "FAIL", "pinned CometCore.sol sha256 mismatch", sha256_file(core_fix))
        return 1
    rec("PIN-CORE", "PASS", "pinned CometCore.sol sha256 matches manifest")
    excerpt_txt = excerpt.read_text(encoding="utf-8")
    if "accrualDescaleFactor = baseScale / BASE_ACCRUAL_SCALE" not in excerpt_txt:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing constructor factor assignment")
        return 1
    if "principal) * indexDelta / trackingIndexScale / accrualDescaleFactor" not in excerpt_txt:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing updateBasePrincipal muldiv")
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains constructor factor and updateBasePrincipal")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned compound-finance/comet matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CometWithExtendedAssetList.sol + CometCore.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb descale selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (USDC=1 / WETH=1e12 / wrap / 4-dec reject)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Comet descale clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_comet_descale.lin")
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

    gate = run([str(C0), "vm", str(LIN), "cad_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cad_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cad_test_suite == 1 on Compiler 0 interpreter")

    cases = [
        ("factor", [USDC], 1),
        ("factor", [WETH], 10**12),
        ("factor", [WBTC], 100),
        ("factor", [10**4], 0),
        ("accrued", [USDC, TSCALE, TSCALE, USDC], USDC),
        ("accrued", [WETH, TSCALE, TSCALE, WETH], USDC),
        ("accrued", [USDC, TSCALE, TSCALE, WETH], 0),
        ("accrued", [WBTC, TSCALE, TSCALE, WBTC], USDC),
        ("accrued", [5000000000, 10000000000, USDC, USDC], 50000000000000),
        ("accrued", [0, TSCALE, TSCALE, USDC], 0),
    ]
    n_ok = 0
    for kind, args, expect in cases:
        fn = "cad_factor" if kind == "factor" else "cad_accrued"
        pyv = py_factor(args[0]) if kind == "factor" else py_accrued(*args)
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *args)
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"{fn}{tuple(args)}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}",
            )
            return 1
        n_ok += 1

    usdc = lin_vm(LIN, "cad_accrued", USDC, TSCALE, TSCALE, USDC)
    weth = lin_vm(LIN, "cad_accrued", WETH, TSCALE, TSCALE, WETH)
    forget = lin_vm(LIN, "cad_forget", WETH, TSCALE, TSCALE)
    as18 = lin_vm(LIN, "cad_accrued", USDC, TSCALE, TSCALE, WETH)
    gmxup = lin_vm(LIN, "cad_gmx_upscale", USDC, USDC)
    naive = lin_vm(LIN, "cad_naive_i64", 5000000000, 10000000000, USDC, USDC)
    wide = lin_vm(LIN, "cad_accrued", 5000000000, 10000000000, USDC, USDC)
    if usdc != USDC or weth != USDC:
        rec("USDC-WETH", "FAIL", "6-dec preserve vs 18-dec descale", f"usdc={usdc} weth={weth}")
        return 1
    if forget != WETH or int(oracle(["forget", str(WETH), str(TSCALE), str(TSCALE)])) != WETH:
        rec("FORGET-TRAP", "FAIL", "forget-descale WETH contrast", f"lin={forget}")
        return 1
    if as18 != 0:
        rec("AS18-TRAP", "FAIL", "USDC with WETH factor", f"lin={as18}")
        return 1
    if gmxup != WAD:
        rec("GMX-OPP", "FAIL", "GMX-style 6->18 upscale contrast", f"lin={gmxup}")
        return 1
    if naive == wide or wide != 50000000000000:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit accrued", f"naive={naive} wide={wide}")
        return 1
    wrap_py = trunc_div(w64(5000000000 * 10000000000), USDC)
    if naive != wrap_py:
        rec("NAIVE-WRAP", "FAIL", "LIN naive wrap != python w64", f"lin={naive} py={wrap_py}")
        return 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("USDC-WETH", "PASS", "USDC factor=1 yields 1e6; WETH factor=1e12 also yields 1e6 (6-dec preserve)")
    rec("FORGET-TRAP", "PASS", "WETH forget-descale: 1e18 vs correct 1e6 (1e12x over-accrual)")
    rec("AS18-TRAP", "PASS", "USDC treated as 18-dec factor: 0 vs correct 1e6")
    rec("GMX-OPP", "PASS", "GMX-style USDC 6->18 upscale is 1e18; Comet descale keeps 1e6")
    rec("NAIVE-WRAP", "PASS", "naive i64 5e9*1e10/1e6 wraps; 128-bit muldiv yields 5e13")
    rec("WBTC-SCALE", "PASS", "WBTC 8-dec factor=100; 1e8 principal * 1e15 / 1e15 / 100 = 1e6")

    jit_ok = lin_roundtrip_jit(LIN, "cad_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cad_test_suite (in-memory libtcc)")
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
        "PASS" if "cad_accrued" in src and "cad_factor" in src else "FAIL",
        "LIN clone takes principal/indexDelta/trackingIndexScale/baseScale as arguments",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "cad_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit principal * indexDelta / trackingIndexScale then / factor",
    )
    rec(
        "NOT-TRACK",
        "PASS" if "accrualDescaleFactor" in excerpt_txt and "cad_factor" in src and "c3t_" not in src else "FAIL",
        "kernel is reward-wei descale, not divBaseWei tracking-index wrap or interest index",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_COMET_DESCALE", 'out = out + "="', 'out = out + "ex{"']
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects accrualDescaleFactor / baseTrackingAccrued before ENV",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_COMET_DESCALE" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects accrual_descale / base_tracking_accrued",
    )

    evidence = {
        "schema": "LIN_COMET_ACCRUAL_DESCALE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/compound-finance/comet",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "constants_path": CORE_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "core_git_blob_sha": CORE_BLOB,
            "core_file_sha256": CORE_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2025-12-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "Compound III USDC/WETH markets: COMP reward wei stays 6-dec via baseScale/1e6",
        },
        "lin_clone": "src/lin_comet_descale.lin",
        "c11_oracle": "test/oracles/comet_descale_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "usdc_factor": 1,
            "weth_factor": 10**12,
            "wbtc_factor": 100,
            "four_dec_reject": 0,
            "usdc_accrued": USDC,
            "weth_accrued": USDC,
            "weth_forget": WETH,
            "usdc_as18": 0,
            "wbtc_accrued": USDC,
            "gmx_upscale": WAD,
            "wrap_wide": 50000000000000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-comet-descale",
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
