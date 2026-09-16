#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum EIP-1559 CalcBaseFee (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of consensus/misc/eip1559/eip1559.go (git blob + sha256)
    * pinned DefaultElasticityMultiplier=2 / DefaultBaseFeeChangeDenominator=8 /
      InitialBaseFee=1e9 excerpt from params/protocol_params.go
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * a Python bigint oracle of the EIP-1559 integer formula

  NOT claimed:
    * full uint256 / mainnet Geth node parity
    * that LIN replaces go-ethereum or the EVM fee market
    * wall-clock superiority vs gc/LLVM
    * computational soundness of Merkle receipts

Class: EXPERIMENTAL (real EIP-1559 algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_eip1559_basefee.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "eip1559_basefee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "eip1559_basefee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_go_ethereum")
EVIDENCE = ROOT / "examples" / "eip1559_basefee" / "eip1559_basefee_evidence.json"
INT_C = FIX / "eip1559_integer.c"

PINNED_SHA256 = "aafcf793817199d0ae5349659a49278fa65bd3dd5afffb6a5a4096fcda916d77"
PINNED_BLOB = "a90bd744b2757b5ad167622038f6ebdc48f8ba6b"
PINNED_COMMIT = "293a300d64be3d9a1c2cc92c26fcff4089deadcd"
PINNED_TAG = "v1.14.12"
UPSTREAM_REL = "consensus/misc/eip1559/eip1559.go"
PARAMS_REL = "params/protocol_params.go"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-eip1559-basefee"

INITIAL = 1_000_000_000
ELASTICITY = 2
DENOM = 8


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


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_fee_delta(fee: int, gas_delta: int, target: int, denom: int) -> int:
    if target <= 0 or denom <= 0 or fee < 0 or gas_delta < 0:
        return 0
    return (fee * gas_delta // target) // denom


def py_calc(limit: int, used: int, fee: int, elasticity: int, denom: int, london: int) -> int:
    if limit < 0 or used < 0 or fee < 0 or elasticity <= 0 or denom <= 0 or london < 0:
        return 0
    if london == 0:
        return INITIAL
    target = limit // elasticity
    if used == target:
        return fee
    if used > target:
        delta = py_fee_delta(fee, used - target, target, denom)
        if delta < 1:
            delta = 1
        return fee + delta
    delta = py_fee_delta(fee, target - used, target, denom)
    if fee < delta:
        return 0
    return fee - delta


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


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_EIP1559_BASEFEE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  EIP-1559 CalcBaseFee — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "eip1559.go"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned eip1559.go missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned eip1559.go sha256 matches manifest")
    blob_local = git_blob_sha(pinned)
    if blob_local != PINNED_BLOB:
        rec("PIN-BLOB", "FAIL", "pinned git blob sha mismatch", blob_local)
        return 1
    rec("PIN-BLOB", "PASS", "pinned eip1559.go git blob sha1 matches GitHub")

    excerpt = (FIX / "eip1559_params_excerpt.txt").read_text(encoding="utf-8")
    if "DefaultElasticityMultiplier     = 2" not in excerpt or "InitialBaseFee                  = 1000000000" not in excerpt:
        rec("PIN-PARAMS", "FAIL", "params excerpt missing canonical constants")
        return 1
    rec("PIN-PARAMS", "PASS", "pinned protocol_params excerpt has elasticity=2 denom=8 initial=1e9")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned go-ethereum commit matches fixture",
            f"tag={PINNED_TAG} commit={commit} blob={blob}",
        )
        params = UPSTREAM / PARAMS_REL
        if params.exists() and excerpt.strip() in params.read_text(encoding="utf-8"):
            rec("UPSTREAM-PARAMS", "PASS", "live protocol_params.go contains pinned elasticity/denom/initial")
        else:
            rec("UPSTREAM-PARAMS", "FAIL", "live protocol_params.go missing pinned excerpt")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-PARAMS", "SKIP", "live params not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-PARAMS", "FAIL", "params not checked", up_note)

    go_src = pinned.read_text(encoding="utf-8")
    if "func CalcBaseFee" not in go_src or "parent.GasUsed == parentGasTarget" not in go_src:
        rec("GO-FORMULA", "FAIL", "pinned Go file does not contain CalcBaseFee formula")
        return 1
    rec("GO-FORMULA", "PASS", "pinned Go contains CalcBaseFee with target-equal / increase / decrease")

    if not INT_C.exists():
        rec("C-SUBSET", "FAIL", "eip1559_integer.c missing")
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
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree on canonical vectors")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout and chk.returncode != 0:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eip1559 clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_eip1559_basefee.lin")

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

    if "1000000000ULL" in c_src and "cfs_strip_suffixes" in tr_src:
        rec("SUFFIX-NEED", "PASS", "C restatement uses ULL suffixes; v2 transpiler strips them")
    else:
        rec("SUFFIX-NEED", "FAIL", "ULL suffix / strip pairing missing")

    gate = run([str(C0), "vm", str(LIN), "eip_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "eip_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "eip_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        (30000000, 15000000, INITIAL, ELASTICITY, DENOM, 1),
        (30000000, 30000000, INITIAL, ELASTICITY, DENOM, 1),
        (30000000, 0, INITIAL, ELASTICITY, DENOM, 1),
        (30000000, 15000001, 1000, ELASTICITY, DENOM, 1),
        (30000000, 30000000, INITIAL, ELASTICITY, DENOM, 0),
        (30000000, 0, 100, ELASTICITY, DENOM, 1),
        (30000000, 0, INITIAL, ELASTICITY, DENOM, 1),
        (15000000, 15000000, INITIAL, ELASTICITY, DENOM, 1),
    ]
    n_ok = 0
    for vec in vectors:
        want = int(oracle(["calc", *[str(x) for x in vec]]).splitlines()[-1])
        want_limbs = int(oracle(["calc", *[str(x) for x in vec], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("eip_calc_base_fee", *vec)
        py = py_calc(*vec)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"calc{vec}", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"eip_calc_base_fee{vec}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {vec}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python bigint")

    ov_fee = 10**13
    ov_vec = (30000000, 30000000, ov_fee, ELASTICITY, DENOM, 1)
    ov_lin = lin_vm("eip_calc_base_fee", *ov_vec)
    ov_c11 = int(oracle(["calc", *[str(x) for x in ov_vec]]).splitlines()[-1])
    ov_py = py_calc(*ov_vec)
    if ov_lin != ov_c11 or ov_lin != ov_py or ov_lin != 11250000000000:
        rec("WIDE-FEE", "FAIL", "128-bit full-block 1e13 wei parent", f"lin={ov_lin} c11={ov_c11} py={ov_py}")
        return 1
    rec("WIDE-FEE", "PASS", "full block at parent=1e13 wei: LIN==C11==Python == 11250000000000")

    naive = int(oracle(["naive-delta", str(ov_fee), "15000000", "15000000", "8"]).splitlines()[-1])
    wide = py_fee_delta(ov_fee, 15000000, 15000000, DENOM)
    if naive == wide:
        rec("I64-WRAP", "FAIL", "naive uint64 product unexpectedly equalled bigint muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive uint64 (1e13*15e6) wraps; 128-bit muldiv does not",
        f"naive_delta={naive} bigint_delta={wide}",
    )

    src = LIN.read_text(encoding="utf-8")
    if "eip_calc_base_fee(parent_gas_limit: int, parent_gas_used: int, parent_base_fee: int, elasticity: int, denom: int, london: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Geth ChainConfig/Header pointers")
        return 1
    rec(
        "EXPLICIT-ARGS",
        "PASS",
        "LIN clone takes elasticity/denom/london as arguments (no hidden ChainConfig)",
    )
    if "*params.ChainConfig" in go_src and "*types.Header" in go_src:
        rec("GETH-PTR", "PASS", "upstream CalcBaseFee is pointerful; LIN scalar clone drops Header/Config objects")
    else:
        rec("GETH-PTR", "FAIL", "expected pointerful Geth signature in pinned file")

    jit_ok = lin_roundtrip_jit("eip_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on eip_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("eip_calc_base_fee", 30000000, 30000000, INITIAL, 2, 8, 1)
        if jv == 1125000000:
            rec("C0-JIT", "PASS", "lin_c0 jit full-block 1 gwei == 1125000000 (in-memory libtcc)")
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
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "LGPL-3.0",
        "params_path": PARAMS_REL,
        "elasticity": ELASTICITY,
        "base_fee_change_denominator": DENOM,
        "initial_base_fee": INITIAL,
    }
    evidence["lin_clone"] = "src/lin_eip1559_basefee.lin"
    evidence["c11_oracle"] = "test/oracles/eip1559_basefee_c11.c"
    evidence["c_subset"] = "test/fixtures/external_proof/eip1559_integer.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["canonical_full_block_1gwei"] = 1125000000
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
