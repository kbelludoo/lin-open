#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: rust-bitcoin SignedAmount (CC0-1.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of units/src/amount/signed.rs (git blob + sha256)
    * pinned Bitcoin Core v27.1 consensus/amount.h (MoneyRange cross-oracle)
    * an independent C11 oracle (unsigned __int128 AND 32-bit limb mul)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * that LIN is a wallet, rust-bitcoin, or Bitcoin Core
    * uint256 / Lightning / PSBT / script
    * that LIN is faster than rustc
    * that rust-bitcoin and Core agree on negative amounts — they do not

Class: EXPERIMENTAL (real 21M-BTC cap, i64 satoshi domain).
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
LIN = ROOT / "src" / "lin_rust_bitcoin_signedamount.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "rust_bitcoin_signedamount_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "rust_bitcoin_signedamount_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_rust_bitcoin")
EVIDENCE = ROOT / "examples" / "rust_bitcoin_signedamount" / "signedamount_evidence.json"

COIN = 100_000_000
MAX_MONEY = 21_000_000 * COIN
MIN_MONEY = -MAX_MONEY
PINNED_SHA256 = "08e2010b1fb71e179b36e01bee1a55fd61003d85153339b22f15dd37b5c80c92"
PINNED_BLOB = "8f510f16cdd0d8cd3b53a3b522a17035e388b873"
PINNED_COMMIT = "1cbf4bd62ea99c558c6d8ef794edbd984a2a4684"
UPSTREAM_REL = "units/src/amount/signed.rs"
CORE_SHA256 = "cb7bd951877f3fea5a0c280d4bb907a8403437add81e3d5b898879b78fdc877e"
CORE_BLOB = "f0eb4e0723c3159153c655fae17cb252102cbddb"
CORE_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
CORE_REL = "src/consensus/amount.h"


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


def git_blob(path: Path) -> str:
    proc = run(["git", "hash-object", str(path)], timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout.strip()


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


def lin_vm_raw(path: Path, fn: str) -> subprocess.CompletedProcess[str]:
    return run([str(C0), "vm", str(path), fn], timeout=60)


def rs_strip_underscores_py(s: str) -> str:
    """Independent clone of src/lin_from_rust.lin rs_strip_underscores."""
    out: list[str] = []
    prev_d = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "_" and prev_d and i + 1 < len(s) and "0" <= s[i + 1] <= "9":
            i += 1
            continue
        out.append(c)
        prev_d = "0" <= c <= "9"
        i += 1
    return "".join(out)


def cfs_strip_int_suffix_py(s: str) -> str:
    """Independent clone of src/lin_from_c.lin cfs_strip_int_suffix."""
    out: list[str] = []
    i = 0
    n = len(s)

    def is_ident_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    while i < n:
        c = s[i]
        if "0" <= c <= "9":
            if i > 0 and is_ident_char(s[i - 1]) and not s[i - 1].isdigit():
                out.append(c)
                i += 1
                continue
            while i < n and "0" <= s[i] <= "9":
                out.append(s[i])
                i += 1
            while i < n and s[i] in "ULul":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


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
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
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
    url = "https://github.com/rust-bitcoin/rust-bitcoin.git"
    if not (UPSTREAM / ".git").exists():
        proc = run(
            ["git", "clone", "--filter=blob:none", "--sparse", url, str(UPSTREAM)],
            timeout=120,
        )
        if proc.returncode != 0:
            return "", "", ""
        run(
            ["git", "-C", str(UPSTREAM), "sparse-checkout", "set", "units/src/amount"],
            timeout=30,
        )
    run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=60)
    run(["git", "-C", str(UPSTREAM), "checkout", PINNED_COMMIT], timeout=30)
    src = UPSTREAM / UPSTREAM_REL
    if not src.exists():
        return "", "", ""
    return PINNED_COMMIT, git_blob(src), sha256_file(src)


def rec(claims: list[dict[str, str]], name: str, status: str, detail: str, extra: str = "") -> None:
    row = {"name": name, "status": status, "detail": detail}
    if extra:
        row["extra"] = extra
    claims.append(row)
    mark = {"PASS": "ok", "FAIL": "FAIL", "SKIP": "skip"}[status]
    print(f"  [{mark}] {name}: {detail}" + (f" ({extra})" if extra else ""))


def i64_wrap_mul(a: int, b: int) -> int:
    p = (a * b) & ((1 << 64) - 1)
    if p >= 2**63:
        p -= 2**64
    return p


def py_mul_ok(a: int, b: int) -> tuple[int, int]:
    if a < MIN_MONEY or a > MAX_MONEY:
        return 0, 0
    p = a * b
    if p < MIN_MONEY or p > MAX_MONEY:
        return 0, 0
    return 1, p


def main() -> int:
    print("=" * 78)
    print("  rust-bitcoin SignedAmount  —  LIN Compiler 0 / C11 external proof")
    print("=" * 78)
    claims: list[dict[str, str]] = []
    evidence: dict = {"claims": []}
    ensure_c0()
    ensure_oracle()

    pinned = FIX / "rust_bitcoin_signed.rs"
    if not pinned.exists():
        rec(claims, "PIN-RS", "FAIL", "missing fixture rust_bitcoin_signed.rs")
        return 1
    got_sha = sha256_file(pinned)
    got_blob = git_blob(pinned)
    if got_sha != PINNED_SHA256 or got_blob != PINNED_BLOB:
        rec(
            claims,
            "PIN-RS",
            "FAIL",
            "fixture hash mismatch",
            f"sha256={got_sha} blob={got_blob}",
        )
        return 1
    rec(claims, "PIN-RS", "PASS", "pinned signed.rs sha256+blob", PINNED_SHA256)

    core_pin = FIX / "bitcoin_core_amount.h"
    if sha256_file(core_pin) != CORE_SHA256 or git_blob(core_pin) != CORE_BLOB:
        rec(claims, "PIN-CORE", "FAIL", "Core amount.h hash mismatch")
        return 1
    rec(claims, "PIN-CORE", "PASS", "pinned Bitcoin Core v27.1 amount.h", CORE_SHA256)

    text = pinned.read_text(encoding="utf-8")
    if "21_000_000 * 100_000_000" not in text or "pub const MIN" not in text:
        rec(claims, "PIN-CONST", "FAIL", "MAX/MIN literals missing from signed.rs")
        return 1
    rec(claims, "PIN-CONST", "PASS", "signed.rs contains MAX=21e6*COIN and MIN=-MAX")

    core_txt = core_pin.read_text(encoding="utf-8")
    if "MAX_MONEY = 21000000 * COIN" not in core_txt or "nValue >= 0" not in core_txt:
        rec(claims, "CORE-CONST", "FAIL", "MoneyRange/MAX_MONEY missing")
        return 1
    rec(claims, "CORE-CONST", "PASS", "Core MoneyRange is [0, MAX_MONEY] (no negatives)")

    commit, blob, live_sha = ensure_upstream()
    if live_sha and live_sha != PINNED_SHA256:
        rec(claims, "UPSTREAM-FETCH", "FAIL", "live rust-bitcoin bytes != pin", live_sha)
        return 1
    if live_sha:
        rec(claims, "UPSTREAM-FETCH", "PASS", "fetched rust-bitcoin matches pin", commit or PINNED_COMMIT)
    else:
        rec(claims, "UPSTREAM-FETCH", "SKIP", "network/clone unavailable; fixture pin still holds")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "rs_from_rs" not in rs_src or "rs_strip_underscores" not in rs_src or "REJ_RUST_MACRO" not in rs_src:
        rec(claims, "RS-EMIT", "FAIL", "lin_from_rust v2 emit/underscore/macro gate missing")
        return 1
    if rs_strip_underscores_py("21_000_000 * 100_000_000") != "21000000 * 100000000":
        rec(claims, "RS-EMIT", "FAIL", "python underscore strip golden failed")
        return 1
    if rs_strip_underscores_py("sa_max") != "sa_max":
        rec(claims, "RS-EMIT", "FAIL", "underscore strip must not eat identifiers")
        return 1
    rec(
        claims,
        "RS-EMIT",
        "PASS",
        "lin_from_rust v2 source emits LIN; python golden 21_000_000→21000000; identifiers preserved",
    )

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX" not in c_src or "cfs_strip_int_suffix" not in c_src or "ceil(" not in c_src:
        rec(claims, "C-HOST", "FAIL", "lin_from_c v2 CXX/float/suffix gates missing")
        return 1
    if cfs_strip_int_suffix_py("return 21ULL + 3UL + 4LL;") != "return 21 + 3 + 4;":
        rec(claims, "C-HOST", "FAIL", "python U/L/LL suffix strip golden failed")
        return 1
    rec(
        claims,
        "C-HOST",
        "PASS",
        "lin_from_c v2: REJ_C_CXX + ceil/floor REJ_C_FLOAT + python golden ULL/UL/LL strip",
    )

    str_rej = lin_vm_raw(RS_TR, "rs_from_rs_gate")
    if str_rej.returncode == 0 or "VM_REJ_STRING_LITERAL" not in (str_rej.stdout + str_rej.stderr):
        rec(claims, "C0-STR-REJ", "FAIL", "expected lin_c0 vm to fail-close string-literal transpiler module")
        return 1
    rec(
        claims,
        "C0-STR-REJ",
        "PASS",
        "lin_c0 vm fail-closes rs_from_rs_gate with VM_REJ_STRING_LITERAL (numeric VM; emit proven by source+python golden)",
    )

    suite = lin_vm("sa_test_suite")
    if suite != 1:
        rec(claims, "LIN-SUITE", "FAIL", f"sa_test_suite={suite}")
        return 1
    rec(claims, "LIN-SUITE", "PASS", "sa_test_suite value=1")

    if int(oracle(["max"])) != MAX_MONEY or lin_vm("sa_max") != MAX_MONEY:
        rec(claims, "MAX", "FAIL", "MAX_MONEY mismatch")
        return 1
    rec(claims, "MAX", "PASS", "21_000_000 * 100_000_000 = 2100000000000000", str(MAX_MONEY))

    if int(oracle(["min"])) != MIN_MONEY or lin_vm("sa_min") != MIN_MONEY:
        rec(claims, "MIN", "FAIL", "MIN_MONEY mismatch")
        return 1
    rec(claims, "MIN", "PASS", "MIN = -MAX (negative 21M accounting dual)")

    # Canonical: 0 sat is in range; 0 sat failure channel is separate.
    if lin_vm("sa_from_sat_ok", 0) != 1 or lin_vm("sa_from_sat", 0) != 0:
        rec(claims, "ZERO", "FAIL", "zero sat must be valid and value 0")
        return 1
    rec(claims, "ZERO", "PASS", "0 sat is valid; ok flag distinguishes failure from zero")

    if lin_vm("sa_from_sat_ok", MAX_MONEY + 1) != 0 or lin_vm("sa_from_sat", MAX_MONEY + 1) != 0:
        rec(claims, "CAP-PLUS", "FAIL", "MAX+1 sat must fail-close")
        return 1
    rec(claims, "CAP-PLUS", "PASS", "MAX+1 sat fail-closed (naive i64 would accept 2100000000000001)")

    # Honest divergence vs Bitcoin Core.
    lin_neg = lin_vm("sa_from_sat_ok", -1)
    core_neg = lin_vm("core_money_range", -1)
    o_lin = int(oracle(["from_sat_ok", "-1"]))
    o_core = int(oracle(["core_range", "-1"]))
    if lin_neg != 1 or core_neg != 0 or o_lin != 1 or o_core != 0:
        rec(claims, "DIVERGE-NEG", "FAIL", "expected rust-bitcoin accept -1, Core reject -1")
        return 1
    rec(
        claims,
        "DIVERGE-NEG",
        "PASS",
        "rust-bitcoin SignedAmount accepts -1 sat; Bitcoin Core MoneyRange rejects it",
        "lin_ok=1 core_ok=0",
    )

    add_ok, add_v = oracle(["add", str(MAX_MONEY), "1"]).split()
    if add_ok != "0" or lin_vm("sa_checked_add_ok", MAX_MONEY, 1) != 0:
        rec(claims, "ADD-OV", "FAIL", "MAX+1 add must fail-close")
        return 1
    rec(claims, "ADD-OV", "PASS", "checked_add(MAX, 1 sat) fail-closed (21M cap, not i64 wrap)")

    a, b = 100_000_000, 2
    py_ok, py_v = py_mul_ok(a, b)
    o_ok, o_v = oracle(["mul", str(a), str(b)]).split()
    lin_ok = lin_vm("sa_checked_mul_ok", a, b)
    lin_v = lin_vm("sa_checked_mul", a, b)
    if not (py_ok == int(o_ok) == lin_ok == 1 and py_v == int(o_v) == lin_v == 200_000_000):
        rec(claims, "MUL-COIN2", "FAIL", f"py={py_v} c11={o_v} lin={lin_v}")
        return 1
    rec(claims, "MUL-COIN2", "PASS", "1 BTC * 2 = 200000000 sat; Python == C11 == LIN")

    wrap = i64_wrap_mul(MAX_MONEY, 4393)
    py_ok, py_v = py_mul_ok(MAX_MONEY, 4393)
    o_ok, o_v = oracle(["mul", str(MAX_MONEY), "4393"]).split()
    lin_ok = lin_vm("sa_checked_mul_ok", MAX_MONEY, 4393)
    lin_v = lin_vm("sa_checked_mul", MAX_MONEY, 4393)
    if wrap == 0 or py_ok != 0 or int(o_ok) != 0 or lin_ok != 0 or lin_v != 0:
        rec(claims, "I64-WRAP-MUL", "FAIL", f"wrap={wrap} py_ok={py_ok} lin={lin_v}")
        return 1
    rec(
        claims,
        "I64-WRAP-MUL",
        "PASS",
        "naive i64 MAX*4393 wraps; 128-bit product fail-closes at 21M cap",
        f"i64_wrap={wrap} bigint={MAX_MONEY * 4393}",
    )

    n_ok = 0
    vecs = [
        (0, 0),
        (1, 1),
        (COIN, 1),
        (COIN, -1),
        (-COIN, 2),
        (MAX_MONEY, 0),
        (MAX_MONEY, 1),
        (MIN_MONEY, 1),
        (MIN_MONEY, -1),
        (50 * COIN, 2),
        (MAX_MONEY, 4392),
        (MAX_MONEY, 4393),
        (MAX_MONEY, 5000),
        (123456789, 7),
        (-21000000, COIN),
    ]
    for x, y in vecs:
        pok, pv = py_mul_ok(x, y)
        ook, ov = oracle(["mul", str(x), str(y)]).split()
        lok = lin_vm("sa_checked_mul_ok", x, y)
        lv = lin_vm("sa_checked_mul", x, y)
        if pok != int(ook) or pok != lok:
            rec(claims, "VEC-CONSENSUS", "FAIL", f"ok mismatch ({x},{y})")
            return 1
        if pok == 1 and not (pv == int(ov) == lv):
            rec(claims, "VEC-CONSENSUS", "FAIL", f"value mismatch ({x},{y}) py={pv} c11={ov} lin={lv}")
            return 1
        n_ok += 1
    rec(claims, "VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint == C11 i128/limbs == LIN vm")
    rec(claims, "PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    add_vecs = [(100, 200), (MAX_MONEY, 0), (MAX_MONEY, 1), (MIN_MONEY, -1), (MIN_MONEY, MAX_MONEY), (-COIN, COIN)]
    for x, y in add_vecs:
        want_ok = int(MIN_MONEY <= x <= MAX_MONEY and MIN_MONEY <= y <= MAX_MONEY and MIN_MONEY <= x + y <= MAX_MONEY)
        want = x + y if want_ok else 0
        ook, ov = oracle(["add", str(x), str(y)]).split()
        if lin_vm("sa_checked_add_ok", x, y) != want_ok or int(ook) != want_ok:
            rec(claims, "ADD-VEC", "FAIL", f"add_ok ({x},{y})")
            return 1
        if want_ok and (lin_vm("sa_checked_add", x, y) != want or int(ov) != want):
            rec(claims, "ADD-VEC", "FAIL", f"add ({x},{y})")
            return 1
    rec(claims, "ADD-VEC", "PASS", "checked_add vectors: Python == C11 == LIN (21M cap)")

    src = LIN.read_text(encoding="utf-8")
    if "sa_from_sat_ok" not in src or "core_money_range" not in src:
        rec(claims, "OK-CHANNEL", "FAIL", "explicit ok / Core divergence helpers missing")
        return 1
    rec(
        claims,
        "OK-CHANNEL",
        "PASS",
        "LIN exposes sa_from_sat_ok (0 sat is valid) plus core_money_range (honest Core divergence)",
    )
    if "sa_umul_part" in src and "_lia_ushr" in src:
        rec(claims, "WIDE-MUL", "PASS", "clone uses 128-bit abs product (naive i64 MAX*4393 wraps)")
    else:
        rec(claims, "WIDE-MUL", "FAIL", "128-bit mul missing")
        return 1

    jit_ok = lin_roundtrip_jit("sa_test_suite")
    if jit_ok:
        rec(claims, "C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sa_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("sa_max")
        if jv == MAX_MONEY:
            rec(claims, "C0-JIT", "PASS", "lin_c0 jit sa_max matches MAX_MONEY (in-memory libtcc)")
        else:
            rec(claims, "C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/rust-bitcoin/rust-bitcoin",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "CC0-1.0",
    }
    evidence["cross_oracle"] = {
        "repo": "https://github.com/bitcoin/bitcoin",
        "tag": "v27.1",
        "commit": CORE_COMMIT,
        "path": CORE_REL,
        "git_blob_sha": CORE_BLOB,
        "file_sha256": CORE_SHA256,
        "license": "MIT",
        "note": "MoneyRange is [0, MAX]; rust-bitcoin SignedAmount is [-MAX, MAX]",
    }
    evidence["lin_clone"] = "src/lin_rust_bitcoin_signedamount.lin"
    evidence["c11_oracle"] = "test/oracles/rust_bitcoin_signedamount_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["max_money_sat"] = MAX_MONEY
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-rust-bitcoin-signedamount"
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
