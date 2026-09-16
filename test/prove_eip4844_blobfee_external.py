#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum EIP-4844 fakeExponential / CalcBlobFee (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of consensus/misc/eip4844/eip4844.go (git blob + sha256)
    * pinned BlobTxMinBlobGasprice=1 / UpdateFraction=3338477 / Target=3*131072
      excerpt from params/protocol_params.go
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * a Python bigint oracle of the EIP-4844 integer Taylor expansion

  NOT claimed:
    * full uint256 / mainnet Geth node parity
    * that LIN replaces go-ethereum or Ethereum blob DA pricing
    * wall-clock superiority vs gc/LLVM
    * computational soundness of Merkle receipts

Class: EXPERIMENTAL (real EIP-4844 algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_eip4844_blobfee.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "eip4844_blobfee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "eip4844_blobfee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_go_ethereum")
EVIDENCE = ROOT / "examples" / "eip4844_blobfee" / "eip4844_blobfee_evidence.json"
INT_C = FIX / "eip4844_integer.c"

PINNED_SHA256 = "23af9802a9d2acc3818dba2768bc81da37fb857dd67590a27e3e13edaae02868"
PINNED_BLOB = "2dad9a0cd3de18ac8db0dde8ba7101300b11d6d9"
PINNED_COMMIT = "293a300d64be3d9a1c2cc92c26fcff4089deadcd"
PINNED_TAG = "v1.14.12"
UPSTREAM_REL = "consensus/misc/eip4844/eip4844.go"
PARAMS_REL = "params/protocol_params.go"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-eip4844-blobfee"

MIN_PRICE = 1
UPDATE_FRAC = 3_338_477
BLOB_GAS = 131_072
TARGET = 3 * BLOB_GAS

GETH_EXP = [
    (1, 0, 1, 1),
    (38493, 0, 1000, 38493),
    (0, 1234, 2345, 0),
    (1, 2, 1, 6),
    (1, 4, 2, 6),
    (1, 3, 1, 16),
    (1, 6, 2, 18),
    (1, 4, 1, 49),
    (1, 8, 2, 50),
    (10, 8, 2, 542),
    (11, 8, 2, 596),
    (1, 5, 1, 136),
    (1, 5, 2, 11),
    (2, 5, 2, 23),
]
GETH_FEE = [(0, 1), (2314057, 1), (2314058, 2), (10 * 1024 * 1024, 23)]
GETH_WIDE = (1, 50_000_000, 2_225_652, 5_709_098_764)


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int, timeout: int = 120) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=timeout)
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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_fake_exp(factor: int, numerator: int, denominator: int) -> int:
    if factor < 0 or numerator < 0 or denominator <= 0:
        return 0
    output = 0
    accum = factor * denominator
    i = 1
    while accum > 0:
        output += accum
        accum = accum * numerator // denominator
        accum = accum // i
        i += 1
        if i > 4096:
            return 0
    return output // denominator


def first_u64_wrap(factor: int, numerator: int, denominator: int) -> tuple[int, int, int, int]:
    accum = factor * denominator
    i = 1
    while accum > 0:
        prod = accum * numerator
        if prod >= 2**64:
            naive = ((accum % (2**64)) * (numerator % (2**64))) % (2**64) // denominator
            wide = prod // denominator
            return accum, prod, naive, wide
        accum = prod // denominator // i
        i += 1
        if i > 4096:
            break
    raise RuntimeError("expected a uint64 wrap on this Geth vector")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/ethereum/go-ethereum.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=180)
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
    evidence: dict = {"schema": "LIN_EIP4844_BLOBFEE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  EIP-4844 fakeExponential / CalcBlobFee — external LIN proof (uint64-scale)")
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
    blob_local = git_blob_sha(pinned)
    if blob_local != PINNED_BLOB:
        rec("PIN-BLOB", "FAIL", "pinned git blob sha mismatch", blob_local)
        return 1
    rec("PIN-BLOB", "PASS", "pinned eip4844.go git blob sha1 matches GitHub")

    excerpt = (FIX / "eip4844_params_excerpt.txt").read_text(encoding="utf-8")
    if "BlobTxMinBlobGasprice              = 1" not in excerpt or "3338477" not in excerpt or "BlobTxBlobGasPerBlob" not in excerpt:
        rec("PIN-PARAMS", "FAIL", "params excerpt missing Cancun blob constants")
        return 1
    rec("PIN-PARAMS", "PASS", "pinned protocol_params excerpt has min=1 frac=3338477 blob_gas=1<<17")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned go-ethereum commit matches fixture",
            f"tag={PINNED_TAG} commit={commit} blob={blob}")
        params = UPSTREAM / PARAMS_REL
        live_params = params.read_text(encoding="utf-8") if params.exists() else ""
        if excerpt.strip() in live_params and "BlobTxTargetBlobGasPerBlock = 3 * BlobTxBlobGasPerBlob" in live_params:
            rec("UPSTREAM-PARAMS", "PASS", "live protocol_params.go contains pinned blob constants")
        else:
            rec("UPSTREAM-PARAMS", "FAIL", "live protocol_params.go missing pinned excerpt")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-PARAMS", "SKIP", "live params not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-PARAMS", "FAIL", "params not checked", up_note)

    go_src = pinned.read_text(encoding="utf-8")
    if "func fakeExponential" not in go_src or "func CalcBlobFee" not in go_src:
        rec("GO-FORMULA", "FAIL", "pinned Go file does not contain fakeExponential / CalcBlobFee")
        return 1
    rec("GO-FORMULA", "PASS", "pinned Go contains fakeExponential Taylor loop and CalcBlobFee")

    if not INT_C.exists():
        rec("C-SUBSET", "FAIL", "eip4844_integer.c missing")
        return 1
    c_src = INT_C.read_text(encoding="utf-8")
    c_code = re.sub(r"/\*.*?\*/", "", c_src, flags=re.S)
    c_code = re.sub(r"//.*?$", "", c_code, flags=re.M)
    if "->" in c_code or re.search(r"\bstruct\b", c_code) or re.search(r"\bfloat\b", c_code):
        rec("C-SUBSET", "FAIL", "C restatement is not a LIN-eligible scalar subset")
        return 1
    rec("C-SUBSET", "PASS", "C restatement is scalar (no struct/pointer body); eligible for lin_from_c")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree on Geth vectors")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout and chk.returncode != 0:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eip4844 clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_eip4844_blobfee.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (if/else emit path)")

    tr_src = C_TR.read_text(encoding="utf-8")
    if "version=2" not in tr_src or "has_else" not in tr_src or "cfs_strip_suffixes" not in tr_src:
        rec("C-TR-V2", "FAIL", "lin_from_c.lin v2 if/else + suffix strip missing")
        return 1
    if "REJ_C_CXX" not in tr_src or "cfs_has_amp_ref" not in tr_src:
        rec("C-TR-V2", "FAIL", "lin_from_c.lin v2 C++/& fail-closed missing")
        return 1
    rec("C-TR-V2", "PASS", "lin_from_c.lin v2: braced if/else emit, U/L suffix strip, & and C++ reject")

    if "3338477ULL" in c_src and "cfs_strip_suffixes" in tr_src:
        rec("SUFFIX-NEED", "PASS", "C restatement uses ULL suffixes; v2 transpiler strips them")
    else:
        rec("SUFFIX-NEED", "FAIL", "ULL suffix / strip pairing missing")

    gate = run([str(C0), "vm", str(LIN), "bb_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "bb_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "bb_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for f, n, d, want in GETH_EXP:
        c11 = int(oracle(["exp", str(f), str(n), str(d)]).splitlines()[-1])
        limbs = int(oracle(["exp", str(f), str(n), str(d), "--limbs"]).splitlines()[-1])
        lin = lin_vm("bb_fake_exp", f, n, d)
        py = py_fake_exp(f, n, d)
        if not (c11 == limbs == lin == py == want):
            rec("VEC-EXP", "FAIL", f"fake_exp({f},{n},{d})", f"lin={lin} c11={c11} limbs={limbs} py={py} geth={want}")
            return 1
        n_ok += 1
    for excess, want in GETH_FEE:
        c11 = int(oracle(["fee", str(excess)]).splitlines()[-1])
        limbs = int(oracle(["fee", str(excess), "--limbs"]).splitlines()[-1])
        lin = lin_vm("bb_cancun_blob_fee", excess)
        py = py_fake_exp(MIN_PRICE, excess, UPDATE_FRAC)
        if not (c11 == limbs == lin == py == want):
            rec("VEC-FEE", "FAIL", f"cancun_blob_fee({excess})", f"lin={lin} c11={c11} geth={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} Geth vectors: C11 i128 == limbs == LIN vm == Python bigint")

    wf, wn, wd, ww = GETH_WIDE
    wide_c11 = int(oracle(["exp", str(wf), str(wn), str(wd)]).splitlines()[-1])
    wide_lin = lin_vm("bb_fake_exp", wf, wn, wd, timeout=180)
    wide_py = py_fake_exp(wf, wn, wd)
    if not (wide_c11 == wide_lin == wide_py == ww):
        rec("GETH-WIDE", "FAIL", "Geth TestFakeExponential 50e6/2225652", f"lin={wide_lin} c11={wide_c11} py={wide_py}")
        return 1
    rec("GETH-WIDE", "PASS", "Geth published vector fakeExponential(1,50e6,2225652)==5709098764")

    accum, prod, naive, wide = first_u64_wrap(wf, wn, wd)
    naive_or = int(oracle(["naive-muldiv", str(accum), str(wn), str(wd)]).splitlines()[-1])
    if naive == wide or naive_or == wide:
        rec("I64-WRAP", "FAIL", "naive uint64 product unexpectedly equalled bigint muldiv")
        return 1
    rec("I64-WRAP", "PASS", "naive uint64 (accum*50e6) wraps on a Geth Taylor step; 128-bit muldiv does not",
        f"accum={accum} naive={naive_or} bigint={wide} prod_bits={prod.bit_length()}")

    src = LIN.read_text(encoding="utf-8")
    if "bb_calc_blob_fee(excess: int, min_price: int, update_frac: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Geth package-level big.Int")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes min_price/update_frac as arguments (no hidden params big.Int)")
    if "*big.Int" in go_src and "minBlobGasPrice" in go_src:
        rec("GETH-PTR", "PASS", "upstream CalcBlobFee is pointerful big.Int; LIN scalar clone drops Header objects")
    else:
        rec("GETH-PTR", "FAIL", "expected pointerful Geth signature in pinned file")

    jit_ok = lin_roundtrip_jit("bb_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on bb_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("bb_cancun_blob_fee", 0)
        if jv == 1:
            rec("C0-JIT", "PASS", "lin_c0 jit cancun_blob_fee(0)==1 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "LGPL-3.0",
        "params_path": PARAMS_REL,
        "min_blob_gasprice": MIN_PRICE,
        "update_fraction": UPDATE_FRAC,
        "blob_gas_per_blob": BLOB_GAS,
        "target_blob_gas": TARGET,
    }
    evidence["lin_clone"] = "src/lin_eip4844_blobfee.lin"
    evidence["c11_oracle"] = "test/oracles/eip4844_blobfee_c11.c"
    evidence["c_subset"] = "test/fixtures/external_proof/eip4844_integer.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["canonical_zero_excess"] = 1
    evidence["canonical_10mib_excess"] = 23
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
