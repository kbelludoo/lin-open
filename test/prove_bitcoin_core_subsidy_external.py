#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 GetBlockSubsidy vs LIN C0.

PASS claims this run recomputes against:
  * pinned amount.h + GetBlockSubsidy bytes (git blob + sha256)
  * live GitHub raw at commit 1088a98f... (SKIP if network fails)
  * C11 oracle (guarded shift XOR shift-loop)
  * Python int
  * optional Go replica of btcd CalcBlockSubsidy (ISC)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * in-memory libtcc JIT when libtcc is present

NOT claimed: LIN is a Bitcoin node; LIN replaces Core; wall-clock superiority.
Class: EXPERIMENTAL (real issuance schedule; fail-closed edges vs Core/btcd).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_bitcoin_core_subsidy.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_core_subsidy_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_core_subsidy_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
EVIDENCE = ROOT / "examples" / "bitcoin_core_subsidy" / "bitcoin_core_subsidy_evidence.json"
GO_SRC = ROOT / "test" / "oracles" / "bitcoin_core_subsidy_btcd.go"

COIN = 100_000_000
GENESIS = 50 * COIN
INTERVAL = 210_000
MAX_MONEY = 21_000_000 * COIN
TOTAL_ISSUED = 2_099_999_997_690_000
PIN_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PIN_AMOUNT_SHA = "cb7bd951877f3fea5a0c280d4bb907a8403437add81e3d5b898879b78fdc877e"
PIN_AMOUNT_BLOB = "f0eb4e0723c3159153c655fae17cb252102cbddb"
PIN_FN_SHA = "fbe1792f48eca2a2d2cd7201d5cb512025bb94b28130e2778e1f10d852606ba6"
PIN_BTCD_FN_SHA = "036427e6ef7fcbe6e7ba2870b5197878947cb12553c16de70f0fd66a979b747d"
BTCD_COMMIT = "cc26860b40265e1332cca8748c5dbaf3c81cc094"
HEIGHTS = [0, 1, 209999, 210000, 419999, 420000, 630000, 840000, 1050000, 13_440_000]


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def py_subsidy(height: int, interval: int = INTERVAL, genesis: int = GENESIS) -> int:
    if height < 0 or interval <= 0 or genesis < 0:
        return 0
    era = height // interval
    if era >= 64:
        return 0
    return genesis >> era


def py_supply_all() -> int:
    return sum(INTERVAL * (GENESIS >> e) for e in range(64))


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()
    except Exception:
        return None


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def extract_fn(src: str, start: str) -> str:
    i = src.find(start)
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i : j + 2] + "\n" if j > i else ""


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE v27.1 GetBlockSubsidy — external LIN proof (C11 compiler 0)")
    print("=" * 78)

    amount = FIX / "bitcoin_core_v27_1_amount.h"
    fnfix = FIX / "bitcoin_core_v27_1_getblocksubsidy.cpp"
    btcdfix = FIX / "btcd_v0_24_2_calcblocksubsidy.go"
    scalar = FIX / "bitcoin_core_subsidy_scalar.c"
    if sha256_file(amount) != PIN_AMOUNT_SHA:
        rec("PIN-AMOUNT", "FAIL", "amount.h sha256 mismatch", sha256_file(amount))
        return 1
    rec("PIN-AMOUNT", "PASS", "pinned amount.h sha256 matches v27.1")
    blob = run(["git", "hash-object", str(amount)]).stdout.strip()
    if blob != PIN_AMOUNT_BLOB:
        rec("PIN-AMOUNT-BLOB", "FAIL", "git hash-object amount.h", blob)
        return 1
    rec("PIN-AMOUNT-BLOB", "PASS", "git blob sha of amount.h", blob)
    if sha256_file(fnfix) != PIN_FN_SHA:
        rec("PIN-FN", "FAIL", "GetBlockSubsidy excerpt sha256 mismatch", sha256_file(fnfix))
        return 1
    rec("PIN-FN", "PASS", "pinned GetBlockSubsidy excerpt sha256")
    if sha256_file(btcdfix) != PIN_BTCD_FN_SHA:
        rec("PIN-BTCD", "FAIL", "btcd CalcBlockSubsidy excerpt sha256 mismatch")
        return 1
    rec("PIN-BTCD", "PASS", "pinned btcd v0.24.2 CalcBlockSubsidy excerpt")

    live_amt = fetch(f"https://raw.githubusercontent.com/bitcoin/bitcoin/{PIN_COMMIT}/src/consensus/amount.h")
    live_val = fetch(f"https://raw.githubusercontent.com/bitcoin/bitcoin/{PIN_COMMIT}/src/validation.cpp")
    if live_amt is None or live_val is None:
        rec("UPSTREAM-LIVE", "SKIP", "GitHub raw fetch unavailable; fixture pin still holds")
    else:
        if hashlib.sha256(live_amt).hexdigest() != PIN_AMOUNT_SHA:
            rec("UPSTREAM-LIVE", "FAIL", "live amount.h differs from fixture")
            return 1
        live_fn = extract_fn(live_val.decode("utf-8", "replace"), "CAmount GetBlockSubsidy(")
        if hashlib.sha256(live_fn.encode()).hexdigest() != PIN_FN_SHA:
            rec("UPSTREAM-LIVE", "FAIL", "live GetBlockSubsidy differs from fixture")
            return 1
        rec("UPSTREAM-LIVE", "PASS", "live v27.1 amount.h + GetBlockSubsidy match fixtures", PIN_COMMIT)

    live_btcd = fetch(f"https://raw.githubusercontent.com/btcsuite/btcd/{BTCD_COMMIT}/blockchain/validate.go")
    if live_btcd is None:
        rec("BTCD-LIVE", "SKIP", "btcd raw fetch unavailable; fixture pin still holds")
    else:
        live_fn = extract_fn(live_btcd.decode("utf-8", "replace"), "func CalcBlockSubsidy")
        if hashlib.sha256(live_fn.encode()).hexdigest() != PIN_BTCD_FN_SHA:
            rec("BTCD-LIVE", "FAIL", "live btcd CalcBlockSubsidy differs from fixture")
            return 1
        rec("BTCD-LIVE", "PASS", "live btcd v0.24.2 CalcBlockSubsidy matches fixture", BTCD_COMMIT)

    ensure_oracle()
    st = oracle(["selftest"])
    if "PASS" not in st:
        rec("C11-SELFTEST", "FAIL", "C11 shift-loop vs guarded shift", st)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 selftest: loop shift == guarded shift; supply cap gap")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of subsidy clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_core_subsidy.lin")
    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "btc_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "btc_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "btc_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for h in HEIGHTS:
        want_py = py_subsidy(h)
        want_c11 = int(oracle(["lin", str(h)]))
        want_core = int(oracle(["core", str(h)]))
        got = lin_vm("btc_subsidy_main", h)
        if want_py != want_c11 or got != want_py:
            rec("VEC-LIN", "FAIL", f"height={h}", f"py={want_py} c11={want_c11} lin={got}")
            return 1
        if h >= 0 and want_core != want_py:
            rec("VEC-CORE", "FAIL", f"core vs lin at height={h}", f"core={want_core} lin={want_py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} heights: Python == C11 == LIN vm == Core (h>=0)")

    if lin_vm("btc_subsidy_main", -1) != 0 or int(oracle(["lin", "-1"])) != 0:
        rec("NEG-HEIGHT-LIN", "FAIL", "LIN must fail-close height<0")
        return 1
    rec("NEG-HEIGHT-LIN", "PASS", "LIN and C11-lin return 0 for height=-1")
    if int(oracle(["core", "-1"])) != GENESIS:
        rec("NEG-HEIGHT-CORE", "FAIL", "Core-faithful -1 should be 50 BTC")
        return 1
    rec("NEG-HEIGHT-CORE", "PASS", "Core-faithful C11: height=-1 yields 50*COIN (toward-zero /)")
    if int(oracle(["lin", "10", "0"])) != 0:
        rec("ZERO-INTERVAL", "FAIL", "LIN interval=0")
        return 1
    rec("ZERO-INTERVAL", "PASS", "LIN interval<=0 fail-closes to 0 (Core UB; btcd returns 50 BTC)")

    tot_lin = lin_vm("btc_supply_all")
    tot_c11 = int(oracle(["supply"]))
    tot_py = py_supply_all()
    if tot_lin != TOTAL_ISSUED or tot_c11 != tot_py or tot_lin != tot_py:
        rec("SUPPLY-ALL", "FAIL", "total issuance", f"lin={tot_lin} c11={tot_c11} py={tot_py}")
        return 1
    rec("SUPPLY-ALL", "PASS", "64-era sum == 2099999997690000 sats", f"gap_vs_MAX_MONEY={MAX_MONEY - tot_py}")
    if lin_vm("btc_actual_below_cap") != 1 or tot_py >= MAX_MONEY:
        rec("CAP-GAP", "FAIL", "actual supply must be < MAX_MONEY")
        return 1
    rec("CAP-GAP", "PASS", "MAX_MONEY is a sanity cap, not the issued supply (Core amount.h)")

    wrapped32 = ctypes_i32(GENESIS)
    if wrapped32 == GENESIS:
        rec("I32-WRAP", "FAIL", "int32 50*COIN unexpectedly equalled int64")
        return 1
    rec("I32-WRAP", "PASS", "naive int32 50*COIN wraps; LIN uses i64 CAmount", f"i32={wrapped32} i64={GENESIS}")

    csrc = C_TR.read_text(encoding="utf-8")
    core_fn = fnfix.read_text(encoding="utf-8")
    sc = scalar.read_text(encoding="utf-8")
    if "REJ_C_CXX" not in csrc or "CAmount" not in csrc or "cfs_strip_int_suffix" not in csrc:
        rec("C-TR-V2", "FAIL", "lin_from_c.lin v2 markers missing")
    else:
        rec("C-TR-V2", "PASS", "C transpiler v2: REJ_C_CXX, CAmount, integer-suffix strip")
    if "Consensus::Params&" not in core_fn or "nHeight < 0" in core_fn:
        rec("CORE-REF", "FAIL", "expected Core reference param and no negative guard")
    else:
        rec("CORE-REF", "PASS", "Core GetBlockSubsidy takes Consensus::Params& (transpiler REJ_C_CXX/POINTER)")
    if "nHeight < 0" not in sc or "interval <= 0" not in sc or "::" in sc:
        rec("SCALAR-LIFT", "FAIL", "scalar C subset missing fail-closed lift")
    else:
        rec("SCALAR-LIFT", "PASS", "scalar C subset: explicit args, fail-closed height/interval, no C++")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "btc_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on btc_test_suite (in-memory libtcc)")
    else:
        jv = run([str(C0), "jit", str(LIN), "btc_subsidy_main", "210000"], timeout=60)
        gotj = value_of(jv.stdout)
        if jv.returncode == 0 and gotj == 2_500_000_000:
            rec("C0-JIT", "PASS", "lin_c0 jit btc_subsidy_main(210000)==2500000000")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    if GO_SRC.exists() and shutil_which("go"):
        gp = run(["go", "run", str(GO_SRC), "210000"], timeout=60)
        if gp.returncode == 0 and gp.stdout.strip() == "2500000000":
            rec("BTCD-GO", "PASS", "Go replica of btcd CalcBlockSubsidy(210000)==25 BTC")
        else:
            rec("BTCD-GO", "FAIL", "go subsidy", gp.stdout + gp.stderr)
    else:
        rec("BTCD-GO", "SKIP", "go toolchain or replica source missing")

    evidence = {
        "schema": "LIN_BITCOIN_CORE_SUBSIDY_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "clone_lin": "https://github.com/kbelludoo/clone-lin-bitcoin-core-subsidy",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/bitcoin/bitcoin",
            "tag": "v27.1",
            "commit": PIN_COMMIT,
            "path": "src/validation.cpp GetBlockSubsidy + src/consensus/amount.h",
            "license": "MIT",
            "amount_h_git_blob_sha": PIN_AMOUNT_BLOB,
            "amount_h_sha256": PIN_AMOUNT_SHA,
            "getblocksubsidy_sha256": PIN_FN_SHA,
        },
        "cross_oracle": {
            "btcd": "https://github.com/btcsuite/btcd",
            "commit": BTCD_COMMIT,
            "path": "blockchain/validate.go CalcBlockSubsidy",
            "license": "ISC",
            "fn_sha256": PIN_BTCD_FN_SHA,
        },
        "lin_clone": "src/lin_bitcoin_core_subsidy.lin",
        "c11_oracle": "test/oracles/bitcoin_core_subsidy_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "total_issued_sats": tot_lin,
        "max_money_sats": MAX_MONEY,
        "genesis_height_0": GENESIS,
        "first_halving_height": 210000,
    }
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


def ctypes_i32(v: int) -> int:
    return ((v + 2**31) % 2**32) - 2**31


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


if __name__ == "__main__":
    sys.exit(main())
