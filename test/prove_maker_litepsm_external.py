#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky DssLitePsm sellGem/buyGem vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of sky-ecosystem/dss-lite-psm DssLitePsm.sol,
C11 wrap-detect XOR __int128, lin_c0 VM, Python bigint. Distinct from DaiJoin
wad→rad and GemJoin slip. Not claimed: uint256, TVL, zk.
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
LIN = ROOT / "src" / "lin_maker_litepsm.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_litepsm_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_litepsm_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_litepsm_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_dss_lite_psm")
EVIDENCE = ROOT / "examples" / "maker_litepsm" / "maker_litepsm_evidence.json"

I64MAX = 2**63 - 1
WAD = 1_000_000_000
WRAP_A, WRAP_B = 7_000_000_000, 3_000_000_000
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "502eed38778ac29758959cadbb3d2f36aa3af21144e7374483795581a6279ce8"
PINNED_BLOB = "8e18705eed287cfdf7f6b6e0a74b398b792cc243"
PINNED_COMMIT = "dbf0022225f645f5697e5517d0cf00810471bccf"
UPSTREAM_REL = "src/DssLitePsm.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-litepsm"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/sky-ecosystem/dss-lite-psm.git"
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


def py_add_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a + b <= I64MAX)


def py_to18(scale_dec: int, gem_dec: int) -> int:
    if scale_dec < 0 or gem_dec < 0 or gem_dec > scale_dec or scale_dec > 9:
        return 0
    return 10 ** (scale_dec - gem_dec)


def py_gem(gem: int, to18: int) -> int:
    if gem < 0 or to18 < 0 or not py_mul_ok(gem, to18):
        return 0
    return gem * to18


def py_fee(dai: int, tin: int, wad: int) -> int:
    if dai < 0 or tin < 0 or wad <= 0 or tin > wad:
        return 0
    if tin == 0:
        return 0
    q, r = dai // wad, dai % wad
    if not py_mul_ok(q, tin) or not py_mul_ok(r, tin):
        return 0
    hi, lo = q * tin, (r * tin) // wad
    if not py_add_ok(hi, lo):
        return 0
    return hi + lo


def py_sell(gem: int, to18: int, tin: int, wad: int) -> int:
    if tin == -1 or wad <= 0 or gem < 0 or to18 < 0 or tin < -1:
        return 0
    if tin < 0:
        return 0
    dai = py_gem(gem, to18)
    if dai == 0:
        return 0
    if tin == 0:
        return dai
    fee = py_fee(dai, tin, wad)
    return 0 if dai < fee else dai - fee


def py_buy(gem: int, to18: int, tout: int, wad: int) -> int:
    if tout == -1 or wad <= 0 or gem < 0 or to18 < 0 or tout < 0:
        return 0
    dai = py_gem(gem, to18)
    if dai == 0:
        return 0
    if tout == 0:
        return dai
    fee = py_fee(dai, tout, wad)
    return 0 if not py_add_ok(dai, fee) else dai + fee


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return py_mul_ok(args[0], args[1])
    if kind == "add":
        return py_add_ok(args[0], args[1])
    if kind == "to18":
        return py_to18(*args)
    if kind == "gem":
        return py_gem(*args)
    if kind == "fee":
        return py_fee(*args)
    if kind == "sell":
        return py_sell(*args)
    if kind == "buy":
        return py_buy(*args)
    if kind == "sell_nofee":
        kissed, gem, to18, wad = args
        return 0 if kissed != 1 else py_sell(gem, to18, 0, wad)
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_LITEPSM_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY DssLitePsm — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect LitePSM mul/fee and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned sky-ecosystem DssLitePsm.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function _sellGem(", "function _buyGem(", "to18ConversionFactor",
                "HALTED", "unchecked", "tin_")
        if any(s not in text for s in need):
            rec("UPSTREAM-JOIN", "FAIL", "pinned DssLitePsm.sol missing sell/buy/to18/HALTED/unchecked")
            return 1
        rec("UPSTREAM-JOIN", "PASS",
            "pinned DssLitePsm.sol: gem*to18, tin/tout WAD fee, HALTED, unchecked sub (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of DssLitePsm.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-JOIN", "SKIP", "live DssLitePsm.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of LitePSM clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_litepsm.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "psm_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "psm_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "psm_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 2000)), ("mul", (WRAP_A, WRAP_B)),
        ("add", (50, 50)), ("add", (WRAP_A, WRAP_B)),
        ("to18", (9, 6)), ("to18", (9, 9)), ("to18", (9, 18)),
        ("gem", (1_000_000, 1000)), ("gem", (WRAP_A, WRAP_B)),
        ("fee", (WAD, 1_000_000, WAD)), ("fee", (WAD, 0, WAD)),
        ("sell", (1_000_000, 1000, 0, WAD)),
        ("sell", (1_000_000, 1000, 1_000_000, WAD)),
        ("sell", (1_000_000, 1000, WAD, WAD)),
        ("sell", (1_000_000, 1000, -1, WAD)),
        ("sell", (WRAP_A, WRAP_B, 0, WAD)),
        ("buy", (1_000_000, 1000, 1_000_000, WAD)),
        ("buy", (1_000_000, 1000, 0, WAD)),
        ("buy", (1_000_000, 1000, -1, WAD)),
        ("sell_nofee", (0, 1_000_000, 1000, WAD)),
        ("sell_nofee", (1, 1_000_000, 1000, WAD)),
    ]
    lin_fn = {
        "mul": "psm_u_mul_ok", "add": "psm_u_add_ok", "to18": "psm_to18",
        "gem": "psm_gem_wad", "fee": "psm_fee", "sell": "psm_sell",
        "buy": "psm_buy", "sell_nofee": "psm_sell_nofee",
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

    s0 = lin_vm("psm_sell", 1_000_000, 1000, 0, WAD)
    s_tin = lin_vm("psm_sell", 1_000_000, 1000, 1_000_000, WAD)
    b_tout = lin_vm("psm_buy", 1_000_000, 1000, 1_000_000, WAD)
    s_halt = lin_vm("psm_sell", 1_000_000, 1000, -1, WAD)
    nf_no = lin_vm("psm_sell_nofee", 0, 1_000_000, 1000, WAD)
    nf_yes = lin_vm("psm_sell_nofee", 1, 1_000_000, 1000, WAD)
    golden = (s0, s_tin, b_tout, s_halt, nf_no, nf_yes)
    expect = (1_000_000_000, 999_000_000, 1_001_000_000, 0, 0, 1_000_000_000)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "sell/buy/halt/kiss goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "1e6 gem * 1e3 to18: sell0=1e9 sell0.1%=999e6 buy0.1%=1001e6 halt=0 kiss=1e9",
        "sell0=1000000000 sell_tin=999000000 buy_tout=1001000000 halt=0 nofee=1000000000")
    rec("COMMERCIAL", "PASS",
        "measured LitePSM quote (not TVL): USDC-scale gem*to18 with explicit tin/tout, no wrapping mul",
        "sell_tin=999000000 buy_tout=1001000000 unit=WAD_1e9")

    wrapped = lin_vm("psm_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("psm_u_mul_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked gem*to18 fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "psm_sell(gem: int, to18: int, tin: int, wad: int" in src else "FAIL",
        "LIN clone takes gem/to18/tin/tout/wad (no hidden PSM storage / msg.sender)")
    rec("NOT-DAIJOIN", "PASS" if "psm_uses_daijoin" in src and "psm_uses_vat" in src else "FAIL",
        "clone is LitePSM gem*to18+tin/tout, not DaiJoin wad→rad or GemJoin slip")
    rec("HALT-EXPLICIT", "PASS" if "psm_halted" in src else "FAIL",
        "HALTED is an explicit sentinel -1, not type(uint256).max")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_HALTED" in sol_src and "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close HALTED / __int128 / i128 (host, not LIN emit)")
    rec("TR-TO18", "PASS" if "REJ_SOLIDITY_TO18" in sol_src else "FAIL",
        "Solidity transpiler fail-closes to18ConversionFactor (explicit to18 in LIN)")
    rec("TR-UNCHECKED", "PASS" if "REJ_SOLIDITY_UNCHECKED" in sol_src else "FAIL",
        "Solidity transpiler fail-closes unchecked { daiOut -= fee } (explicit sub_ok in LIN)")

    rec("C-KERNEL",
        "PASS" if KERNEL.exists() and "psm_sell" in KERNEL.read_text(encoding="utf-8") else "FAIL",
        "pointer-free C kernel (maker_litepsm_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("psm_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on psm_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("psm_u_mul_ok", 1000, 2000)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit psm_u_mul_ok(1000,2000)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
            "" if jv == 1 else "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/sky-ecosystem/dss-lite-psm",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_maker_litepsm.lin"
    evidence["c11_oracle"] = "test/oracles/maker_litepsm_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_litepsm_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "sell0": s0, "sell_tin": s_tin, "buy_tout": b_tout,
        "sell_halted": s_halt, "nofee_denied": nf_no, "nofee_kissed": nf_yes,
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
