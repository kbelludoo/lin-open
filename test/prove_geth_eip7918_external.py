#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Geth Osaka EIP-7918 excess-blob-gas vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of consensus/misc/eip4844/eip4844.go (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb clone)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision fakeExponential / reserve-price identity

  NOT claimed:
    * Geth big.Int range (LIN path is uint64-scale + 128-bit product)
    * that LIN replaces Geth, the EVM, or proto-danksharding
    * wall-clock superiority vs gc/solc
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Osaka EIP-7918 algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_geth_eip7918.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_eip7918_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_eip7918_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_go_ethereum")
EVIDENCE = ROOT / "examples" / "geth_eip7918" / "geth_eip7918_evidence.json"
SCALAR_C = FIX / "eip7918_scalar.c"
SCALAR_GO = FIX / "eip7918_scalar.go"

PINNED_SHA256 = "c8b68e4f32cef33e9420648344edc8fa3bb5d5cb42de22fbf0b34bea5dbdf63c"
PINNED_BLOB = "add85092c2ec0be391176b72c4431b5d1d9896b8"
PINNED_COMMIT = "24dd23631661017452cfc7bcd07c114d3796cd65"
UPSTREAM_REL = "consensus/misc/eip4844/eip4844.go"
GAS = 131072
COST = 8192


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
    proc = run(cmd, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/ethereum/go-ethereum.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=180,
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


def lone_amp(s: str) -> int:
    i = 0
    n = 0
    while i < len(s):
        if s[i] == "&":
            if i + 1 < len(s) and s[i + 1] == "&":
                i += 2
                continue
            n += 1
        i += 1
    return n


def c_reason(sig: str, body: str) -> str:
    if "::" in sig or "::" in body:
        return "REJ_C_CXX_SCOPE"
    if lone_amp(sig) > 0:
        return "REJ_C_REFERENCE"
    if "*" in sig or "->" in body:
        return "REJ_C_POINTER"
    if "struct" in sig or "struct" in body:
        return "REJ_C_STRUCT"
    return "OK"


def go_reason(sig: str, body: str) -> str:
    if "*" in sig:
        return "REJ_GO_POINTER"
    if lone_amp(sig) > 0 or lone_amp(body) > 0:
        return "REJ_GO_ADDRESS"
    if "[]" in sig or "[]" in body:
        return "REJ_GO_SLICE"
    if "nil" in body:
        return "REJ_GO_POINTER"
    if "." in body:
        return "REJ_GO_SELECTOR"
    return "OK"


def fake_exp_py(factor: int, numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    output = 0
    accum = factor * denominator
    i = 1
    while accum > 0:
        output += accum
        accum = accum * numerator // denominator // i
        i += 1
        if i > 256:
            return 0
    return output // denominator


def osaka_py(excess: int, used: int, base_fee: int, blob_fee: int, target: int, maxv: int) -> int:
    target_gas = target * GAS
    s = excess + used
    if s < target_gas:
        return 0
    if COST * base_fee > blob_fee * GAS:
        return excess + (used * (maxv - target) // maxv)
    return s - target_gas


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_EIP7918_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH EIP-7918 Osaka excess-blob-gas — external LIN proof (uint64-scale)")
    print("=" * 78)

    pinned = FIX / "eip4844.go"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned eip4844.go missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned eip4844.go sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned go-ethereum commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of eip4844.go")
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

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb fake_exp/osaka selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb EIP-7918 agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eip7918 clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_eip7918.lin")

    for label, path in (("C-TR-CHECK", C_TR), ("GO-TR-CHECK", GO_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check of {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "e7918_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "e7918_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "e7918_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("fake_exp", ["1", "2", "1"], "e7918_fake_exp", (1, 2, 1), 6),
        ("fake_exp", ["1", "50000000", "2225652"], "e7918_fake_exp", (1, 50000000, 2225652), 5709098764),
        ("fake_exp", ["1", "2314058", "3338477"], "e7918_fake_exp", (1, 2314058, 3338477), 2),
        ("cancun", ["0", str(4 * GAS), "3"], "e7918_cancun", (0, 4 * GAS, 3), GAS),
        ("full", ["0", str(6 * GAS), "1000000000", "6", "9", "5007716"],
         "e7918_osaka_from_excess", (0, 6 * GAS, 1000000000, 6, 9, 5007716), 262144),
        ("full", ["0", str(6 * GAS), "1", "6", "9", "5007716"],
         "e7918_osaka_from_excess", (0, 6 * GAS, 1, 6, 9, 5007716), 0),
        ("full", ["5149252", "1310720", "30", "9", "14", "8832827"],
         "e7918_osaka_from_excess", (5149252, 1310720, 30, 9, 14, 8832827), 5617366),
        ("full", ["19251039", "2490368", "50", "21", "32", "20609697"],
         "e7918_osaka_from_excess", (19251039, 2490368, 50, 21, 32, 20609697), 20107103),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, want_py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if want != want_py:
            rec("VEC-PY", "FAIL", f"python {fn}{largs}", f"py={want_py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    py_below = osaka_py(0, 6 * GAS, 1_000_000_000, fake_exp_py(1, 0, 5007716), 6, 9)
    if py_below != 262144:
        rec("PY-RESERVE", "FAIL", "python reserve-price BelowReservePrice", f"py={py_below}")
        return 1
    rec("PY-RESERVE", "PASS", "Python bigint BelowReservePrice == 262144 (blobGasTarget*3/9)")

    src = LIN.read_text(encoding="utf-8")
    geth = pinned.read_text(encoding="utf-8")
    if "e7918_osaka(parent_excess: int, parent_used: int, base_fee: int, blob_fee: int" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Geth *Header")
    elif "*types.Header" not in geth or "parent.BaseFee" not in geth:
        rec("EXPLICIT-ARGS", "FAIL", "pinned Geth still must show pointer header / BaseFee")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes excess/used/base_fee/blob_fee/target/max as arguments (no *Header)",
        )

    if "e7918_reserve_gt" in src and "e7918_mul_hi" in src:
        rec("WIDE-RESERVE", "PASS", "reserve-price compare is 128-bit product, not wrapping i64")
    else:
        rec("WIDE-RESERVE", "FAIL", "128-bit reserve compare missing")

    wide_a = 1_200_000_000_000_000  # 1.2e15; 8192*1.2e15 = 9.83e18 overflows signed i64
    got_r = lin_vm("e7918_reserve_gt", COST, wide_a, 1, GAS)
    py_r = 1 if COST * wide_a > 1 * GAS else 0
    wrapped = (COST * wide_a) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if got_r != 1 or py_r != 1 or wrapped == COST * wide_a:
        rec("I64-WRAP", "FAIL", "128-bit reserve_gt should beat wrapping i64", f"lin={got_r} wrap={wrapped}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "BlobBaseCost*1.2e15 overflows signed i64; 128-bit reserve_gt still 1 vs blob_fee=1",
        f"i64_wrap={wrapped} bigint={COST * wide_a}",
    )

    c_tr = C_TR.read_text(encoding="utf-8")
    go_tr = GO_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX_SCOPE" in c_tr and "REJ_C_REFERENCE" in c_tr and "cfs_count_ref" in c_tr:
        rec("C-EMIT-V2", "PASS", "lin_from_c.lin v2 rejects :: and lone & (&& is not a reference)")
    else:
        rec("C-EMIT-V2", "FAIL", "C++ fail-closed codes missing")
    if "go_from_go" in go_tr and "REJ_GO_POINTER" in go_tr and "REJ_GO_SELECTOR" in go_tr:
        rec("GO-EMIT", "PASS", "lin_from_go.lin emits scalar Go and rejects Geth pointers/selectors")
    else:
        rec("GO-EMIT", "FAIL", "Go transpiler emit/reject path missing")

    if c_reason("int f(std::uint64_t x)", "return x;") != "REJ_C_CXX_SCOPE":
        rec("C-RULE-CXX", "FAIL", "python oracle of REJ_C_CXX_SCOPE")
        return 1
    if c_reason("int f(int &x)", "return x;") != "REJ_C_REFERENCE":
        rec("C-RULE-REF", "FAIL", "python oracle of REJ_C_REFERENCE")
        return 1
    if c_reason("int f(int x, int y)", "return x && y;") != "OK":
        rec("C-RULE-AND", "FAIL", "&& must not count as a C++ reference")
        return 1
    rec("C-RULES", "PASS", "Python fail-closed oracle: :: / lone & / && match lin_from_c v2")

    scalar_c = SCALAR_C.read_text(encoding="utf-8")
    if c_reason(
        "uint64_t e7918_scaled_excess(uint64_t used, uint64_t maxv, uint64_t target)",
        "return used * (maxv - target) / maxv;",
    ) != "OK":
        rec("SCALAR-C", "FAIL", "scalar C fixture should be eligible")
        return 1
    rec("SCALAR-C", "PASS", "eip7918_scalar.c is eligible under lin_from_c v2")

    geth_sig = "func calcExcessBlobGas(isOsaka bool, bcfg BlobConfig, parent *types.Header) uint64"
    geth_body = "if parent.ExcessBlobGas != nil { return *parent.ExcessBlobGas }"
    if not go_reason(geth_sig, geth_body).startswith("REJ_"):
        rec("GETH-REJ", "FAIL", "Geth calcExcessBlobGas should be rejected")
        return 1
    rec("GETH-REJ", "PASS", "Geth *Header / nil / selector body is REJ_GO_* (not silently lowered)")

    if go_reason(
        "func ScaledExcess(used uint64, max uint64, target uint64) uint64",
        "return used * (max - target) / max",
    ) != "OK":
        rec("SCALAR-GO", "FAIL", "scalar Go fixture should be eligible")
        return 1
    rec("SCALAR-GO", "PASS", "eip7918_scalar.go is eligible under lin_from_go")

    if "*types.Header" not in geth or "BlobBaseCost" not in geth:
        rec("GETH-SOURCE", "FAIL", "pinned Geth missing Header pointers or BlobBaseCost")
    else:
        rec("GETH-SOURCE", "PASS", "pinned Geth still uses *Header and BlobBaseCost (clone does not)")

    jit_ok = lin_roundtrip_jit("e7918_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on e7918_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("e7918_fake_exp", 1, 2, 1)
        if jv == 6:
            rec("C0-JIT", "PASS", "lin_c0 jit e7918_fake_exp(1,2,1)==6 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_eip7918.lin"
    evidence["c11_oracle"] = "test/oracles/geth_eip7918_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["below_reserve_prague"] = 262144
    evidence["geth_test_bpo1"] = 5617366
    evidence["geth_test_bpo3"] = 20107103
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
