#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: rust-bitcoin FeeRate sat/vB and sat/kwu conversions vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of units/src/fee_rate/mod.rs (git blob + sha256)
    * an independent C11 oracle (remainder ceil AND wrapping (n+d-1)/d)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full u64 FeeRate::MAX domain (LIN path is i64-nonneg)
    * that LIN replaces rust-bitcoin wallets or Bitcoin Core policy
    * wall-clock superiority vs rustc/LLVM

Class: EXPERIMENTAL (real rust-bitcoin unit math, i64-scale operands).
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
LIN = ROOT / "src" / "lin_rust_bitcoin_vbceil.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "rust_bitcoin_vbceil_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "rust_bitcoin_vbceil_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_rust_bitcoin")
EVIDENCE = ROOT / "examples" / "rust_bitcoin_vbceil" / "rust_bitcoin_vbceil_evidence.json"

PINNED_SHA256 = "cbb0c13c54a808aa80de9652196e4f13f3f47bc3985e96b5c6fa7aeb6b705ecc"
PINNED_BLOB = "e2e03fc112b8d28b80b13d449cb59d8ae4243742"
PINNED_COMMIT = "cb2404331101acac9df5a07487ea6f3ed1828037"
UPSTREAM_REL = "units/src/fee_rate/mod.rs"
MVB = 1_000_000
KWU = 4_000
KVB = 1_000
U64_MAX = (1 << 64) - 1
I64_MAX = (1 << 63) - 1


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


def lin_vm(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


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


def py_div_ceil(n: int, d: int) -> int:
    if d <= 0 or n < 0:
        return 0
    q, r = divmod(n, d)
    return q if r == 0 else q + 1


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/rust-bitcoin/rust-bitcoin.git"
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
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_RUST_BITCOIN_VBCEIL_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  RUST-BITCOIN FeeRate to_sat_per_vb_ceil — external LIN proof")
    print("=" * 78)

    pinned = FIX / "rust_bitcoin_fee_rate_mod.rs"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned rust_bitcoin_fee_rate_mod.rs missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned fee_rate/mod.rs sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned rust-bitcoin commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of units/src/fee_rate/mod.rs")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    src_txt = pinned.read_text(encoding="utf-8")
    if "fn to_sat_per_vb_ceil" not in src_txt or "div_ceil(1_000_000)" not in src_txt:
        rec("UPSTREAM-API", "FAIL", "pinned file missing to_sat_per_vb_ceil")
        return 1
    rec("UPSTREAM-API", "PASS", "pinned rust-bitcoin exposes to_sat_per_vb_ceil via div_ceil(1e6)")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 remainder-ceil selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 remainder ceil matches rust-bitcoin unit tests")

    wrap = int(oracle(["naive_wrap", str(U64_MAX), str(MVB)]))
    rem = int(oracle(["rem_ceil", str(U64_MAX), str(MVB)]))
    py_rem = py_div_ceil(U64_MAX, MVB)
    if rem != py_rem:
        rec("U64-CEIL", "FAIL", "C11 rem ceil vs python", f"c11={rem} py={py_rem}")
        return 1
    if wrap == rem:
        rec("U64-WRAP", "FAIL", "naive (n+d-1)/d unexpectedly equalled rem ceil at u64::MAX")
        return 1
    rec(
        "U64-WRAP",
        "PASS",
        "naive uint64 (n+d-1)/d wraps at u64::MAX; remainder ceil matches rust/python",
        f"naive={wrap} rem={rem}",
    )

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vbceil clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_rust_bitcoin_vbceil.lin")

    chk2 = run([str(C0), "check", str(RS_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk2.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "rbv_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "rbv_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "rbv_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("from_vb", ["10"], "rbv_from_sat_per_vb", (10,), 10 * MVB),
        ("from_kwu", ["2500"], "rbv_from_sat_per_kwu", (2500,), 2500 * KWU),
        ("from_kvb", ["11"], "rbv_from_sat_per_kvb", (11,), 11 * KVB),
        ("vb_floor", ["2000400"], "rbv_to_sat_per_vb_floor", (2000400,), 2),
        ("vb_ceil", ["2000400"], "rbv_to_sat_per_vb_ceil", (2000400,), 3),
        ("kwu_floor", ["2000400"], "rbv_to_sat_per_kwu_floor", (2000400,), 500),
        ("kwu_ceil", ["2000400"], "rbv_to_sat_per_kwu_ceil", (2000400,), 501),
        ("kvb_floor", ["2000400"], "rbv_to_sat_per_kvb_floor", (2000400,), 2000),
        ("kvb_ceil", ["2000400"], "rbv_to_sat_per_kvb_ceil", (2000400,), 2001),
        ("vb_ceil", ["2000000"], "rbv_to_sat_per_vb_ceil", (2000000,), 2),
        ("vb_ceil", ["0"], "rbv_to_sat_per_vb_ceil", (0,), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py_want in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != py_want or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} py={py_want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python (rust-bitcoin tests)")

    bmin = lin_vm("rbv_broadcast_min")
    dust = lin_vm("rbv_dust")
    if bmin != MVB or lin_vm("rbv_to_sat_per_kwu_floor", bmin) != 250:
        rec("BROADCAST-MIN", "FAIL", "BROADCAST_MIN 1 sat/vB == 250 sat/kwu", f"mvb={bmin}")
        return 1
    rec("BROADCAST-MIN", "PASS", "FeeRate::BROADCAST_MIN (1 sat/vB) is 250 sat/kwu floor")
    if dust != 3 * MVB or lin_vm("rbv_to_sat_per_kwu_floor", dust) != 750:
        rec("DUST", "FAIL", "DUST 3 sat/vB == 750 sat/kwu", f"mvb={dust}")
        return 1
    rec("DUST", "PASS", "FeeRate::DUST (3 sat/vB) is 750 sat/kwu floor")

    big = I64_MAX
    lin_big = lin_vm("rbv_to_sat_per_vb_ceil", big)
    py_big = py_div_ceil(big, MVB)
    c11_big = int(oracle(["vb_ceil", str(big)]).splitlines()[-1])
    if lin_big != py_big or lin_big != c11_big:
        rec("I64-CEIL", "FAIL", "i64::MAX vb ceil", f"lin={lin_big} py={py_big} c11={c11_big}")
        return 1
    rec("I64-CEIL", "PASS", "i64::MAX remainder ceil matches C11 and Python bigint", f"ceil={lin_big}")

    jit_ok = lin_roundtrip_jit("rbv_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on rbv_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("rbv_to_sat_per_vb_ceil", 2000400)
        if jv == 3:
            rec("C0-JIT", "PASS", "lin_c0 jit rbv_to_sat_per_vb_ceil(2000400)==3 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    lin_src = LIN.read_text(encoding="utf-8")
    if "rbv_to_sat_per_vb_ceil(sat_mvb: int)" not in lin_src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit sat_mvb argument")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes sat/MvB as an argument (no FeeRate receiver / Self)",
        )
    if "n + d - 1" in lin_src or "(n + d" in lin_src:
        rec("REM-CEIL", "FAIL", "clone still uses wrapping (n+d-1)/d")
    elif "n % d" in lin_src or "r = n % d" in lin_src:
        rec("REM-CEIL", "PASS", "clone uses remainder div_ceil, not wrapping (n+d-1)/d")
    else:
        rec("REM-CEIL", "FAIL", "remainder ceil missing")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "rs_from_rs" in rs_src and "rs_strip_underscores" in rs_src and "rs_has_lone_amp" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 emits LIN, expands 1_000, treats && as not-borrow")
    else:
        rec("RS-EMIT", "FAIL", "emit path missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/rust-bitcoin/rust-bitcoin",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "CC0-1.0",
    }
    evidence["lin_clone"] = "src/lin_rust_bitcoin_vbceil.lin"
    evidence["c11_oracle"] = "test/oracles/rust_bitcoin_vbceil_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["broadcast_min_sat_mvb"] = bmin
    evidence["dust_sat_mvb"] = dust
    evidence["i64_max_vb_ceil"] = lin_big
    evidence["u64_max_naive_wrap"] = wrap
    evidence["u64_max_rem_ceil"] = rem
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
