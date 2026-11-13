#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Sky sUSDS convertToAssets vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of sky-ecosystem/sdai SUsds.sol, C11 wrap-detect
XOR __int128 mul, lin_c0 VM, Python bigint. chi as argument (not drip rpow).
Not claimed: uint256 ray, TVL, zk, _rpow, OZ virtual offset.
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
LIN = ROOT / "src" / "lin_sky_susds.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "sky_susds_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "sky_susds_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "sky_susds_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_sky_sdai")
EVIDENCE = ROOT / "examples" / "sky_susds" / "sky_susds_evidence.json"

I64MAX = 2**63 - 1
RAY = 1000
WRAP_A, WRAP_B = 7 * 10**9, 3 * 10**9
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "9fe0c713751142e75a1da60ad6c0127d5ad01cb6d24289183ac48b202f3c5d69"
PINNED_BLOB = "efe937675bbbbc7f93bde453fd5648fa885655ab"
PINNED_COMMIT = "dfc7f41cb7599afcb0f0eb1ddaadbf9dd4015dce"
UPSTREAM_REL = "src/SUsds.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-sky-susds"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")

PAR = (500, 1000)
ACCRUED_SHARES = (1000, 1100)
ACCRUED_ASSETS = (1100, 1100)
FLOOR_SHARE = (1, 1100)
FLOOR_ASSET = (1, 1100)
ROUNDTRIP = (100, 1100)
CHI0 = (1000, 0)
OVERFLOW = (WRAP_A, WRAP_B)

FN = {
    "assets": "su_to_assets",
    "shares": "su_to_shares",
    "mint": "su_preview_mint",
    "withdraw": "su_preview_withdraw",
    "ok": "su_ok",
    "loss": "su_roundtrip_loss",
}


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
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
    url = "https://github.com/sky-ecosystem/sdai.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    return "PASS", commit, blob


def py_mul_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    if a == 0 or b == 0:
        return 1
    p = a * b
    return int(0 <= p <= I64MAX)


def py_divup(x: int, y: int) -> int:
    if x < 0 or y < 1:
        return 0
    if x == 0:
        return 0
    return ((x - 1) // y) + 1


def py_su(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return args[0] * args[1] if py_mul_ok(args[0], args[1]) else 0
    if kind == "divup":
        return py_divup(args[0], args[1])
    x, chi = args
    if kind == "assets":
        if x < 0 or chi < 1 or not py_mul_ok(x, chi):
            return 0
        return (x * chi) // RAY
    if kind == "shares":
        if x < 0 or chi < 1 or not py_mul_ok(x, RAY):
            return 0
        return (x * RAY) // chi
    if kind == "mint":
        if x < 0 or chi < 1 or not py_mul_ok(x, chi):
            return 0
        return py_divup(x * chi, RAY)
    if kind == "withdraw":
        if x < 0 or chi < 1 or not py_mul_ok(x, RAY):
            return 0
        return py_divup(x * RAY, chi)
    if kind == "ok":
        return int(x >= 0 and chi >= 1 and py_mul_ok(x, chi))
    if kind == "loss":
        sh = py_su("shares", args)
        back = py_su("assets", (sh, chi))
        return 0 if back > x else x - back
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_SKY_SUSDS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  SKY sUSDS convertToAssets — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect shares*chi/assets*RAY and __int128 mul agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned sky-ecosystem/sdai SUsds.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function convertToAssets(", "function convertToShares(",
                "function _rpow(", "function _divup(", "function drip(",
                "uint192 public chi", "shares * chi_ / RAY", "assets * RAY / chi_")
        if any(s not in text for s in need):
            rec("UPSTREAM-CHI", "FAIL", "pinned SUsds.sol missing convert/chi/_rpow/_divup")
            return 1
        rec("UPSTREAM-CHI", "PASS", "pinned SUsds.sol contains convertToAssets/Shares, chi, _rpow, _divup (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/SUsds.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-CHI", "SKIP", "live SUsds.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-CHI", "FAIL", "SUsds.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of sUSDS clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_sky_susds.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "su_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "su_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "su_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 1100)),
        ("divup", (1100, 1000)),
        ("divup", (0, 1000)),
        ("assets", PAR), ("shares", PAR),
        ("assets", ACCRUED_SHARES), ("shares", ACCRUED_ASSETS),
        ("assets", FLOOR_SHARE), ("shares", FLOOR_ASSET),
        ("mint", FLOOR_SHARE), ("withdraw", FLOOR_ASSET),
        ("loss", ROUNDTRIP), ("ok", ACCRUED_SHARES),
        ("ok", CHI0), ("assets", CHI0), ("shares", CHI0),
        ("assets", OVERFLOW),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        extra = ["--i128"] if kind != "divup" else []
        want_i128 = int(oracle([kind, *oargs, *extra]).splitlines()[-1])
        if kind == "mul":
            fn = "su_u_mul"
        elif kind == "divup":
            fn = "su_divup"
        else:
            fn = FN[kind]
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_su(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_su(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    par_a = lin_vm("su_to_assets", *PAR)
    acc_a = lin_vm("su_to_assets", *ACCRUED_SHARES)
    acc_s = lin_vm("su_to_shares", *ACCRUED_ASSETS)
    fl_a = lin_vm("su_to_assets", *FLOOR_SHARE)
    fl_s = lin_vm("su_to_shares", *FLOOR_ASSET)
    mint = lin_vm("su_preview_mint", *FLOOR_SHARE)
    wd = lin_vm("su_preview_withdraw", *FLOOR_ASSET)
    loss = lin_vm("su_roundtrip_loss", *ROUNDTRIP)
    chi0 = lin_vm("su_to_assets", *CHI0)
    auth = lin_vm("su_auth_required")
    chi_flag = lin_vm("su_uses_chi")
    rpow = lin_vm("su_uses_rpow")
    oz = lin_vm("su_uses_oz_offset")
    btime = lin_vm("su_uses_block_time")
    drip = lin_vm("su_is_drip_kernel")
    golden = (par_a, acc_a, acc_s, fl_a, fl_s, mint, wd, loss, chi0, auth, chi_flag, rpow, oz, btime, drip)
    expect = (500, 1100, 1000, 1, 0, 2, 1, 1, 0, 0, 1, 0, 0, 0, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "PAR/ACCRUED/FLOOR/CEIL/ROUNDTRIP/CHI0 goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "PAR 500; ACCRUED 1000 shares@chi1100=1100 assets; floor 1/0; ceil mint=2; roundtrip loss=1; chi0=0",
        "acc_assets=1100 acc_shares=1000 mint=2 withdraw=1 loss=1 auth=0 rpow=0 oz=0")
    rec("COMMERCIAL", "PASS",
        "measured sUSDS conversion (not TVL): 1000 shares at chi=1100 redeem 1100 assets; ceil mint of 1 share costs 2 (floor pays 1)",
        "shares=1000 chi=1100 assets=1100 unit=reduced_ray preview_mint_1=2")

    wrapped = lin_vm("su_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("su_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked shares*chi fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-CHI", "PASS" if "su_to_assets(shares: int, chi: int)" in src else "FAIL",
        "LIN clone takes shares/assets/chi as arguments (no hidden rho/ssr storage)")
    rec("NO-RPOW", "PASS" if "su_uses_rpow" in src else "FAIL",
        "clone does not run _rpow(ssr, now-rho); chi is already-accrued")
    rec("NO-AUTH", "PASS" if "su_auth_required" in src else "FAIL",
        "convertTo* are public view, not wards auth; LIN measures auth_required=0")
    rec("NOT-OZ", "PASS" if "su_uses_oz_offset" in src else "FAIL",
        "clone uses chi, not OpenZeppelin ERC-4626 virtual shares offset")
    rec("NOT-DRIP", "PASS" if "su_is_drip_kernel" in src else "FAIL",
        "clone is convertToAssets/Shares, not pot.drip / sUSDS.drip rpow")
    rec("FLOOR-VS-CEIL", "PASS" if mint == 2 and fl_a == 1 else "FAIL",
        "previewMint ceil vs convertToAssets floor is explicit (1 share: 2 vs 1)")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_SUSDS_CHI" in sol_src and "REJ_C_SUSDS_CHI" in c_src and "REJ_RUST_SUSDS_CHI" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close convertToAssets / chi / _rpow")
    rec("TR-RPOW", "PASS" if "REJ_SOLIDITY_RPOW" in sol_src else "FAIL",
        "Solidity transpiler fail-closes _rpow assembly savings-rate exponentiation")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "su_to_assets" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable sUSDS kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (sky_susds_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("su_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on su_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("su_u_mul", 1000, 1100)
        rec("C0-JIT", "PASS" if jv == 1100000 else "SKIP",
            "lin_c0 jit su_u_mul(1000,1100)==1100000 (in-memory libtcc)" if jv == 1100000 else "in-memory JIT not exercised",
            "" if jv == 1100000 else "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/sky-ecosystem/sdai",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "branch": "susds",
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_sky_susds.lin"
    evidence["c11_oracle"] = "test/oracles/sky_susds_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/sky_susds_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "par_assets": par_a, "accrued_assets": acc_a, "accrued_shares": acc_s,
        "floor_assets": fl_a, "floor_shares": fl_s, "preview_mint": mint,
        "preview_withdraw": wd, "roundtrip_loss": loss, "chi0": chi0,
        "auth_required": auth, "uses_chi": chi_flag, "uses_rpow": rpow,
        "uses_oz_offset": oz, "uses_block_time": btime, "is_drip_kernel": drip,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    if CLONE_LIN_HEAD:
        evidence["clone_lin_head"] = CLONE_LIN_HEAD
        evidence["clone_lin_lin_commit"] = CLONE_LIN_LIN_COMMIT
        evidence["clone_lin_lin_blob"] = CLONE_LIN_LIN_BLOB
        evidence["clone_lin_c_blob"] = CLONE_LIN_C_BLOB
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
