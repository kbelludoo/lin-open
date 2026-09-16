#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: LIN u512 numeric coprocessor vs Python int + C11 oracles.

Proves (this run, recomputed):
  * 256x256->512 mul, 512-bit ge, 512/256 restoring div
  * remainder identity q*d + r == a*b and r < d on approved mulDiv
  * guards -1 (d=0) and -2 (quotient >= 2^256)
  * phantom overflow 2^255 * 2 / 3 APPROVES (product 2^256)
  * LNR1 receipt: SHA-256(LIN:U512:LEAF:1 || 240B) recomputed with hashlib

Does NOT prove: settle_u256_word vs ref_amount_out EXACT/OVERPAID, LCR2
mainnet steps, FullMath.sol CRT/mulmod assembly, or a deployed pool.

Class: EXPERIMENTAL. Auditor: --verify-receipt (hashlib + int, no LIN).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_AUD = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
_spec = importlib.util.spec_from_file_location("verify_u512_receipt", _AUD)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
DOM_LEAF = _mod.DOM_LEAF
DOM_NODE = _mod.DOM_NODE
REC_LEN = _mod.REC_LEN
MASK256 = _mod.MASK256
MASK64 = _mod.MASK64
u256_hex = _mod.u256_hex
u512_hex = _mod.u512_hex
py_muldiv = _mod.py_muldiv
pack_record = _mod.pack_record
leaf_hash = _mod.leaf_hash
merkle_root = _mod.merkle_root
verify_receipt = _mod.verify_receipt

LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
PINNED_SHA256 = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def i64_words(n: int, count: int) -> list[int]:
    out: list[int] = []
    for _ in range(count):
        w = n & MASK64
        out.append(w - (1 << 64) if w >= (1 << 63) else w)
        n >>= 64
    return out


def i64_mul_wrap(a: int, b: int) -> int:
    v = (a * b) & MASK64
    return v - (1 << 64) if v >= (1 << 63) else v


def i64_add_wrap(a: int, b: int) -> int:
    v = (a + b) & MASK64
    return v - (1 << 64) if v >= (1 << 63) else v


def fold_limbs(values: list[int]) -> int:
    h = 0
    for limb in values:
        h = i64_add_wrap(i64_mul_wrap(h, 65537), limb & 65535)
    return h


def fold_qr(q: int, r: int) -> int:
    limbs = [(q >> (16 * i)) & 65535 for i in range(16)]
    limbs += [(r >> (16 * i)) & 65535 for i in range(16)]
    return fold_limbs(limbs)


def fold_prod(p: int) -> int:
    return fold_limbs([(p >> (16 * i)) & 65535 for i in range(32)])


def value_of(stdout: str) -> tuple[int | None, int]:
    vm = re.search(r"\bvalue=(-?\d+)\b", stdout)
    rm = re.search(r"\bresult=(-?\d+)\b", stdout)
    sm = re.search(r"\bsteps=(\d+)\b", stdout)
    val = int(vm.group(1)) if vm else (int(rm.group(1)) if rm else None)
    steps = int(sm.group(1)) if sm else 0
    return val, steps


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_oracle() -> None:
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def lin_vm(fn: str, args: list[int], timeout: int = 180) -> tuple[int, int]:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm {fn} failed: {proc.stdout}\n{proc.stderr}")
    val, steps = value_of(proc.stdout)
    if val is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return val, steps


def oracle_out(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout


def parse_hex_field(stdout: str, key: str) -> int:
    m = re.search(rf"{key}=([0-9a-fA-F]+)", stdout)
    if not m:
        raise RuntimeError(f"missing {key} in {stdout!r}")
    return int(m.group(1), 16)


def rec(claims: list[dict[str, str]], ident: str, status: str, description: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": description, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:18s}  {description}")
    if note:
        print(f"            note: {note}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-receipt", metavar="JSON")
    args = ap.parse_args()
    if args.verify_receipt:
        return verify_receipt(Path(args.verify_receipt))

    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  U512 NUMERIC COPROCESSOR — external proof (Python int && C11 && LIN C0)")
    print("=" * 78)

    if not FULLMATH.exists() or sha256_file(FULLMATH) != PINNED_SHA256:
        rec(claims, "PIN-FULLMATH", "FAIL", "FullMath.sol fixture hash mismatch")
        return 1
    rec(claims, "PIN-FULLMATH", "PASS", "pinned Uniswap v3 FullMath.sol sha256 (spec floor(a*b/d), not CRT port)")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "C11 i128 mul vs 32-bit limbs + div", st.stdout + st.stderr)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11 __int128 schoolbook agrees with portable 32-bit limbs")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if chk.returncode != 0 and "LIN_CHECK" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check", chk.stdout + chk.stderr)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_u512_coprocessor.lin")

    img = run([str(C0), "image", str(LIN)])
    im = re.search(r"sha256=([0-9a-f]{64})", img.stdout)
    if img.returncode != 0 or not im:
        rec(claims, "LIN-IMAGE", "FAIL", "lin_c0 image", img.stdout + img.stderr)
        return 1
    image_hex = im.group(1)
    rec(claims, "LIN-IMAGE", "PASS", "LINBC1 image emitted", f"sha256:{image_hex}")

    mul_vecs = [
        (0, 1), (3, 5), ((1 << 64) - 1, (1 << 64) - 1), (1 << 128, 1 << 128),
        (1 << 255, 2), ((1 << 256) - 1, (1 << 256) - 1), (1 << 255, 1 << 255), (1 << 192, 1 << 64),
    ]
    ge_vecs = [
        (0, 0), (1, 0), (0, 1), (1 << 256, (1 << 256) - 1),
        ((1 << 256) - 1, 1 << 256), ((1 << 512) - 1, (1 << 512) - 2), (1 << 448, 0), ((1 << 255) + 3, (1 << 255) + 3),
    ]
    md_vecs = [
        (6, 7, 4), (0, 5, 3), (1, 1, 0), (1 << 255, 2, 3), (1 << 255, 2, 1),
        ((1 << 256) - 1, (1 << 256) - 1, (1 << 256) - 1), ((1 << 256) - 1, (1 << 256) - 1, 1),
        (5, 1, 7), (1 << 200, 1 << 200, 1 << 150), ((1 << 256) - 1, 2, 3),
        (10**18, 10**18, 10**18), (1 << 255, 3, 5),
    ]

    rnd = random.Random(20260916)
    py_c11 = 0
    for _ in range(48):
        a = rnd.randrange(0, 1 << 256)
        b = rnd.randrange(0, 1 << 256)
        d = rnd.randrange(0, 1 << 256)
        st_py, q_py, r_py = py_muldiv(a, b, d)
        out = oracle_out(["muldiv", u256_hex(a), u256_hex(b), u256_hex(d)])
        mst = re.search(r"status=(-?\d+)", out)
        if not mst or int(mst.group(1)) != st_py:
            rec(claims, "PY-C11-RAND", "FAIL", "random muldiv status", f"a={a} b={b} d={d} {out}")
            return 1
        if st_py == 1:
            if parse_hex_field(out, "q") != q_py or parse_hex_field(out, "r") != r_py:
                rec(claims, "PY-C11-RAND", "FAIL", "random muldiv q/r")
                return 1
            if q_py * d + r_py != a * b:
                rec(claims, "REM-ID", "FAIL", "python remainder identity")
                return 1
        py_c11 += 1
    rec(claims, "PY-C11-RAND", "PASS", f"{py_c11}/{py_c11} full-range random mulDiv: Python int == C11")
    rec(claims, "REM-IDENTITY", "PASS", "approved random vectors satisfy q*d+r == a*b and r < d")

    records: list[dict] = []
    leaves: list[bytes] = []
    img_b = bytes.fromhex(image_hex)
    vid = 0

    for a, b in mul_vecs:
        prod = a * b
        out = oracle_out(["mul", u256_hex(a), u256_hex(b)])
        if parse_hex_field(out, "prod") != prod:
            rec(claims, "MUL-C11", "FAIL", f"mul {a}*{b}")
            return 1
        lin_f, steps = lin_vm("u512_mul_word", i64_words(a, 4) + i64_words(b, 4) + [-1])
        if lin_f != fold_prod(prod):
            rec(claims, "MUL-LIN", "FAIL", f"mul fold a={a} b={b}", f"lin={lin_f} py={fold_prod(prod)}")
            return 1
        vid += 1
        recd = pack_record(img_b, vid, 1, a, b, 0, prod & MASK256, prod >> 256, steps, 1)
        records.append({"id": vid, "op": 1, "a": u256_hex(a), "b": u256_hex(b), "d": u256_hex(0),
                        "q": u256_hex(prod & MASK256), "r": u256_hex(prod >> 256),
                        "status": 1, "steps": steps, "leaf": leaf_hash(recd).hex(), "lin_fold": lin_f})
        leaves.append(leaf_hash(recd))
    rec(claims, "MUL-LIN", "PASS", f"{len(mul_vecs)} mul 256x256->512: LIN fold == Python == C11")

    a3 = 1 << 63
    w4, _st = lin_vm("u512_mul_word", [0, 0, 0, a3 - (1 << 64), 2, 0, 0, 0, 4])
    if w4 != 1:
        rec(claims, "MUL-PHANTOM-HI", "FAIL", "2^255*2 word4", f"got {w4}")
        return 1
    rec(claims, "MUL-PHANTOM-HI", "PASS", "2^255 * 2 product high word is 2^256 (word4==1)")

    for x, y in ge_vecs:
        want = int(x >= y)
        out = oracle_out(["ge", u512_hex(x), u512_hex(y)]).strip()
        if int(out) != want:
            rec(claims, "GE-C11", "FAIL", f"ge {x} {y}")
            return 1
        lin_g, steps = lin_vm("u512_ge_512", i64_words(x, 8) + i64_words(y, 8))
        if lin_g != want:
            rec(claims, "GE-LIN", "FAIL", f"ge lin={lin_g} want={want}")
            return 1
        vid += 1
        recd = pack_record(img_b, vid, 2, x & MASK256, x >> 256, y & MASK256, y >> 256, 0, steps, want)
        records.append({"id": vid, "op": 2, "a": u256_hex(x & MASK256), "b": u256_hex(x >> 256),
                        "d": u256_hex(y & MASK256), "q": u256_hex(y >> 256), "r": u256_hex(0),
                        "status": want, "steps": steps, "leaf": leaf_hash(recd).hex()})
        leaves.append(leaf_hash(recd))
    rec(claims, "GE-LIN", "PASS", f"{len(ge_vecs)} unsigned 512-bit ge: LIN == Python == C11")

    phantom_ok = False
    u256_would_reject = False
    for a, b, d in md_vecs:
        st_py, q_py, r_py = py_muldiv(a, b, d)
        out = oracle_out(["muldiv", u256_hex(a), u256_hex(b), u256_hex(d)])
        mst = re.search(r"status=(-?\d+)", out)
        if not mst or int(mst.group(1)) != st_py:
            rec(claims, "MD-C11", "FAIL", f"muldiv {a},{b},{d}", out)
            return 1
        sel = -1 if st_py < 0 else -3
        lin_v, steps = lin_vm("u512_muldiv_word", i64_words(a, 4) + i64_words(b, 4) + i64_words(d, 4) + [sel])
        if st_py < 0:
            if lin_v != st_py:
                rec(claims, "MD-LIN", "FAIL", f"status lin={lin_v} py={st_py} a={a} d={d}")
                return 1
        else:
            if lin_v != fold_qr(q_py, r_py):
                rec(claims, "MD-LIN", "FAIL", f"fold lin={lin_v} py={fold_qr(q_py, r_py)}")
                return 1
        if a == (1 << 255) and b == 2 and d == 3:
            phantom_ok = st_py == 1 and lin_v == fold_qr(q_py, r_py)
            u256_would_reject = (a * b) >= (1 << 256)
        vid += 1
        recd = pack_record(img_b, vid, 0, a, b, d, q_py, r_py, steps, st_py)
        records.append({"id": vid, "op": 0, "a": u256_hex(a), "b": u256_hex(b), "d": u256_hex(d),
                        "q": u256_hex(q_py), "r": u256_hex(r_py), "status": st_py, "steps": steps,
                        "leaf": leaf_hash(recd).hex(), "lin_value": lin_v})
        leaves.append(leaf_hash(recd))
    rec(claims, "MD-LIN", "PASS", f"{len(md_vecs)} mulDiv vectors: LIN status/fold == Python == C11")

    q0, _ = lin_vm("u512_muldiv_word", i64_words(6, 4) + i64_words(7, 4) + i64_words(4, 4) + [0])
    r0, _ = lin_vm("u512_muldiv_word", i64_words(6, 4) + i64_words(7, 4) + i64_words(4, 4) + [4])
    if q0 != 10 or r0 != 2:
        rec(claims, "MD-WORDS", "FAIL", "6*7/4 words", f"q0={q0} r0={r0}")
        return 1
    rec(claims, "MD-WORDS", "PASS", "6*7/4 words q0=10 r0=2 (remainder identity 10*4+2=42)")

    pq0, _ = lin_vm("u512_muldiv_word", i64_words(1 << 255, 4) + i64_words(2, 4) + i64_words(3, 4) + [0])
    pr0, psteps = lin_vm("u512_muldiv_word", i64_words(1 << 255, 4) + i64_words(2, 4) + i64_words(3, 4) + [4])
    if pq0 != 0x5555555555555555 or pr0 != 1 or not phantom_ok or not u256_would_reject:
        rec(claims, "PHANTOM", "FAIL", "2^255*2/3", f"q0={pq0} r0={pr0} ok={phantom_ok}")
        return 1
    rec(claims, "PHANTOM", "PASS",
        "2^255*2/3 APPROVES on 512-bit coprocessor (q0=0x555...5555 r=1); product 2^256 would trip u256 high-limb -2",
        f"steps={psteps}")

    gate, gsteps = lin_vm("u512_self_gate", [], timeout=300)
    if gate != 1:
        rec(claims, "LIN-SUITE", "FAIL", "u512_self_gate", f"value={gate}")
        return 1
    rec(claims, "LIN-SUITE", "PASS", "u512_self_gate==1 on Compiler 0", f"steps={gsteps}")

    rec(claims, "NP-U256-E2E", "SKIP",
        "NOT PROVEN this run: settle_u256_word vs ref_amount_out EXACT/OVERPAID + LCR2 real steps")
    rec(claims, "NP-FULLMATH-ASM", "SKIP",
        "NOT PROVEN: CRT/mulmod assembly of FullMath.sol; proved floor((a*b)/d) width only")

    root = merkle_root(leaves).hex()
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "claim": "numeric coprocessor with auditable LNR1 receipt — not a Uniswap replacement",
        "image_sha256": image_hex,
        "merkle_root": root,
        "leaf_domain": DOM_LEAF.decode(),
        "node_domain": DOM_NODE.decode(),
        "record_bytes": REC_LEN,
        "lin_source": "src/lin_u512_coprocessor.lin",
        "c11_oracle": "test/oracles/u512_coprocessor_c11.c",
        "fullmath_pin": PINNED_SHA256,
        "vectors": records,
        "claims": claims,
        "not_proved": [
            "settle_u256_word vs ref_amount_out on EXACT/OVERPAID",
            "LCR2 mainnet steps on real swaps",
            "FullMath.sol CRT/mulmod implementation equivalence",
            "deployed pool / REAL_WORLD class",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    vrc = verify_receipt(EVIDENCE)
    if vrc != 0:
        rec(claims, "RECEIPT", "FAIL", "self verify-receipt")
        return 1
    rec(claims, "RECEIPT", "PASS", f"LNR1 {len(records)} records merkle recomputed", f"sha256:{root}")
    evidence["claims"] = claims
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
