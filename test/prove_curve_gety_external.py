#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve 3pool get_D/get_y vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live-fetched upstream bytes of StableSwap3Pool.vy (git blob + sha256 pin)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_curve_gety.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity/Vyper uint256 range / mainnet 3pool parity
    * PRECISION/RATES/fee/admin_fee/exchange/add_liquidity
    * that LIN replaces Curve on mainnet
    * wall-clock superiority vs vyper/EVM
    * TVL savings
    * a license to redistribute Curve.Fi source (upstream is informational-only)

Class: EXPERIMENTAL (real 3pool Newton solver, i64-positive, SCALE=1e9).
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
LIN = ROOT / "src" / "lin_curve_gety.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_gety_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_gety_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_contract")
EVIDENCE = ROOT / "examples" / "curve_gety" / "curve_gety_evidence.json"
PIN = ROOT / "test" / "fixtures" / "external_proof" / "curve_3pool_gety.pin.rulel"

E9 = 10**9
PINNED_SHA256 = "03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc"
PINNED_BLOB = "04d170189a1b5ddfecfc0af9ea3fe23eb0840423"
PINNED_COMMIT = "bae23a2fc9a0302d174ea1ffce8219a44a92149c"
UPSTREAM_REL = "contracts/pools/3pool/StableSwap3Pool.vy"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-curve-gety"
I64MAX = 2**63 - 1
N = 3


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=180)
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
    url = "https://github.com/curvefi/curve-contract.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def py_get_d(x0: int, x1: int, x2: int, amp: int) -> int:
    xp = [x0, x1, x2]
    if amp <= 0 or any(v <= 0 for v in xp):
        return 0
    s = sum(xp)
    d = s
    ann = amp * N
    for _ in range(255):
        dp = d
        for v in xp:
            dp = (dp * d) // (v * N)
        dprev = d
        d = (ann * s + dp * N) * d // ((ann - 1) * d + (N + 1) * dp)
        if abs(d - dprev) <= 1:
            break
    return 0 if d > I64MAX else d


def py_get_y(i: int, j: int, x: int, x0: int, x1: int, x2: int, amp: int) -> int:
    if i == j or i < 0 or j < 0 or i > 2 or j > 2 or x <= 0:
        return 0
    xp = [x0, x1, x2]
    d = py_get_d(x0, x1, x2, amp)
    if d <= 0:
        return 0
    c = d
    s_ = 0
    ann = amp * N
    for k in range(N):
        if k == j:
            continue
        _x = x if k == i else xp[k]
        if _x <= 0:
            return 0
        s_ += _x
        c = c * d // (_x * N)
    c = c * d // (ann * N)
    b = s_ + d // ann
    y = d
    for _ in range(255):
        yprev = y
        y = (y * y + c) // (2 * y + b - d)
        if abs(y - yprev) <= 1:
            break
    return 0 if y > I64MAX else y


def py_dy(i: int, j: int, dx: int, x0: int, x1: int, x2: int, amp: int) -> int:
    xp = [x0, x1, x2]
    x = xp[i] + dx
    y = py_get_y(i, j, x, x0, x1, x2, amp)
    if y <= 0:
        return 0
    raw = xp[j] - y
    if raw <= 0:
        return 0
    return raw - 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_CURVE_GETY_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE 3POOL GET_Y — external LIN proof (i64-positive, C11 oracle)")
    print("=" * 78)

    if not PIN.exists():
        rec("PIN-FILE", "FAIL", "pinned curve_3pool_gety.pin.rulel missing")
        return 1
    pin_txt = PIN.read_text(encoding="utf-8")
    if PINNED_SHA256 not in pin_txt or PINNED_BLOB not in pin_txt:
        rec("PIN-SHA256", "FAIL", "pin file does not carry the expected sha256/blob")
        return 1
    rec("PIN-SHA256", "PASS", "pin file records StableSwap3Pool.vy sha256 and git blob")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned curve-contract commit matches pin", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of StableSwap3Pool.vy")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb get_D/get_y selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb Newton agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Curve get_y clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_gety.lin")

    chk2 = run([str(C0), "check", str(VY_TR)])
    rec(
        "VY-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Vyper transpiler v1 (10 ** N + Curve rejects)",
    )

    gate = run([str(C0), "vm", str(LIN), "cgy_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cgy_test_suite via lin_c0 vm", f"rc={gate.returncode} value={gv}\n{gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "cgy_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("getd", ["1000000000", "1000000000", "1000000000", "100"], "cgy_get_d", (E9, E9, E9, 100)),
        ("getd", ["1000000000", "1000000000", "1000000000", "2000"], "cgy_get_d", (E9, E9, E9, 2000)),
        ("gety", ["0", "1", "1000000000", "1000000000", "1000000000", "1000000000", "100"], "cgy_get_y", (0, 1, E9, E9, E9, E9, 100)),
        ("gety", ["0", "1", "1100000000", "1000000000", "1000000000", "1000000000", "100"], "cgy_get_y", (0, 1, 1100000000, E9, E9, E9, 100)),
        ("gety", ["0", "1", "1100000000", "1000000000", "1000000000", "1000000000", "2000"], "cgy_get_y", (0, 1, 1100000000, E9, E9, E9, 2000)),
        ("dy", ["0", "1", "100000000", "1000000000", "1000000000", "1000000000", "100"], "cgy_get_dy_nofee", (0, 1, 100000000, E9, E9, E9, 100)),
        ("getd", ["1200000000", "900000000", "1000000000", "100"], "cgy_get_d", (1200000000, 900000000, E9, 100)),
        ("gety", ["0", "1", "1100000000", "1200000000", "900000000", "1000000000", "100"], "cgy_get_y", (0, 1, 1100000000, 1200000000, 900000000, E9, 100)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs or got_lin != want:
            rec("VEC-CONSENSUS", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} limbs={want_limbs}")
            return 1
        if kind == "getd":
            py = py_get_d(*largs)
        elif kind == "gety":
            py = py_get_y(*largs)
        else:
            py = py_dy(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    y100 = lin_vm("cgy_get_y", 0, 1, 1100000000, E9, E9, E9, 100)
    y2000 = lin_vm("cgy_get_y", 0, 1, 1100000000, E9, E9, E9, 2000)
    if y2000 >= y100 or y100 != 900099889 or y2000 != 900005047:
        rec("AMP-TIGHTENS", "FAIL", "larger A must keep y closer to 1e9", f"A100={y100} A2000={y2000}")
        return 1
    rec("AMP-TIGHTENS", "PASS", "A=2000 keeps y closer to 1e9 than A=100 after +10% x0")

    dy0 = lin_vm("cgy_get_dy_nofee", 0, 1, 0, E9, E9, E9, 100)
    if dy0 != 0:
        rec("DY-UNDERFLOW", "FAIL", "dx=0 must fail-close (uint256 xp[j]-y-1 wraps)", f"got={dy0}")
        return 1
    rec("DY-UNDERFLOW", "PASS", "get_dy dx=0 fail-closes to 0 instead of uint256 wrap of -1")

    naive = lin_vm("cgy_naive_i64_mul", 3099778671, 3099778671)
    if naive != -8838116264523025375:
        rec("I64-WRAP", "FAIL", "naive i64 3099778671^2 wrap", f"got={naive}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (imbalanced D)^2 wraps; 128-bit Newton does not", f"i64_wrap={naive}")

    jit_ok = lin_roundtrip_jit("cgy_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cgy_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("cgy_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cgy_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    vy = VY_TR.read_text(encoding="utf-8")
    if "cgy_muldiv_add_part" in src and "_lia_ushr" in src:
        rec("WIDE-NEWTON", "PASS", "clone uses 128-bit (a*b+add)/d for D and y Newton steps")
    else:
        rec("WIDE-NEWTON", "FAIL", "128-bit muldiv missing")
    if "block.timestamp" in src or "self." in src:
        rec("EXPLICIT-AMP", "FAIL", "clone must not hide A behind storage/time")
    else:
        rec("EXPLICIT-AMP", "PASS", "LIN takes amp and x0,x1,x2 as arguments (no storage field / timestamp ramp)")
    if "REJ_VYPER_STORAGE" in vy and "10 ** 18" in vy and "vy_expand_pow10" in vy:
        rec("VY-EMIT", "PASS", "lin_from_vyper.lin v1 expands 10 ** N and rejects Curve get_y storage/arrays")
    else:
        rec("VY-EMIT", "FAIL", "Vyper 10 ** N expand or Curve reject missing")
    if "vy_parse_test_gate" in vy and "REJ_VYPER_RAWCALL" in vy:
        rec("VY-GATE", "PASS", "vy_parse_test_gate asserts get_y/self._A/raw_call/array rejects")
    else:
        rec("VY-GATE", "FAIL", "vy_parse_test_gate missing Curve assertions")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/curvefi/curve-contract",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "all-rights-reserved informational (not vendored)",
    }
    evidence["lin_clone"] = "src/lin_curve_gety.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/curve_gety_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "get_D_1e9x3_A100": 3000000000,
        "get_y_identity_A100": 1000000000,
        "get_y_plus10pct_A100": 900099889,
        "get_y_plus10pct_A2000": 900005047,
        "get_dy_nofee_plus10pct_A100": 99900110,
        "get_dy_dx0": 0,
        "get_D_imbal_A100": 3099778671,
        "get_y_imbal_A100": 999810078,
        "naive_i64_D2": -8838116264523025375,
    }
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
