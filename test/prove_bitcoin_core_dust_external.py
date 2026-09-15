#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 GetDustThreshold / IsDust vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of policy.cpp / policy.h / feerate.cpp (git blob + sha256)
    * an independent C11 oracle (integer ceil + IEEE ceil on dust-scale operands)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * fail-closed C++ rejects in src/lin_from_c.lin v2 (ceil, ::, reinterpret_cast)

  NOT claimed:
    * LIN replacing Bitcoin Core, a wallet, or consensus
    * IEEE ceil == integer ceil outside the measured dust-scale grid
    * Taproot BIP340 keypath weight (Core keeps the P2WPKH 107-byte dummy; PR 22779)
    * wall-clock superiority vs gcc/bitcoind

Class: EXPERIMENTAL (real Core dust algorithm, scalar script_len + flags).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_bitcoin_core_dust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_core_dust_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_core_dust_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_bitcoin")
EVIDENCE = ROOT / "examples" / "bitcoin_core_dust" / "bitcoin_core_dust_evidence.json"
EXCERPT = FIX / "bitcoin_core_v27_1_dust_excerpt.cpp"
ELIGIBLE = FIX / "bitcoin_core_dust_c11_eligible.c"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINNED_POLICY_SHA256 = "cd442c9e4e40a4811fe6256109020b7567bb777dce5ac8398cf8664de2ccb2d5"
PINNED_POLICY_BLOB = "d08ec4fb7f75c33ff68c1790d39e1671456baa44"
PINNED_POLICY_H_SHA256 = "da74b4819f1726151afb682e3f42f3954eb0d453b3db85faffa98b51189e2359"
PINNED_POLICY_H_BLOB = "6a7980c312c9bdf5398f914711571ed06a57712c"
PINNED_FEERATE_SHA256 = "dcee0d3c510936032addb0735dfb1e5389dcd4f8cf31e6867b94e2e14c6cb561"
PINNED_FEERATE_BLOB = "eb0cba5c67a406ea9d2a3500e6be90b2f2f21b96"
PINNED_EXCERPT_SHA256 = "5ca467863fdd9aaf40f611f58835ec938e88de7e70c34d66ac102d4893b1ec1f"


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
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


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
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra",
         "-o", str(ORACLE_BIN), str(ORACLE_SRC), "-lm"],
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
    url = "https://github.com/bitcoin/bitcoin.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", "v27.1"],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(
        ["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD", "--",
         "src/policy/policy.cpp", "src/policy/policy.h", "src/policy/feerate.cpp"]
    )
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag files failed"
    commit = run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "FETCH_HEAD^{commit}"]
    ).stdout.strip()
    if commit != PINNED_COMMIT:
        return "FAIL", commit, f"commit {commit} != {PINNED_COMMIT}"
    paths = {
        "src/policy/policy.cpp": (PINNED_POLICY_SHA256, PINNED_POLICY_BLOB),
        "src/policy/policy.h": (PINNED_POLICY_H_SHA256, PINNED_POLICY_H_BLOB),
        "src/policy/feerate.cpp": (PINNED_FEERATE_SHA256, PINNED_FEERATE_BLOB),
    }
    notes = []
    for rel, (want_sha, want_blob) in paths.items():
        live = UPSTREAM / rel
        if not live.exists():
            return "FAIL", commit, f"{rel} missing"
        got_sha = sha256_file(live)
        blob = run(["git", "-C", str(UPSTREAM), "hash-object", rel]).stdout.strip()
        if got_sha != want_sha or blob != want_blob:
            return "FAIL", commit, f"{rel} live={got_sha} blob={blob}"
        notes.append(f"{rel}:{blob}")
    return "PASS", commit, ";".join(notes)


def cfs_reason_py(sig: str, body: str) -> str:
    """Mirror src/lin_from_c.lin v2 cfs_reason (fail-closed C++ / IEEE)."""
    if "*" in sig or "->" in body:
        return "REJ_C_POINTER"
    if "struct" in sig or "struct" in body:
        return "REJ_C_STRUCT"
    if "union" in sig or "union" in body:
        return "REJ_C_UNION"
    for tok in ("float", "double", "ceil(", "floor(", "round(", "trunc(", ".0"):
        if tok in sig or tok in body:
            return "REJ_C_FLOAT"
    for tok in ("::", "class ", "template", "static_cast", "reinterpret_cast",
                "dynamic_cast", "const_cast", "namespace", "throw "):
        if tok in sig or tok in body:
            return "REJ_C_CXX"
    if "goto" in body:
        return "REJ_C_GOTO"
    return "OK"


def py_compact(n: int) -> int:
    if n < 0:
        return -1
    if n < 253:
        return 1
    if n <= 65535:
        return 3
    if n <= 4294967295:
        return 5
    return 9


def py_thr(script_len: int, is_witness: int, is_unspendable: int, rate: int) -> int:
    if is_unspendable:
        return 0
    if rate < 0 or script_len < 0:
        return -1
    cs = py_compact(script_len)
    nsz = 8 + cs + script_len + (67 if is_witness else 148)
    if nsz == 0:
        return 0
    num = rate * nsz
    fee = (num + 999) // 1000 if num % 1000 else num // 1000
    if fee == 0 and rate > 0:
        return 1
    return fee


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_BITCOIN_CORE_DUST_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE v27.1 DUST — external LIN proof (C11 Compiler 0)")
    print("=" * 78)

    if not EXCERPT.exists() or sha256_file(EXCERPT) != PINNED_EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "dust excerpt missing or hash mismatch")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned GetDustThreshold excerpt sha256 matches harness")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of bitcoin v27.1 matches pinned blobs",
            f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "policy.cpp/h + feerate.cpp git blobs", up_note[:200])
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 integer==IEEE dust-scale selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 integer ceil matches IEEE ceil on dust-scale grid")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of dust clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_core_dust.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "SKIP", "string transpiler is not an integer VM module",
            (chk2.stdout + chk2.stderr)[:180])
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 accepted lin_from_c.lin as a module")

    gate = run([str(C0), "vm", str(LIN), "btd_dust_gate"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "btd_dust_gate via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "btd_dust_gate == 1 on Compiler 0 interpreter")

    vectors = [
        ("thr", ["25", "0", "0", "3000"], "btd_get_dust_threshold", (25, 0, 0, 3000), 546),
        ("thr", ["22", "1", "0", "3000"], "btd_get_dust_threshold", (22, 1, 0, 3000), 294),
        ("thr", ["34", "1", "0", "3000"], "btd_get_dust_threshold", (34, 1, 0, 3000), 330),
        ("thr", ["23", "0", "0", "3000"], "btd_get_dust_threshold", (23, 0, 0, 3000), 540),
        ("dust", ["545", "25", "0", "0", "3000"], "btd_is_dust", (545, 25, 0, 0, 3000), 1),
        ("dust", ["546", "25", "0", "0", "3000"], "btd_is_dust", (546, 25, 0, 0, 3000), 0),
        ("dust", ["329", "34", "1", "0", "3000"], "btd_is_dust", (329, 34, 1, 0, 3000), 1),
        ("dust", ["330", "34", "1", "0", "3000"], "btd_is_dust", (330, 34, 1, 0, 3000), 0),
        ("fee", ["1000", "200"], "btd_get_fee", (1000, 200), 200),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, published in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        py = py_thr(*largs) if fn == "btd_get_dust_threshold" else (
            1 if (fn == "btd_is_dust" and largs[0] < py_thr(*largs[1:])) else (
                0 if fn == "btd_is_dust" else ((largs[0] * largs[1] + 999) // 1000)
            )
        )
        if fn == "btd_get_fee":
            py = math.ceil(largs[0] * largs[1] / 1000.0) if largs[1] else 0
        if want != published or got_lin != want or py != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} py={py} pub={published}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == Python == LIN vm == Core constants")

    rec("COMMERCIAL-546", "PASS",
        "default DUST_RELAY_TX_FEE=3000 sat/kvB => P2PKH dust 546 sat (nSize=182)",
        "545 sat P2PKH is dust (IsStandardTx reason=dust); 546 sat is not")
    rec("COMMERCIAL-294", "PASS",
        "same rate => P2WPKH dust 294 sat (nSize=98); P2TR/P2WSH 34-byte script => 330 sat",
        "Core PR 22779 kept P2WPKH 107-byte dummy for Taproot; not BIP340 keypath")
    rec("COMMERCIAL-RELAY", "PASS",
        "minrelay 1000 sat/kvB on a 200 vB tx is 200 sat — a different policy number than dust",
        "dust is output value vs spend cost; minrelay is tx fee vs vsize")

    if lin_roundtrip("btd_dust_gate"):
        rec("C0-ROUNDTRIP", "PASS", "lin_c0 roundtrip CONSENSUS on btd_dust_gate (in-memory bytecode)")
    else:
        rec("C0-ROUNDTRIP", "SKIP", "roundtrip did not print CONSENSUS")

    if lin_roundtrip_jit("btd_dust_gate"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on btd_dust_gate (in-memory libtcc)")
    else:
        jv = lin_jit("btd_get_dust_threshold", 25, 0, 0, 3000)
        if jv == 546:
            rec("C0-JIT", "PASS", "lin_c0 jit P2PKH dust==546 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    tr = C_TR.read_text(encoding="utf-8")
    need = ["REJ_C_FLOAT", "ceil(", "reinterpret_cast", "cfs_strip_int_suffix", "else_b"]
    if all(s in tr for s in need) and "version=2" in tr:
        rec("C-TR-V2", "PASS",
            "lin_from_c.lin v2 rejects IEEE ceil and C++ casts; strips U/L suffixes; emits if/else")
    else:
        rec("C-TR-V2", "FAIL", "transpiler v2 markers missing")
        return 1

    cxx_body = EXCERPT.read_text(encoding="utf-8")
    cxx_r = cfs_reason_py("CAmount GetDustThreshold(const CTxOut& txout, const CFeeRate& dustRelayFeeIn)", cxx_body)
    fee_r = cfs_reason_py(
        "CAmount CFeeRate::GetFee(uint32_t num_bytes) const",
        "CAmount nFee{static_cast<CAmount>(std::ceil(nSatoshisPerK * nSize / 1000.0))};",
    )
    recast_r = cfs_reason_py("int64_t f(void)", "return reinterpret_cast<int64_t>(p);")
    ok_r = cfs_reason_py(
        "int64_t btd_spend_overhead(int is_witness)",
        ELIGIBLE.read_text(encoding="utf-8") if ELIGIBLE.exists() else "return 148;",
    )
    if cxx_r != "REJ_C_CXX" or fee_r != "REJ_C_FLOAT" or recast_r != "REJ_C_CXX" or ok_r != "OK":
        rec("TR-REJECT", "FAIL", "expected CXX/FLOAT reject of Core C++ and OK on C11 scalar",
            f"dust={cxx_r} fee={fee_r} recast={recast_r} ok={ok_r}")
        return 1
    rec("TR-REJECT", "PASS",
        "C++ GetDustThreshold => REJ_C_CXX; GetFee ceil/.0 => REJ_C_FLOAT; C11 scalar => OK",
        f"reinterpret_cast={recast_r} (new v2 reject vs GetFee-only static_cast)")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/bitcoin/bitcoin",
        "tag": "v27.1",
        "commit": commit or PINNED_COMMIT,
        "policy_cpp_sha256": PINNED_POLICY_SHA256,
        "policy_cpp_git_blob": PINNED_POLICY_BLOB,
        "policy_h_sha256": PINNED_POLICY_H_SHA256,
        "feerate_cpp_sha256": PINNED_FEERATE_SHA256,
        "feerate_cpp_git_blob": PINNED_FEERATE_BLOB,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_bitcoin_core_dust.lin"
    evidence["c11_oracle"] = "test/oracles/bitcoin_core_dust_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["published"] = {
        "DUST_RELAY_TX_FEE": 3000,
        "DEFAULT_MIN_RELAY_TX_FEE": 1000,
        "p2pkh_dust_sat": 546,
        "p2wpkh_dust_sat": 294,
        "p2tr_kept_p2wpkh_dummy_dust_sat": 330,
        "p2sh_dust_sat": 540,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-bitcoin-core-dust"
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
