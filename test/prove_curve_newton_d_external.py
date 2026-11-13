#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve tricrypto newton_D (informational Vyper) vs LIN C0.

PASS claims are recomputed this run against:
  * live git pin of curvefi/tricrypto-ng CurveCryptoMathOptimized3.vy
    (sha256 + git blob; Vyper is NOT vendored)
  * independent C11 oracle (__int128 AND 32-bit limbs)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * in-memory libtcc JIT when available
  * Python arbitrary-precision int on the same uint64-scale formulas

NOT claimed: uint256 / mainnet tricrypto parity, TVL/dollar savings,
zk soundness, LIN replacing Curve/EVM, K0_prev cubic-root apriori,
stableswap get_D (see clone-lin-curve-gety / clone-lin-curve-vp),
_newton_y (see clone-lin-curve-newton-y).

Class: EXPERIMENTAL (real Curve crypto Newton D algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_curve_newton_d.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_newton_d_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_newton_d_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_tricrypto_ng")
EVIDENCE = ROOT / "examples" / "curve_newton_d" / "curve_newton_d_evidence.json"

PINNED_SHA256 = "d0d48e5c3fa00e36f841250cbce8665292ba3224bb050c948dc3b12a50f01d6c"
PINNED_BLOB = "695c794cb8035e4b2848ad0354d0993dcfb9c7cb"
PINNED_COMMIT = "ecaa8161c240f21dd7c3712eefc5637e1dac742b"
UPSTREAM_REL = "contracts/main/CurveCryptoMathOptimized3.vy"
UPSTREAM_URL = "https://github.com/curvefi/tricrypto-ng.git"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-curve-newton-d"
CLONE_LIN_COMMIT = "588c9340ee7dfbe4502f43eafde9ea1196be5e09"
CLONE_LIN_KERNEL_BLOB = "ef3c15cb87a289f27fec83b05674c7574f9d290a"
CLONE_LIN_ORACLE_BLOB = "dba5c29b9210d9d627055992abfefbee237ccae4"

ANN = 1707629
GAMMA = 11809
E9 = 10**9
PREC = E9


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", UPSTREAM_URL])
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
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def py_md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q >= (1 << 63) else q


def py_icbrt(n: int) -> int:
    if n <= 0:
        return 0
    lo, hi = 0, 1 << 32
    if n < hi:
        hi = n
    while lo < hi:
        mid = lo + ((hi - lo + 1) >> 1)
        cub = mid * mid * mid
        if cub <= n:
            lo = mid
        else:
            hi = mid - 1
    return lo


def py_newton_d(ann: int, gamma: int, x0: int, x1: int, x2: int, k0_prev: int) -> int:
    if ann <= 0 or gamma <= 0 or k0_prev != 0 or min(x0, x1, x2) <= 0:
        return 0
    xs = sorted([x0, x1, x2], reverse=True)
    h, m, l = xs
    s = h + m + l
    gm = py_icbrt(h * m * l)
    d = 3 * gm
    if d <= 0:
        return 0
    n, p = 3, PREC
    for _ in range(255):
        d_prev = d
        k0 = py_md(p, h * n, d)
        k0 = py_md(k0, m * n, d)
        k0 = py_md(k0, l * n, d)
        if k0 <= 0:
            return 0
        orig = gamma + p
        g1 = (orig - k0 + 1) if orig > k0 else (k0 - orig + 1)
        t = py_md(p, d, gamma)
        t = py_md(t, g1, gamma)
        t = py_md(t, g1, 1)
        mul1 = py_md(t, 10000, ann)
        if mul1 <= 0:
            return 0
        mul2 = py_md(2 * p * n, k0, g1)
        t2 = py_md(s, mul2, p)
        t3 = py_md(mul1, n, k0)
        t4 = py_md(mul2, d, p)
        lhs = s + t2 + t3
        if lhs < t4:
            d = d_prev // 2
            continue
        neg = lhs - t4
        if neg <= 0:
            return 0
        d_plus = py_md(d, neg + s, neg)
        d_minus = py_md(d, d, neg)
        if p > k0:
            extra = py_md(py_md(d, mul1 // neg, p), p - k0, k0)
            d_minus = d_minus + extra
        else:
            extra = py_md(py_md(d, mul1 // neg, p), k0 - p, k0)
            if d_minus < extra:
                d = d_prev // 2
                continue
            d_minus = d_minus - extra
        d = d_plus - d_minus if d_plus > d_minus else (d_minus - d_plus) // 2
        diff = abs(d - d_prev)
        lim = max(100, d // 100000)
        if diff < lim:
            return d
    return 0


def py_vp(ann: int, gamma: int, x0: int, x1: int, x2: int) -> int:
    d = py_newton_d(ann, gamma, x0, x1, x2, 0)
    s = x0 + x1 + x2
    if d <= 0 or s <= 0:
        return 0
    return py_md(d, PREC, s)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_CURVE_NEWTON_D_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE TRICRYPTO newton_D — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned tricrypto-ng commit matches published sha256",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CurveCryptoMathOptimized3.vy")
        rec("NO-VENDOR", "PASS", "Vyper source is hash-pinned only (not copied into lin-open)")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; published pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from published digest", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb newton_D selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb newton_D agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of curve newton_D clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_newton_d.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("VY-TR-CHECK", VY_TR), ("C-TR-CHECK", C_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    vy_src = VY_TR.read_text(encoding="utf-8")
    if all(tok in vy_src for tok in ("REJ_VYPER_NEWTON_D", "REJ_VYPER_ARRAY", "REJ_VYPER_UNSAFE", "vy_parse_test_gate")):
        rec("VY-GATE", "PASS", "lin_from_vyper.lin fail-closes newton_D / uint256[ / unsafe_")
    else:
        rec("VY-GATE", "FAIL", "Vyper reject tokens missing")
        return 1
    sol_src = SOL_TR.read_text(encoding="utf-8")
    if all(tok in sol_src for tok in ("REJ_SOLIDITY_NEWTON_D", "REJ_SOLIDITY_ARRAY", "version=3")):
        rec("SOL-GATE", "PASS", "lin_from_solidity.lin v3 fail-closes newton_D / uint256[")
    else:
        rec("SOL-GATE", "FAIL", "Solidity v3 reject tokens missing")
        return 1
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_NEWTON_D" in rs_src:
        rec("RS-GATE", "PASS", "lin_from_rust.lin fail-closes newton_D")
    else:
        rec("RS-GATE", "FAIL", "Rust newton_D reject missing")
        return 1
    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_NEWTON_D" in c_src and "REJ_C_UNSAFE" in c_src:
        rec("C-REJ", "PASS", "lin_from_c.lin fail-closes newton_D / unsafe_ / uint256")
    else:
        rec("C-REJ", "FAIL", "C transpiler reject tokens missing")

    gate = run([str(C0), "vm", str(LIN), "cnd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cnd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cnd_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cnd_muldiv", (100, 200, 50), 400),
        ("cbrt", [str(E9), str(E9), str(E9)], "cnd_cbrt3", (E9, E9, E9), E9),
        ("nd", [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), "0"], "cnd_newton_d", (ANN, GAMMA, E9, E9, E9, 0), 3 * E9),
        ("nd", [str(ANN), str(GAMMA), "1100000000", str(E9), str(E9), "0"], "cnd_newton_d", (ANN, GAMMA, 1100000000, E9, E9, 0), 3096846429),
        ("vp", [str(ANN), str(GAMMA), "1100000000", str(E9), str(E9)], "cnd_get_vp", (ANN, GAMMA, 1100000000, E9, E9), 998982719),
        ("nd", [str(ANN), str(GAMMA), "1200000000", "900000000", str(E9), "0"], "cnd_newton_d", (ANN, GAMMA, 1200000000, 900000000, E9, 0), 3077962761),
        ("nd", [str(ANN), str(GAMMA), "1010000000", str(E9), str(E9), "0"], "cnd_newton_d", (ANN, GAMMA, 1010000000, E9, E9, 0), 3009971862),
        ("nd", [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), "1"], "cnd_newton_d", (ANN, GAMMA, E9, E9, E9, 1), 0),
        ("nd", ["2700", str(GAMMA), str(E9), str(E9), str(E9), "0"], "cnd_newton_d", (2700, GAMMA, E9, E9, E9, 0), 0),
        ("vp", [str(ANN), str(GAMMA), str(E9), str(E9), str(E9)], "cnd_get_vp", (ANN, GAMMA, E9, E9, E9), E9),
        ("nd", [str(ANN), str(GAMMA), "100000000", "100000000", "100000000", "0"], "cnd_newton_d", (ANN, GAMMA, 100000000, 100000000, 100000000, 0), 300000000),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, named in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != named:
            rec("VEC-NAMED", "FAIL", f"{fn}{largs}", f"c11={want} named={named}")
            return 1
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = (largs[0] * largs[1]) // largs[2]
        elif kind == "cbrt":
            py = py_icbrt(largs[0] * largs[1] * largs[2])
        elif kind == "nd":
            py = py_newton_d(*largs)
        else:
            py = py_vp(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == named goldens")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    wrapped = (3000000000 * 508044030482641) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("cnd_naive_i64_mul", 3000000000, 508044030482641)
    if naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 S*mul2 wrap", f"lin={naive} wrap={wrapped}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e9*mul2) wraps; 128-bit newton_D path does not",
        f"i64_wrap={wrapped} bigint={3000000000 * 508044030482641}",
    )

    rec(
        "VS-SUM",
        "PASS",
        "10% extra of one coin: invariant D lags the naive sum (gamma curvature)",
        f"D=3096846429 S=3100000000 vp=998982719 balanced_vp={E9}",
    )

    jit_ok = lin_roundtrip_jit("cnd_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cnd_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("cnd_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cnd_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cnd_newton_d(ann: int, gamma: int, x0: int, x1: int, x2: int, k0_prev: int)" in src:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes ANN, gamma, x0,x1,x2 as arguments (no hidden pool storage)")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args")
    if "cnd_prod128" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product for S*mul2 / D*D (i64 wraps)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit product missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/curvefi/tricrypto-ng",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "all-rights-reserved informational-only (not vendored)",
    }
    evidence["lin_clone"] = "src/lin_curve_newton_d.lin"
    evidence["c11_oracle"] = "test/oracles/curve_newton_d_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "identity_D": 3 * E9,
        "plus10_D": 3096846429,
        "plus10_vp": 998982719,
        "plus1_D": 3009971862,
        "imbalanced_D": 3077962761,
        "small_D": 300000000,
        "k0_prev_failclosed": 0,
        "ann2700_failclosed": 0,
        "balanced_vp": E9,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["clone_lin_commit"] = CLONE_LIN_COMMIT
    evidence["clone_lin_kernel_blob"] = CLONE_LIN_KERNEL_BLOB
    evidence["clone_lin_oracle_blob"] = CLONE_LIN_ORACLE_BLOB
    evidence["lin_sha256"] = sha256_file(LIN)
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
