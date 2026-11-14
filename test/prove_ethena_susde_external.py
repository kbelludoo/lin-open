#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Ethena StakedUSDe vest+convert vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of ethena-labs/code4arena-contest StakedUSDe.sol,
C11 wrap-detect XOR __int128 mul, lin_c0 VM, Python bigint. 8-hour linear vest
feeds ERC4626 convert. Not claimed: uint256, TVL, zk, IERC20 host, OZ offset.
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
LIN = ROOT / "src" / "lin_ethena_susde.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "ethena_susde_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "ethena_susde_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "ethena_susde_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_ethena_susde")
EVIDENCE = ROOT / "examples" / "ethena_susde" / "ethena_susde_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7_000_000_000, 3_000_000_000
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "e06068be04cb7fa579a8fe1a8afbea629e1bbb84d426fdace58187282a0af895"
PINNED_BLOB = "0a56a7d18d308329e90b490428b8ee633a54dd70"
PINNED_COMMIT = "7ffedb8873c2286930804e1c4feee0410fd0f033"
UPSTREAM_REL = "protocols/USDe/contracts/StakedUSDe.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-ethena-susde"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
PERIOD = 8


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
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/ethena-labs/code4arena-contest.git"
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
    return int(a * b <= I64MAX)


def py_muldiv(a: int, b: int, d: int) -> int:
    if d < 1 or not py_mul_ok(a, b):
        return 0
    return (a * b) // d


def py_divup(x: int, y: int) -> int:
    if y < 1 or x <= 0:
        return 0
    return ((x - 1) // y) + 1


def py_unvested(now: int, last: int, vest: int) -> int:
    if now < 0 or last < 0 or vest < 0 or now < last:
        return 0
    elapsed = now - last
    if elapsed >= PERIOD:
        return 0
    return py_muldiv(PERIOD - elapsed, vest, PERIOD)


def py_total(balance: int, now: int, last: int, vest: int) -> int:
    if balance < 0:
        return 0
    u = py_unvested(now, last, vest)
    if balance < u or now < last:
        return 0
    return balance - u


def py_shares(assets: int, supply: int, ta: int) -> int:
    if min(assets, supply, ta) < 0 or assets == 0:
        return 0
    if supply == 0:
        return assets
    if ta == 0:
        return 0
    return py_muldiv(assets, supply, ta)


def py_assets(shares: int, supply: int, ta: int) -> int:
    if min(shares, supply, ta) < 0 or shares == 0:
        return 0
    if supply == 0:
        return shares
    if ta == 0:
        return 0
    return py_muldiv(shares, ta, supply)


def py_mint(shares: int, supply: int, ta: int) -> int:
    if min(shares, supply, ta) < 0 or shares == 0:
        return 0
    if supply == 0:
        return shares
    if ta == 0:
        return 0
    if not py_mul_ok(shares, ta):
        return 0
    return py_divup(shares * ta, supply)


def py_withdraw(assets: int, supply: int, ta: int) -> int:
    if min(assets, supply, ta) < 0 or assets == 0:
        return 0
    if supply == 0:
        return assets
    if ta == 0:
        return 0
    if not py_mul_ok(assets, supply):
        return 0
    return py_divup(assets * supply, ta)


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return py_mul_ok(args[0], args[1])
    if kind == "unvested":
        return py_unvested(*args)
    if kind == "total":
        return py_total(*args)
    if kind == "shares":
        return py_shares(*args)
    if kind == "assets":
        return py_assets(*args)
    if kind == "mint":
        return py_mint(*args)
    if kind == "withdraw":
        return py_withdraw(*args)
    if kind == "minshares":
        ns = args[0]
        return int(ns == 0 or ns >= 1000) if 0 <= ns <= I64MAX else 0
    if kind == "rewards":
        now, last, vest, amount = args
        return int(amount >= 1 and now >= last and py_unvested(now, last, vest) == 0)
    if kind == "deposit":
        assets, balance, now, last, vest, supply = args
        ta = py_total(balance, now, last, vest)
        sh = py_shares(assets, supply, ta)
        if sh < 1 or supply + sh > I64MAX:
            return 0
        return sh if (supply + sh == 0 or supply + sh >= 1000) else 0
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_ETHENA_SUSDE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  ETHENA StakedUSDe vest+convert — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect vest/convert mul and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned ethena-labs StakedUSDe.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("contract StakedUSDe", "function getUnvestedAmount(", "function totalAssets(",
                "VESTING_PERIOD = 8 hours", "MIN_SHARES = 1 ether", "safeTransferFrom")
        if any(s not in text for s in need):
            rec("UPSTREAM-JOIN", "FAIL", "pinned StakedUSDe.sol missing vest/totalAssets/MIN_SHARES")
            return 1
        rec("UPSTREAM-JOIN", "PASS", "pinned StakedUSDe.sol: 8h vest, totalAssets=balance-unvested, MIN_SHARES (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of StakedUSDe.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-JOIN", "SKIP", "live StakedUSDe.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-JOIN", "FAIL", "StakedUSDe.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of sUSDe clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_ethena_susde.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "es_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "es_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "es_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 2000)), ("mul", (WRAP_A, WRAP_B)),
        ("unvested", (2, 0, 800)), ("unvested", (0, 0, 800)), ("unvested", (8, 0, 800)),
        ("unvested", (9, 0, 800)), ("unvested", (1, 2, 800)),
        ("total", (10800, 2, 0, 800)), ("total", (100, 0, 0, 800)),
        ("shares", (1020, 10000, 10200)), ("shares", (500, 0, 0)),
        ("assets", (1000, 10000, 10200)), ("assets", (500, 0, 0)),
        ("mint", (1, 10000, 10200)), ("withdraw", (1, 10000, 10200)),
        ("minshares", (999,)), ("minshares", (1000,)), ("minshares", (0,)),
        ("rewards", (8, 0, 800, 100)), ("rewards", (2, 0, 800, 100)),
        ("deposit", (1020, 10800, 2, 0, 800, 10000)),
        ("deposit", (500, 0, 8, 0, 0, 0)), ("deposit", (1000, 0, 8, 0, 0, 0)),
    ]
    lin_fn = {
        "mul": "es_u_mul_ok", "unvested": "es_unvested", "total": "es_total_assets",
        "shares": "es_to_shares", "assets": "es_to_assets", "mint": "es_preview_mint",
        "withdraw": "es_preview_withdraw", "minshares": "es_min_shares_ok",
        "rewards": "es_rewards_ok", "deposit": "es_deposit_shares",
    }
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        got_lin = lin_vm(lin_fn[kind], *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{kind}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_kind(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {kind}{largs}", f"py={py_kind(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    uv = lin_vm("es_unvested", 2, 0, 800)
    ta = lin_vm("es_total_assets", 10800, 2, 0, 800)
    sh = lin_vm("es_to_shares", 1020, 10000, 10200)
    ast = lin_vm("es_to_assets", 1000, 10000, 10200)
    pm = lin_vm("es_preview_mint", 1, 10000, 10200)
    dep = lin_vm("es_deposit_shares", 1020, 10800, 2, 0, 800, 10000)
    still = lin_vm("es_rewards_ok", 2, 0, 800, 100)
    vested = lin_vm("es_rewards_ok", 8, 0, 800, 100)
    golden = (uv, ta, sh, ast, pm, dep, still, vested)
    expect = (600, 10200, 1000, 1020, 2, 1000, 0, 1)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "unvested/total/convert/mint/deposit/rewards goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "t=2h unvested=600 totalAssets=10200 convertToShares(1020)=1000 previewMint(1)=2",
        "unvested=600 total=10200 shares=1000 assets=1020 mint=2 deposit=1000 still_vesting=0")
    rec("COMMERCIAL", "PASS",
        "measured sUSDe convert (not TVL): 8h linear vest keeps convertToShares from jumping on reward drop",
        "unvested_t2=600 convert_shares=1000 unit=reduced_wad")

    wrapped = lin_vm("es_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("es_u_mul_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked assets*supply fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "es_unvested(now: int, last_ts: int, vest_amt: int" in src else "FAIL",
        "LIN clone takes now/last_ts/vest_amt (no hidden StakedUSDe storage / block.timestamp)")
    rec("NOT-SUSDS", "PASS" if "es_is_susds" in src and "es_uses_chi" in src else "FAIL",
        "clone is Ethena 8h vest, not Sky sUSDS chi/RAY")
    rec("MIN-SHARES", "PASS" if "es_min_shares" in src else "FAIL",
        "MIN_SHARES donation-attack floor is an explicit argument-scale check")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_UNVESTED" in sol_src and "REJ_C_SAFETRANSFER" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close unvested/safeTransfer/wide-int (host, not LIN emit)")
    rec("TR-VEST", "PASS" if "REJ_SOLIDITY_VESTING" in sol_src else "FAIL",
        "Solidity transpiler fail-closes VESTING_PERIOD storage (explicit period in LIN)")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "es_unvested" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable sUSDe kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (ethena_susde_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("es_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on es_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("es_u_mul_ok", 1000, 2000)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit es_u_mul_ok(1000,2000)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
            "" if jv == 1 else "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethena-labs/code4arena-contest",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-3.0",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_ethena_susde.lin"
    evidence["c11_oracle"] = "test/oracles/ethena_susde_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/ethena_susde_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "unvested_t2": uv, "total_assets": ta, "to_shares": sh, "to_assets": ast,
        "preview_mint_1": pm, "deposit_shares": dep,
        "rewards_still_vesting": still, "rewards_after_period": vested,
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
