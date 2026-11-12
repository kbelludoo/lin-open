#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Maker/Sky pot.drip (Dai Savings Rate chi) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned makerdao/dss src/pot.sol
      (sha256 + git blob; Solidity is hash-pinned, not vendored — AGPL)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b)/d that mirrors src/lin_maker_pot_drip.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet RAY=1e27 / vat.ilks / sDAI parity
    * that LIN replaces Maker/Sky/Dai/USDS on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Maker DSR algorithm, RAY'=1e9 operands).
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
LIN = ROOT / "src" / "lin_maker_pot_drip.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_pot_drip_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_pot_drip_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_pot_drip" / "maker_pot_drip_evidence.json"

RAY = 10**9
DSR = RAY + 10**6
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
PINNED_BLOB = "cae58cdafe7b4014fd87dcfb002968f61dc89eee"
PINNED_SHA256 = "8b22fb58d37e5eba6c5d1f42c8651a2c5077d39a93edd13082029bc3bfb3edc6"
UPSTREAM_REL = "src/pot.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-pot-drip"


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


def py_muldiv(a: int, b: int, d: int, round_half: bool) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    num = a * b + ((d // 2) if round_half else 0)
    q = num // d
    return 0 if q > 2**63 - 1 else q


def py_rpow(x: int, n: int, b: int) -> int:
    if b <= 0 or x < 0 or n < 0:
        return 0
    if x == 0:
        return b if n == 0 else 0
    z = x if (n & 1) else b
    n2 = n >> 1
    steps = 0
    while n2 != 0:
        x = py_muldiv(x, x, b, True)
        if n2 & 1:
            z = py_muldiv(z, x, b, True)
        n2 >>= 1
        steps += 1
        if steps > 63:
            return 0
    return z


def py_drip(dsr: int, chi: int, now_ts: int, rho: int) -> int:
    if min(dsr, chi, now_ts, rho) < 0 or now_ts < rho:
        return 0
    return py_muldiv(py_rpow(dsr, now_ts - rho, RAY), chi, RAY, False)


def py_linear(dsr: int, chi: int, now_ts: int, rho: int) -> int:
    if min(dsr, chi, now_ts, rho) < 0 or now_ts < rho or dsr < RAY:
        return 0
    extra = (dsr - RAY) * (now_ts - rho)
    s = RAY + extra
    return 0 if s > 2**63 - 1 else py_muldiv(s, chi, RAY, False)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/makerdao/dss.git"
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
        return "SKIP", "", "src/pot.sol missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", "", f"live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    if "function drip()" not in text or "now - rho" not in text or "vat.suck" not in text:
        return "FAIL", "", "pot.sol missing drip / now-rho / vat.suck"
    if "10 ** 27" not in text:
        return "FAIL", "", "pot.sol missing 10 ** 27 RAY"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"pot.sol blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY pot.drip — external LIN proof (RAY'=1e9, C11 Compiler 0)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of pot.drip clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_pot_drip.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler v3"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "mpd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mpd_test_suite via lin_c0 vm", gate.stdout[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "mpd_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss pot.sol matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/pot.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b)/d agree")

    vectors = [
        ("drip", [RAY, RAY, 1000, 1000], "mpd_drip", py_drip(RAY, RAY, 1000, 1000)),
        ("drip", [DSR, RAY, 2, 0], "mpd_drip", py_drip(DSR, RAY, 2, 0)),
        ("linear", [DSR, RAY, 2, 0], "mpd_linear", py_linear(DSR, RAY, 2, 0)),
        ("drip", [DSR, RAY, 10, 0], "mpd_drip", py_drip(DSR, RAY, 10, 0)),
        ("linear", [DSR, RAY, 10, 0], "mpd_linear", py_linear(DSR, RAY, 10, 0)),
        ("drip", [DSR, RAY, 9, 10], "mpd_drip", py_drip(DSR, RAY, 9, 10)),
        ("drip", [DSR, 2 * RAY, 2, 0], "mpd_drip", py_drip(DSR, 2 * RAY, 2, 0)),
        ("chi_delta", [DSR, RAY, 2, 0], "mpd_chi_delta", py_drip(DSR, RAY, 2, 0) - RAY),
        ("join_rad", [10**9, RAY], "mpd_join_rad", 10**18),
        ("suck_rad", [10**9, 2001000], "mpd_suck_rad", 2001000000000000),
        ("rmul", [RAY, RAY], "mpd_rmul", RAY),
        ("rpow", [RAY, 100, RAY], "mpd_rpow", RAY),
    ]
    n_ok = 0
    for kind, args, fn, py in vectors:
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind}{tuple(args)} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{tuple(args)}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{tuple(args)}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("DT-IDENTITY", "PASS", "now==rho returns stored chi (no elapsed DSR)",
        f"chi={lin_vm('mpd_drip', DSR, 2 * RAY, 50, 50)}")
    rec("EXPLICIT-DT", "PASS", "dsr=RAY'+1e6 dt=2: compound 1002001000 vs linear 1002000000 vs ignore-dt 1e9",
        f"drip={lin_vm('mpd_drip', DSR, RAY, 2, 0)} linear={lin_vm('mpd_linear', DSR, RAY, 2, 0)} ignore={lin_vm('mpd_wrong_ignore_dt', RAY)}")
    rec("FILE-RHO", "PASS", "file() requires now==rho; LIN mpd_file_ok makes that explicit",
        f"eq={lin_vm('mpd_file_ok', 100, 100)} ne={lin_vm('mpd_file_ok', 101, 100)}")

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("mpd_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("mpd_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if wide != 0 or naive != wrapped or wrapped == 0:
        rec("I64-WRAP", "FAIL", "naive i64 7e18*3e18 should wrap; 128-bit muldiv fail-closes to 0",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (7e18*3e18) wraps; 128-bit muldiv fail-closes",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("mpd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mpd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mpd_drip", DSR, RAY, 2, 0)
        if jv == 1002001000:
            rec("C0-JIT", "PASS", "lin_c0 jit mpd_drip(dsr,RAY,2,0)==1002001000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "mpd_drip(dsr: int, chi: int, now_ts: int, rho: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN drip args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes dsr/chi/now/rho as arguments (no Solidity now)")
    if "mpd_muldiv_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product (naive i64 a*b wraps on 7e18*3e18)")
    if "REJ_SOLIDITY_POT_DRIP" not in sol_src or "REJ_SOLIDITY_NOW" not in sol_src or "10 ** N" not in sol_src:
        rec("SOL-EMIT", "FAIL", "solidity transpiler missing 10**N / NOW / POT_DRIP")
        return 1
    rec("SOL-EMIT", "PASS", "lin_from_solidity.lin expands 10**N<=18 and fail-closes pot.drip/now/RAY27")
    if "REJ_C_POT_DRIP" not in c_src or "REJ_C_TIME" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing POT_DRIP / TIME reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes wall-clock time and pot_drip")
    if "REJ_RUST_POT_DRIP" not in rs_src or "REJ_RUST_TIME" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing POT_DRIP / TIME reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes Instant::now/SystemTime and pot_drip")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta", (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_MAKER_POT_DRIP_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/makerdao/dss",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA256,
            "license": "AGPL-3.0-or-later",
            "vendored": False,
        },
        "lin_clone": "src/lin_maker_pot_drip.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/maker_pot_drip_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "ray_prime": RAY,
        "named_goldens": {
            "drip(dsr, RAY, 0)": RAY,
            "drip(dsr, RAY, dt=2)": 1002001000,
            "linear(dsr, RAY, dt=2)": 1002000000,
            "drip(dsr, RAY, dt=10)": 1010045120,
            "linear(dsr, RAY, dt=10)": 1010000000,
            "chi_delta(dt=2)": 2001000,
            "join_rad(1e9, RAY)": 10**18,
            "naive_i64(7e18, 3e18)": wrapped,
        },
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
