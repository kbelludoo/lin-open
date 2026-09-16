#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: LIN u512 numeric coprocessor vs Python int vs C11 oracles.

Proves 256x256->512 mul, 512-bit ge, 512/256 restoring div (q*d+r==n),
and mulDiv guards -1 (d=0) / -2 (q overflow). Class: EXPERIMENTAL
(FullMath width, not CRT/mulmod assembly, not a deployed pool).

Does not close settle_u256_word. See test/prove_u256_lcr2_e2e_slice.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
M64 = (1 << 64) - 1
U256 = (1 << 256) - 1
U512 = (1 << 512) - 1


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def i64(w: int) -> int:
    w &= M64
    return w - (1 << 64) if w >= (1 << 63) else w


def words(x: int, n: int = 4) -> list[int]:
    return [i64((x >> (64 * i)) & M64) for i in range(n)]


def from_words(ws: list[int]) -> int:
    out = 0
    for i, w in enumerate(ws):
        out |= (w & M64) << (64 * i)
    return out


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(a * b, d)
    if q > U256:
        return -2, 0, 0
    return 1, q, r


def py_div(n: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(n, d)
    if q > U256:
        return -2, 0, 0
    return 1, q, r


def parse_oracle(stdout: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in stdout.strip().replace("\n", " ").split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def merkle(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nxt = [
            hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest()
            for i in range(0, len(nodes), 2)
        ]
        nodes = nxt
    return nodes[0]


def pack_lnr1(img: bytes, vec_id: int, op: int, status: int,
              a: int, b: int, d: int, q: int, r: int, steps: int) -> bytes:
    rec = bytearray(240)
    rec[0:4] = b"LNR1"
    rec[4] = 1
    rec[5] = 1
    rec[8:40] = img
    struct.pack_into("<Qii", rec, 40, vec_id, op, status)
    rec[56:88] = (a & U256).to_bytes(32, "big")
    rec[88:120] = (b & U256).to_bytes(32, "big")
    rec[120:152] = (d & U256).to_bytes(32, "big")
    rec[152:184] = (q & U256).to_bytes(32, "big")
    rec[184:216] = (r & U256).to_bytes(32, "big")
    struct.pack_into("<Q", rec, 216, steps)
    return bytes(rec)


def ensure_c0() -> None:
    if C0.exists():
        return
    p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if p.returncode != 0 or not C0.exists():
        raise RuntimeError(p.stderr or p.stdout)


def ensure_oracle() -> None:
    p = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)


def lin_image() -> tuple[Path, bytes, str]:
    img = Path("/tmp/u512_coprocessor.linbc")
    p = run([str(C0), "image", str(LIN), "-o", str(img)], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    blob = img.read_bytes()
    loader = hashlib.sha256(b"linbc1:img:" + blob[:-32]).digest()
    if loader != blob[-32:]:
        raise RuntimeError("LINBC1 self-hash mismatch")
    return img, loader, p.stdout.strip()


def lin_run(img: Path, fn: str, args: list[int], timeout: int = 180) -> tuple[int, int]:
    p = run([str(C0), "run", str(img), fn, *[str(a) for a in args]], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{fn} {args[:4]}... {p.stdout}\n{p.stderr}")
    m = re.search(r"value=(-?\d+)\s+steps=(\d+)", p.stdout)
    if not m:
        raise RuntimeError(p.stdout)
    return int(m.group(1)), int(m.group(2))


def lin_muldiv(img: Path, a: int, b: int, d: int) -> tuple[int, int, int, int]:
    args = words(a) + words(b) + words(d)
    st, steps = lin_run(img, "u512_muldiv_word", args + [-1])
    if st != 1:
        return st, 0, 0, steps
    qw, rs = [], steps
    for i in range(8):
        v, s = lin_run(img, "u512_muldiv_word", args + [i])
        qw.append(v)
        rs += s
    return 1, from_words(qw[:4]), from_words(qw[4:]), rs


def lin_mul(img: Path, a: int, b: int) -> tuple[int, int]:
    args = words(a) + words(b)
    ws, steps = [], 0
    for i in range(8):
        v, s = lin_run(img, "u512_mul_word", args + [i])
        ws.append(v)
        steps += s
    return from_words(ws), steps


def lin_ge(img: Path, left: int, right: int) -> tuple[int, int]:
    args = words(left, 8) + words(right, 8)
    return lin_run(img, "u512_ge_word", args)


def lin_div(img: Path, n: int, d: int) -> tuple[int, int, int, int]:
    args = words(n, 8) + words(d, 4)
    st, steps = lin_run(img, "u512_div_word", args + [-1])
    if st != 1:
        return st, 0, 0, steps
    qw, rs = [], steps
    for i in range(8):
        v, s = lin_run(img, "u512_div_word", args + [i])
        qw.append(v)
        rs += s
    return 1, from_words(qw[:4]), from_words(qw[4:]), rs


def rec_claim(claims: list, ident: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    print(f"  [{status}] {ident:16s} {desc}" + (f"  ({note})" if note else ""))


def main() -> int:
    claims: list[dict] = []
    print("=" * 72)
    print("  LIN u512 numeric coprocessor — external proof")
    print("=" * 72)
    ensure_c0()
    ensure_oracle()

    fm = hashlib.sha256(FULLMATH.read_bytes()).hexdigest() if FULLMATH.exists() else ""
    rec_claim(claims, "PIN-FULLMATH", "PASS" if fm else "FAIL",
              "pinned FullMath.sol (width spec, not assembly)", fm[:16])

    rng_n = 200
    import random
    rng = random.Random(20260916)
    edges = [0, 1, 2, 3, 997, 1000, 1997, 65535, 65536, (1 << 32) - 1,
             (1 << 64) - 1, 1 << 64, (1 << 128) - 1, 1 << 128, 1 << 255, U256]
    pairs = [(a, b, d) for a in edges for b in (1, 2, 997, U256) for d in (1, 2, 3, 1997, U256) if not (a == 0 and b == 0)]
    for _ in range(rng_n):
        pairs.append((rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256)))
    c11_ok = 0
    for a, b, d in pairs:
        if d == 0:
            d = 1
        p = run([str(ORACLE_BIN), "muldiv", str(a), str(b), str(d)])
        if p.returncode != 0:
            rec_claim(claims, "C11-PY", "FAIL", "oracle exit", p.stderr[:120])
            return 1
        o = parse_oracle(p.stdout)
        st, q, r = py_muldiv(a, b, d)
        if int(o["status"]) != st:
            rec_claim(claims, "C11-PY", "FAIL", f"status {o['status']} != {st}")
            return 1
        if st == 1 and (int(o["q"]) != q or int(o["r"]) != r or int(o["prod"]) != a * b):
            rec_claim(claims, "C11-PY", "FAIL", "q/r/prod mismatch")
            return 1
        if st == 1 and q * d + r != a * b:
            rec_claim(claims, "C11-PY", "FAIL", "identity")
            return 1
        c11_ok += 1
    rec_claim(claims, "C11-PY", "PASS", "16-bit && 64-bit C11 == Python int", f"n={c11_ok}")

    ge_n = 0
    ge_vecs = [(0, 0), (1, 0), (0, 1), (U512, U512 - 1), (1 << 256, 1), (U512, 0)]
    for _ in range(80):
        ge_vecs.append((rng.randrange(0, 1 << 512), rng.randrange(0, 1 << 512)))
    for L, R in ge_vecs:
        p = run([str(ORACLE_BIN), "ge", str(L), str(R)])
        if p.returncode != 0 or int(parse_oracle(p.stdout)["ge"]) != int(L >= R):
            rec_claim(claims, "C11-GE", "FAIL", f"{L}>={R}")
            return 1
        ge_n += 1
    rec_claim(claims, "C11-GE", "PASS", "512-bit ge vs Python", f"n={ge_n}")

    img, loader, img_meta = lin_image()
    rec_claim(claims, "LIN-IMAGE", "PASS", "LINBC1 freeze", loader.hex()[:16])

    sg, sg_steps = lin_run(img, "u512_self_gate", [], timeout=300)
    rec_claim(claims, "LIN-SELF", "PASS" if sg == 1 else "FAIL",
              "in-image gate 7*9/2, getAmountOut=1813, d=0, q-ovf, mul, ge",
              f"value={sg} steps={sg_steps}")
    if sg != 1:
        return 1

    records = []
    vec_id = 0

    def add_rec(op, st, a, b, d, q, r, steps, tag):
        nonlocal vec_id
        vec_id += 1
        raw = pack_lnr1(loader, vec_id, op, st, a, b, d, q, r, steps)
        leaf = hashlib.sha256(DOM_LEAF + raw).digest()
        records.append({
            "tag": tag, "op": op, "status": st, "a": str(a), "b": str(b), "d": str(d),
            "q": str(q), "r": str(r), "steps": steps, "raw_hex": raw.hex(),
            "leaf_hex": leaf.hex(), "zero_on_reject": True,
        })

    mul_vecs = [(7, 9), (U256, U256), (1 << 255, 2), (1 << 128, 1 << 128), (0, U256), (997, (1 << 256) // 997)]
    for a, b in mul_vecs:
        prod, stps = lin_mul(img, a, b)
        if prod != a * b:
            rec_claim(claims, "LIN-MUL", "FAIL", f"{a}*{b}")
            return 1
        add_rec(0, 1, a, b, 0, prod & U256, prod >> 256, stps, "mul")
    rec_claim(claims, "LIN-MUL", "PASS", "256x256->512 vs Python", f"n={len(mul_vecs)}")

    ge_lin = [(5, 3), (3, 5), (1 << 64, 1), (U512, U512), ((1 << 511) + 3, 1 << 511)]
    for L, R in ge_lin:
        g, stps = lin_ge(img, L, R)
        if g != int(L >= R):
            rec_claim(claims, "LIN-GE", "FAIL", f"{L}>={R} got {g}")
            return 1
        add_rec(1, g, L & U256, L >> 256, R & U256, R >> 256, 0, stps, "ge")
    rec_claim(claims, "LIN-GE", "PASS", "512-bit ge in LinVM", f"n={len(ge_lin)}")

    rout = ((1 << 256) + 996) // 997  # ceil(2^256/997)
    md_vecs = [
        (7, 9, 2, "7*9/2"),
        (997000, 20000, 10997000, "getAmountOut-1000-10000-20000"),
        (1 << 255, 2, 3, "2^255*2/3"),
        (997, rout, 1997, "phantom-amm"),
        (1, 1, 0, "d=0"),
        (1 << 128, 1 << 128, 1, "q-overflow"),
        (U256, U256, U256, "max*max/max"),
    ]
    for a, b, d, tag in md_vecs:
        st, q, r, stps = lin_muldiv(img, a, b, d)
        est, eq, er = py_muldiv(a, b, d)
        if st != est or (st == 1 and (q != eq or r != er)):
            rec_claim(claims, "LIN-MULDIV", "FAIL", tag, f"lin={st,q,r} py={est,eq,er}")
            return 1
        if st == 1 and q * d + r != a * b:
            rec_claim(claims, "LIN-MULDIV", "FAIL", tag + " identity")
            return 1
        add_rec(3, st, a, b, d, q if st == 1 else 0, r if st == 1 else 0, stps, tag)
    rec_claim(claims, "LIN-MULDIV", "PASS", "mulDiv + remainder identity + guards", f"n={len(md_vecs)}")

    n = (1 << 255) * 2
    st, q, r, stps = lin_div(img, n, 3)
    est, eq, er = py_div(n, 3)
    if st != 1 or q != eq or r != er:
        rec_claim(claims, "LIN-DIV", "FAIL", "512/256 2^256/3")
        return 1
    add_rec(2, st, n & U256, n >> 256, 3, q, r, stps, "div-2^256/3")
    rec_claim(claims, "LIN-DIV", "PASS", "div 512/256 remainder identity", f"q={q:x} r={r}")

    leaves = [bytes.fromhex(r["leaf_hex"]) for r in records]
    root = merkle(leaves).hex()
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "class_definition": "real published width (FullMath-style 512 intermediate) on LINVM-1; not mainnet assembly",
        "loader_digest": loader.hex(),
        "image_file_sha256": hashlib.sha256(img.read_bytes()).hexdigest(),
        "lin_source_sha256": sha256_file(LIN),
        "oracle_src_sha256": sha256_file(ORACLE_SRC),
        "fullmath_sha256": fm,
        "c0_image_meta": img_meta,
        "self_gate_steps": sg_steps,
        "merkle_root": root,
        "domains": {"leaf": "LIN:U512:LEAF:1", "node": "LIN:U512:NODE:1"},
        "record_bytes": 240,
        "claims": claims,
        "records": records,
        "not_claimed": [
            "Uniswap V3 FullMath CRT/mulmod assembly parity",
            "settle_u256_word is FullMath (it is SafeMath-width; high 256 of product => -2)",
            "full 2000-swap / 157-unfiltered campaign",
            "zk / computational soundness of Merkle (tamper-evidence + re-execution)",
            "LIN replacing Uniswap or the EVM",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    v = run([sys.executable, str(VERIFY), str(EVIDENCE)])
    ok = v.returncode == 0 and '"valid": true' in v.stdout.replace("true", " true")
    # json.dumps indent has "valid": true
    vr = json.loads(v.stdout)
    rec_claim(claims, "AUDITOR", "PASS" if vr.get("valid") else "FAIL",
              "stdlib verifier (no LIN) recomputes math+merkle", vr.get("merkle_root", "")[:16])
    evidence["claims"] = claims
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"\n  merkle {root}")
    print(f"  evidence {EVIDENCE}")
    return 0 if vr.get("valid") and all(c["status"] == "PASS" for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
