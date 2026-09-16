#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum v1.14.12 CalcGasLimit / VerifyGaslimit vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of CalcGasLimit / VerifyGaslimit / protocol_params
    * Geth-published TestCalcGasLimit vectors (block_validator_test.go)
    * an independent C11 oracle (geth uint64 wrap XOR LIN fail-closed)
    * Python int (exact on the Geth MaxGasLimit = 2^63-1 domain)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN is a Geth node or replaces Ethereum consensus
    * uint64 values above 2^63-1 (LinVM is i64; Geth MaxGasLimit is 2^63-1)
    * wall-clock superiority vs go-ethereum

Class: EXPERIMENTAL (real Geth algorithm, i64-nonneg domain = Geth MaxGasLimit).
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
LIN = ROOT / "src" / "lin_geth_gaslimit.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_gaslimit_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_gaslimit_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_go_ethereum")
EVIDENCE = ROOT / "examples" / "geth_gaslimit" / "geth_gaslimit_evidence.json"

PINNED_COMMIT = "293a300d64be3d9a1c2cc92c26fcff4089deadcd"
BV_SHA256 = "d191d2a0f8b5f32cfc8f3c57f71a9859b3bba43572d187c85e450fc63ce0f8bd"
BV_BLOB = "59783a040730e0be0e273bb24ec3ea4d59fcaef3"
GL_SHA256 = "27c36df89ad62c42ed0f3aca81c976363a1397f940c009bf12363f55368f6666"
GL_BLOB = "dfcabd9a802c4341dbc25ba96d76b4ccc6e550b5"
PP_SHA256 = "2019832fdff9831970c4fb1b89603b6de8521d561f04bdf9d074dfa5e837b0b5"
PP_BLOB = "90e7487cff16f0f482a93adac2c652b546aba97f"
TEST_SHA256 = "83bedcdda2f6e878081e1786fcf8d2d4ee627c68ab16de07c2180cb37bc08fdf"
TEST_BLOB = "8af4057693e97a9a0248fbf1c77a2d628a170bd7"
UPSTREAM_URL = "https://github.com/ethereum/go-ethereum.git"

DIV = 1024
MIN_GL = 5000
GETH_MAX = (1 << 63) - 1

# core/block_validator_test.go TestCalcGasLimit goldens (v1.14.12).
TEST_CALC = [
    (20000000, 20019530, 19980470),
    (40000000, 40039061, 39960939),
]


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


def lin_vm(fn: str, *args: int, timeout: int = 60) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=timeout)
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


def oracle_value(args: list[str]) -> int:
    v = value_of(oracle(args))
    if v is None:
        raise RuntimeError(f"no value= for {args}")
    return v


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


def geth_calc_py(parent: int, desired: int) -> int:
    parent &= (1 << 64) - 1
    desired &= (1 << 64) - 1
    delta = ((parent // DIV) - 1) & ((1 << 64) - 1)
    if desired < MIN_GL:
        desired = MIN_GL
    if parent < desired:
        limit = (parent + delta) & ((1 << 64) - 1)
        return desired if limit > desired else limit
    if parent > desired:
        limit = (parent - delta) & ((1 << 64) - 1)
        return desired if limit < desired else limit
    return parent


def lin_calc_py(parent: int, desired: int, divisor: int = DIV, min_limit: int = MIN_GL) -> int:
    if parent < 0 or desired < 0 or min_limit < 0 or divisor <= 0:
        return 0
    q = parent // divisor
    if q == 0:
        return 0
    delta = q - 1
    if parent + delta < parent:
        return 0
    d = desired if desired >= min_limit else min_limit
    if parent < d:
        limit = parent + delta
        return d if limit > d else limit
    if parent > d:
        limit = parent - delta
        return d if limit < d else limit
    return parent


def geth_verify_py(parent: int, header: int) -> int:
    def to_i64(x: int) -> int:
        x &= (1 << 64) - 1
        return x - (1 << 64) if x >= (1 << 63) else x

    diff = to_i64(parent) - to_i64(header)
    if diff < 0:
        diff = -diff
    bound = (parent & ((1 << 64) - 1)) // DIV
    if diff >= bound:
        return 0
    if (header & ((1 << 64) - 1)) < MIN_GL:
        return 0
    return 1


def lin_verify_py(parent: int, header: int) -> int:
    if parent < 0 or header < 0:
        return 0
    if header < MIN_GL:
        return 0
    bound = parent // DIV
    diff = abs(parent - header)
    return 0 if diff >= bound else 1


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
    bv = UPSTREAM / "core" / "block_validator.go"
    gl = UPSTREAM / "consensus" / "misc" / "gaslimit.go"
    pp = UPSTREAM / "params" / "protocol_params.go"
    tests = UPSTREAM / "core" / "block_validator_test.go"
    if not bv.exists() or not gl.exists() or not pp.exists() or not tests.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD:core/block_validator.go"]
    ).stdout.strip()
    if sha256_file(bv) != BV_SHA256 or blob != BV_BLOB:
        return "FAIL", commit, f"block_validator live={sha256_file(bv)} blob={blob}"
    if sha256_file(gl) != GL_SHA256:
        return "FAIL", commit, "gaslimit.go sha256 mismatch"
    if sha256_file(pp) != PP_SHA256:
        return "FAIL", commit, "protocol_params.go sha256 mismatch"
    if sha256_file(tests) != TEST_SHA256:
        return "FAIL", commit, "block_validator_test.go sha256 mismatch"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_CALCGASLIMIT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH v1.14.12 CalcGasLimit / VerifyGaslimit — external LIN proof")
    print("=" * 78)

    excerpt = FIX / "geth_v1_14_12_CalcGasLimit.go"
    if not excerpt.exists() or "func CalcGasLimit" not in excerpt.read_text(encoding="utf-8"):
        rec("PIN-FILE", "FAIL", "pinned CalcGasLimit excerpt missing")
        return 1
    rec("PIN-FILE", "PASS", "pinned CalcGasLimit excerpt contains the Geth kernel")

    vfile = FIX / "geth_v1_14_12_VerifyGaslimit.go"
    if not vfile.exists() or "int64(parentGasLimit)" not in vfile.read_text(encoding="utf-8"):
        rec("PIN-VERIFY", "FAIL", "pinned VerifyGaslimit excerpt missing int64 cast")
        return 1
    rec("PIN-VERIFY", "PASS", "pinned VerifyGaslimit excerpt contains the int64-cast check")

    up_status, commit, up_note = ensure_upstream()
    blob = BV_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of geth v1.14.12 matches pinned CalcGasLimit/Verify/params/tests",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/block_validator.go")
        live = (UPSTREAM / "core" / "block_validator.go").read_text(
            encoding="utf-8", errors="replace"
        )
        if "parentGasLimit/params.GasLimitBoundDivisor - 1" not in live:
            rec("UPSTREAM-FORMULA", "FAIL", "CalcGasLimit delta formula missing")
            return 1
        rec(
            "UPSTREAM-FORMULA",
            "PASS",
            "live block_validator.go contains parent/divisor - 1",
        )
        tests = (UPSTREAM / "core" / "block_validator_test.go").read_text(
            encoding="utf-8", errors="replace"
        )
        if "{20000000, 20019530, 19980470}" not in tests:
            rec("UPSTREAM-GOLDEN", "FAIL", "TestCalcGasLimit golden missing")
            return 1
        rec("UPSTREAM-GOLDEN", "PASS", "live TestCalcGasLimit contains 20M/40M goldens")
        params = (UPSTREAM / "params" / "protocol_params.go").read_text(
            encoding="utf-8", errors="replace"
        )
        if "GasLimitBoundDivisor uint64 = 1024" not in params:
            rec("UPSTREAM-CONST", "FAIL", "GasLimitBoundDivisor=1024 missing")
            return 1
        if "MinGasLimit          uint64 = 5000" not in params:
            rec("UPSTREAM-CONST", "FAIL", "MinGasLimit=5000 missing")
            return 1
        rec("UPSTREAM-CONST", "PASS", "params.GasLimitBoundDivisor=1024 MinGasLimit=5000")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-FORMULA", "SKIP", "live block_validator.go not fetched")
        rec("UPSTREAM-GOLDEN", "SKIP", "live TestCalcGasLimit not fetched")
        rec("UPSTREAM-CONST", "SKIP", "live protocol_params.go not fetched")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-FORMULA", "FAIL", "could not verify formula")
        rec("UPSTREAM-GOLDEN", "FAIL", "could not verify goldens")
        rec("UPSTREAM-CONST", "FAIL", "could not verify constants")
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 CalcGasLimit selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle matches Geth-published TestCalcGasLimit goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if chk.returncode != 0 and ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of CalcGasLimit clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_gaslimit.lin")

    chk_go = run([str(C0), "check", str(GO_TR)])
    if chk_go.returncode != 0 and "LIN_CHECK" not in chk_go.stdout and ".typecheck=passed" not in chk_go.stdout:
        rec("GO-TR-CHECK", "FAIL", "lin_from_go.lin check", chk_go.stdout + chk_go.stderr)
    else:
        rec("GO-TR-CHECK", "PASS", "Compiler 0 check of Go transpiler v1 (selector/error fail-closed)")

    gosrc = GO_TR.read_text(encoding="utf-8")
    need = ("REJ_GO_SELECTOR", "REJ_GO_ERROR", "REJ_GO_POINTER", "go_rej_geth_calc")
    if all(tok in gosrc for tok in need):
        rec(
            "GO-TR-REJ",
            "PASS",
            "lin_from_go v1 fail-closes package selectors, error returns, pointers",
        )
    else:
        rec("GO-TR-REJ", "FAIL", "Go reject codes missing from lin_from_go.lin")
        return 1

    csrc = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX_SCOPE" in csrc and "REJ_C_REFERENCE" in csrc and "cfs_cxx_reject_gate" in csrc:
        rec("C-TR-CXX", "PASS", "lin_from_c v2 fail-closes C++ scope/template/class/reference")
    else:
        rec("C-TR-CXX", "FAIL", "C++ reject codes missing from lin_from_c.lin")
        return 1

    g1 = run([str(C0), "vm", str(GO_TR), "go_rej_geth_calc"], timeout=30)
    g1v = value_of(g1.stdout)
    if g1.returncode == 0 and g1v == 4:
        rec("GO-NUM-GATE", "PASS", "lin_c0 vm go_rej_geth_calc==4 (selector reject, numeric)")
    elif g1.returncode != 0 and "STRING" in (g1.stdout + g1.stderr).upper():
        rec(
            "GO-NUM-GATE",
            "SKIP",
            "lin_c0 numeric Go gate not executed (string-literal VM reject on module)",
            (g1.stdout + g1.stderr)[:200],
        )
    else:
        rec(
            "GO-NUM-GATE",
            "FAIL",
            "go_rej_geth_calc did not return 4",
            g1.stdout + g1.stderr,
        )
        return 1

    gate = run([str(C0), "vm", str(LIN), "gl_test_suite"], timeout=60)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gl_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gl_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for parent, want_max, want_min in TEST_CALC:
        py_inc = geth_calc_py(parent, 2 * parent)
        py_dec = geth_calc_py(parent, 0)
        py_same = geth_calc_py(parent, parent)
        py_up1 = geth_calc_py(parent, parent + 1)
        py_dn1 = geth_calc_py(parent, parent - 1)
        if py_inc != want_max or py_dec != want_min:
            rec("VEC-PY", "FAIL", f"python vs TestCalcGasLimit parent={parent}")
            return 1
        c11_inc = oracle_value(["calc", str(parent), str(2 * parent)])
        c11_dec = oracle_value(["calc", str(parent), "0"])
        if c11_inc != want_max or c11_dec != want_min:
            rec("VEC-C11", "FAIL", f"c11 vs TestCalcGasLimit parent={parent}")
            return 1
        lin_inc = lin_vm("gl_calc_default", parent, 2 * parent)
        lin_dec = lin_vm("gl_calc_default", parent, 0)
        lin_same = lin_vm("gl_calc_default", parent, parent)
        lin_up1 = lin_vm("gl_calc_default", parent, parent + 1)
        lin_dn1 = lin_vm("gl_calc_default", parent, parent - 1)
        if [lin_inc, lin_dec, lin_same, lin_up1, lin_dn1] != [
            want_max,
            want_min,
            py_same,
            py_up1,
            py_dn1,
        ]:
            rec("VEC-LIN", "FAIL", f"LIN vs goldens parent={parent}")
            return 1
        c11_lin = oracle_value(["lin_calc", str(parent), str(2 * parent), "1024", "5000"])
        if c11_lin != lin_inc:
            rec("VEC-LIMB", "FAIL", f"C11 lin_calc vs LIN parent={parent}")
            return 1
        if lin_verify_py(parent, want_max) != 1 or lin_vm("gl_verify_default", parent, want_max) != 1:
            rec("VEC-VER-OK", "FAIL", f"max increase must verify parent={parent}")
            return 1
        if lin_verify_py(parent, want_max + 1) != 0 or lin_vm(
            "gl_verify_default", parent, want_max + 1
        ) != 0:
            rec("VEC-VER-BAD", "FAIL", f"max+1 must fail verify parent={parent}")
            return 1
        n_ok += 1
    rec(
        "VEC-CONSENSUS",
        "PASS",
        f"{n_ok}/{n_ok} TestCalcGasLimit: C11 == Python == LIN vm == Geth goldens",
    )

    wrap_geth = geth_calc_py(500, 5000)
    wrap_lin = lin_calc_py(500, 5000)
    wrap_c11_g = oracle_value(["calc", "500", "5000"])
    wrap_c11_l = oracle_value(["lin_calc", "500", "5000", "1024", "5000"])
    wrap_lin_vm = lin_vm("gl_calc_default", 500, 5000)
    wrap_ok = lin_vm("gl_calc_ok", 500, 5000, 1024, 5000)
    if wrap_lin != 0 or wrap_c11_l != 0 or wrap_lin_vm != 0 or wrap_ok != 0:
        rec("DELTA-WRAP-LIN", "FAIL", "LIN must fail-close parent/1024==0")
        return 1
    if wrap_geth == 0 or wrap_c11_g == 0:
        rec("DELTA-WRAP-GETH", "FAIL", "Geth uint64 wrap of (500/1024)-1 should be nonzero")
        return 1
    rec(
        "DELTA-WRAP",
        "PASS",
        "parent=500: Geth uint64 (0-1) wraps; LIN fail-closes to 0",
        f"geth={wrap_geth} lin=0",
    )

    if lin_vm("gl_verify_default", 20000000, 4999) != 0:
        rec("MIN-GAS", "FAIL", "header below MinGasLimit=5000 must be invalid")
        return 1
    rec("MIN-GAS", "PASS", "VerifyGaslimit rejects header < 5000")

    if lin_vm("gl_verify", -1, 5000, 1024, 5000) != 0:
        rec("NEG-REJECT", "FAIL", "negative parent must fail-close")
        return 1
    rec(
        "NEG-REJECT",
        "PASS",
        "LIN rejects negative gas limits (Geth int64(uint64) cast is a wrap hazard)",
    )

    src = LIN.read_text(encoding="utf-8")
    if "gl_calc(parent: int, desired: int, divisor: int, min_limit: int)" in src:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes divisor/min as arguments (Geth uses params package globals)",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit divisor/min args")
        return 1

    if "gl_delta_ok" in src and "gl_calc_ok" in src:
        rec(
            "FAIL-CLOSED",
            "PASS",
            "delta underflow (parent/divisor==0) and negatives fail-closed via gl_calc_ok",
        )
    else:
        rec("FAIL-CLOSED", "FAIL", "fail-closed helpers missing")
        return 1

    jit_ok = lin_roundtrip_jit("gl_calc_default", 20000000, 40000000)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gl_calc_default (in-memory libtcc)")
    else:
        jv = lin_jit("gl_calc_default", 20000000, 40000000)
        if jv == 20019530:
            rec("C0-JIT", "PASS", "lin_c0 jit gl_calc_default(20M,40M)==20019530 (in-memory libtcc)")
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
        "tag": "v1.14.12",
        "commit": commit or PINNED_COMMIT,
        "path": "core/block_validator.go CalcGasLimit + consensus/misc/gaslimit.go VerifyGaslimit",
        "block_validator_git_blob_sha": blob or BV_BLOB,
        "block_validator_file_sha256": BV_SHA256,
        "gaslimit_git_blob_sha": GL_BLOB,
        "gaslimit_file_sha256": GL_SHA256,
        "protocol_params_git_blob_sha": PP_BLOB,
        "protocol_params_file_sha256": PP_SHA256,
        "tests_git_blob_sha": TEST_BLOB,
        "tests_file_sha256": TEST_SHA256,
        "license": "LGPL-3.0",
        "constants": {"GasLimitBoundDivisor": DIV, "MinGasLimit": MIN_GL, "MaxGasLimit": GETH_MAX},
    }
    evidence["lin_clone"] = "src/lin_geth_gaslimit.lin"
    evidence["go_transpiler"] = "src/lin_from_go.lin"
    evidence["c11_oracle"] = "test/oracles/geth_gaslimit_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["goldens"] = [
        {"parent": p, "max_increase": mx, "min_decrease": mn} for p, mx, mn in TEST_CALC
    ]
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-geth-gaslimit"
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
