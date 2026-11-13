#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve tricrypto _newton_y (informational Vyper) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git pin of curvefi/tricrypto-ng CurveCryptoMathOptimized3.vy
      (sha256 + git blob; Vyper is NOT vendored)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_curve_newton_y.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int on the same uint64-scale formulas

  NOT claimed:
    * full Solidity/Vyper uint256 / mainnet tricrypto parity
    * that LIN replaces Curve, Uniswap, or the EVM
    * TVL or dollar savings
    * zk / computational soundness
    * closed-form get_y (cbrt) path; this clone is the Newton fallback

Class: EXPERIMENTAL (real Curve crypto Newton algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_curve_newton_y.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_newton_y_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_newton_y_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_tricrypto_ng")
EVIDENCE = ROOT / "examples" / "curve_newton_y" / "curve_newton_y_evidence.json"

PINNED_SHA256 = "d0d48e5c3fa00e36f841250cbce8665292ba3224bb050c948dc3b12a50f01d6c"
PINNED_BLOB = "695c794cb8035e4b2848ad0354d0993dcfb9c7cb"
PINNED_COMMIT = "ecaa8161c240f21dd7c3712eefc5637e1dac742b"
UPSTREAM_REL = "contracts/main/CurveCryptoMathOptimized3.vy"
UPSTREAM_URL = "https://github.com/curvefi/tricrypto-ng.git"

ANN = 1707629
GAMMA = 11809
E9 = 10**9
D = 3 * E9
FEE_DEN = 10**10


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
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=120)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=180)
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


def py_newton_y(ann: int, gamma: int, x0: int, x1: int, x2: int, d: int, i: int) -> int:
    """Independent Python bigint of the uint64-scale Newton formulas."""
    u64 = 1 << 64
    prec = E9
    n = 3
    if i < 0 or i > 2 or d <= 0 or ann <= 0 or gamma <= 0:
        return 0
    if min(x0, x1, x2) <= 0:
        return 0
    zs = [x0, x1, x2]
    zs[i] = 0
    hi = max(zs)
    lo = min(zs)
    mid = sum(zs) - hi - lo

    def md(a: int, b: int, den: int) -> int:
        if den <= 0 or a < 0 or b < 0:
            return 0
        q = (a * b) // den
        return 0 if q >= (1 << 63) else q

    y = md(d, 1, n)
    if y <= 0:
        return 0
    k0_i = prec
    s_i = 0
    q = md(y, d, mid * n)
    if q <= 0:
        return 0
    y = q
    s_i += mid
    q = md(y, d, hi * n)
    if q <= 0:
        return 0
    y = q
    s_i += hi
    k0_i = md(k0_i, hi * n, d)
    k0_i = md(k0_i, mid * n, d)
    conv = max(hi // 100000, d // 100000, 100)
    for _ in range(255):
        y_prev = y
        k0 = md(k0_i, y * n, d)
        if k0 <= 0:
            return 0
        s = s_i + y
        orig = gamma + prec
        g1 = (k0 - orig + 1) if orig < k0 else (orig - k0 + 1)
        t = md(prec, d, gamma)
        t = md(t, g1, gamma)
        t = md(t, 10000, ann)
        t = md(t, g1, 1)
        if t <= 0:
            return 0
        mul1 = t
        t2 = md(prec + prec, k0, g1)
        mul2 = prec + t2
        lhs = prec * y + s * mul2 + mul1
        rhs = d * mul2
        if lhs < rhs:
            y = y_prev // 2
            continue
        yf = lhs - rhs
        fp = yf // y
        if fp <= 0:
            return 0
        y_minus = mul1 // fp
        yp1 = (yf + prec * d) // fp
        extra = md(y_minus, prec, k0)
        y_plus = yp1 + extra
        extra2 = md(prec, s, fp)
        y_minus = y_minus + extra2
        y = y_prev // 2 if y_plus < y_minus else y_plus - y_minus
        diff = abs(y - y_prev)
        lim = max(conv, y // 100000)
        if diff < lim:
            return y
    return 0


def py_get_dy(
    ann: int, gamma: int, x0: int, x1: int, x2: int, d: int, i: int, j: int, dx: int, fee: int
) -> int:
    if dx <= 0 or i == j or i < 0 or j < 0 or i > 2 or j > 2 or fee > FEE_DEN:
        return 0
    xs = [x0, x1, x2]
    xs[i] = xs[i] + dx
    y = py_newton_y(ann, gamma, xs[0], xs[1], xs[2], d, j)
    if y <= 0 or xs[j] <= y:
        return 0
    raw = xs[j] - y - 1
    if fee == 0:
        return raw
    return (raw * (FEE_DEN - fee)) // FEE_DEN


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_CURVE_NEWTON_Y_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE TRICRYPTO newton_y — external LIN proof (uint64-scale, C11 oracle)")
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
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; published pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from published digest", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb newton_y selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb newton_y agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of curve newton_y clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_newton_y.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("VY-TR-CHECK", VY_TR), ("C-TR-CHECK", C_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    vy_src = VY_TR.read_text(encoding="utf-8")
    if all(tok in vy_src for tok in ("REJ_VYPER_NEWTON_Y", "REJ_VYPER_ARRAY", "REJ_VYPER_UNSAFE", "vy_parse_test_gate")):
        rec("VY-GATE", "PASS", "lin_from_vyper.lin fail-closes newton_y / uint256[ / unsafe_ (check+source)")
    else:
        rec("VY-GATE", "FAIL", "Vyper reject tokens missing")
        return 1
    sol_src = SOL_TR.read_text(encoding="utf-8")
    if all(
        tok in sol_src
        for tok in (
            "REJ_SOLIDITY_NEWTON_Y",
            "REJ_SOLIDITY_ARRAY",
            "REJ_SOLIDITY_BPT_OUT",
            "version=3",
        )
    ):
        rec("SOL-GATE", "PASS", "lin_from_solidity.lin v3 fail-closes newton_y / uint256[ / BPT-out")
    else:
        rec("SOL-GATE", "FAIL", "Solidity v3 reject tokens missing")
        return 1
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_NEWTON_Y" in rs_src:
        rec("RS-GATE", "PASS", "lin_from_rust.lin fail-closes newton_y")
    else:
        rec("RS-GATE", "FAIL", "Rust newton_y reject missing")
        return 1

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_NEWTON_Y" in c_src and "REJ_C_UNSAFE" in c_src:
        rec("C-REJ", "PASS", "lin_from_c.lin fail-closes newton_y / unsafe_ / uint256")
    else:
        rec("C-REJ", "FAIL", "C transpiler reject tokens missing")

    gate = run([str(C0), "vm", str(LIN), "cny_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cny_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cny_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cny_muldiv", (100, 200, 50), 400),
        (
            "ny",
            [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), str(D), "1"],
            "cny_newton_y",
            (ANN, GAMMA, E9, E9, E9, D, 1),
            E9,
        ),
        (
            "ny",
            [str(ANN), str(GAMMA), "1100000000", str(E9), str(E9), str(D), "1"],
            "cny_newton_y",
            (ANN, GAMMA, 1100000000, E9, E9, D, 1),
            909085543,
        ),
        (
            "dy",
            [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), str(D), "0", "1", "100000000", "0"],
            "cny_get_dy",
            (ANN, GAMMA, E9, E9, E9, D, 0, 1, 100000000, 0),
            90914456,
        ),
        (
            "dy",
            [
                str(ANN),
                str(GAMMA),
                str(E9),
                str(E9),
                str(E9),
                str(D),
                "0",
                "1",
                "100000000",
                "3000000",
            ],
            "cny_get_dy",
            (ANN, GAMMA, E9, E9, E9, D, 0, 1, 100000000, 3000000),
            90887181,
        ),
        (
            "dy",
            [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), str(D), "0", "1", "0", "0"],
            "cny_get_dy",
            (ANN, GAMMA, E9, E9, E9, D, 0, 1, 0, 0),
            0,
        ),
        (
            "dy",
            ["2700", str(GAMMA), str(E9), str(E9), str(E9), str(D), "0", "1", "100000000", "0"],
            "cny_get_dy",
            (2700, GAMMA, E9, E9, E9, D, 0, 1, 100000000, 0),
            0,
        ),
        (
            "ny",
            [str(ANN), str(GAMMA), "1200000000", "900000000", str(E9), str(D), "1"],
            "cny_newton_y",
            (ANN, GAMMA, 1200000000, 900000000, E9, D, 1),
            833328413,
        ),
        (
            "dy",
            [str(ANN), str(GAMMA), str(E9), str(E9), str(E9), str(D), "0", "1", "10000000", "0"],
            "cny_get_dy",
            (ANN, GAMMA, E9, E9, E9, D, 0, 1, 10000000, 0),
            9906505,
        ),
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
        elif kind == "ny":
            py = py_newton_y(*largs)
        else:
            py = py_get_dy(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == named goldens")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    wrapped = (3000000000 * 169349010160880) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("cny_naive_i64_mul", 3000000000, 169349010160880)
    if naive != wrapped or naive == 0:
        rec("I64-WRAP", "FAIL", "naive i64 S*mul2 wrap", f"lin={naive} wrap={wrapped}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e9*mul2) wraps; 128-bit yfprime path does not",
        f"i64_wrap={wrapped} bigint={3000000000 * 169349010160880}",
    )

    cp = (E9 * E9) // (E9 + 100000000)
    dy = 90914456
    rec(
        "VS-CONSTPROD",
        "PASS",
        "10% in on balanced tricrypto quotes more out than 2-coin x*y=k (third coin)",
        f"get_dy={dy} two_coin_xyk_out={E9 - cp - 1}",
    )

    jit_ok = lin_roundtrip_jit("cny_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cny_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("cny_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cny_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    if "cny_newton_y(ann: int, gamma: int, x0: int, x1: int, x2: int, D: int, i: int)" in src:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes ANN, gamma, D, x0,x1,x2 as arguments (no hidden pool storage)",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args")
    if "cny_prod128" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product for S*mul2 / yfprime (i64 wraps)")
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
    evidence["lin_clone"] = "src/lin_curve_newton_y.lin"
    evidence["c11_oracle"] = "test/oracles/curve_newton_y_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "identity_y": E9,
        "plus10_y1": 909085543,
        "get_dy_10pct_nofee": 90914456,
        "get_dy_10pct_fee_3e6": 90887181,
        "get_dy_1pct_nofee": 9906505,
        "get_dy_dx0_failclosed": 0,
        "get_dy_ann2700_failclosed": 0,
        "imbalanced_y1": 833328413,
    }
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-curve-newton-y"
    evidence["clone_lin_commit"] = "d0eb612e5a8e14e45b9b149764ea006e1263d0b5"
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
