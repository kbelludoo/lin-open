#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: LIN u512 numeric coprocessor vs Python int vs C11 limbs.

Proves (this run):
  * 256x256->512 mul with carry
  * unsigned ge on 512-bit values
  * 512/256 restoring div with remainder identity q*d+r == n
  * FullMath-width mulDiv: d=0 -> -1, q>=2^256 -> -2, phantom 2^255*2/3 APPROVES

Does not prove: Uniswap V2/V3 pool replacement, zk soundness, settle_u256_word
FullMath semantics (that engine still fail-closes when fee*reserve_out >= 2^256).

Auditor path (no LIN, no gcc): --verify-receipt <evidence.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
GOLD = ROOT / "test" / "fixtures" / "external_proof" / "u512_golden_vectors.json"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
MANIFEST = ROOT / "test" / "fixtures" / "external_proof" / "manifest.json"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
IMG = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor.linbc"

U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
M64 = (1 << 64) - 1
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
TAG = b"LIN:U512:v1" + b"\x00" * 5
PINNED_FULLMATH = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def words(x: int, n: int = 4) -> list[int]:
    ws = [(x >> (64 * i)) & M64 for i in range(n)]
    return [w - (1 << 64) if w >= (1 << 63) else w for w in ws]


def be32(x: int) -> bytes:
    return (x & U256).to_bytes(32, "big")


def pack_lnr1(op: int, status: int, steps: int, digest: bytes, a: int, b: int, d: int, q: int, r: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = op
    struct.pack_into("<q", raw, 8, status)
    struct.pack_into("<Q", raw, 16, steps)
    raw[32:64] = digest
    raw[64:96] = be32(a)
    raw[96:128] = be32(b)
    raw[128:160] = be32(d)
    raw[160:192] = be32(q)
    raw[192:224] = be32(r)
    raw[224:240] = TAG
    return bytes(raw)


def unpack_lnr1(raw: bytes) -> dict:
    if len(raw) != 240 or raw[0:4] != b"LNR1" or raw[4] != 1:
        raise ValueError("bad LNR1")
    return {
        "op": raw[5],
        "status": struct.unpack_from("<q", raw, 8)[0],
        "steps": struct.unpack_from("<Q", raw, 16)[0],
        "digest": raw[32:64].hex(),
        "a": int.from_bytes(raw[64:96], "big"),
        "b": int.from_bytes(raw[96:128], "big"),
        "d": int.from_bytes(raw[128:160], "big"),
        "q": int.from_bytes(raw[160:192], "big"),
        "r": int.from_bytes(raw[192:224], "big"),
    }


def leaf_hash(rec: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + rec).digest()


def parent_hash(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(DOM_NODE + l + r).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        raise ValueError("no leaves")
    nodes = list(leaves)
    while len(nodes) > 1:
        if len(nodes) & 1:
            nodes.append(nodes[-1])
        nodes = [parent_hash(nodes[i], nodes[i + 1]) for i in range(0, len(nodes), 2)]
    return nodes[0]


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int, int]:
    n = a * b
    if d == 0:
        return -1, n, 0, 0
    q, r = divmod(n, d)
    if q > U256:
        return -2, n, 0, 0
    return 1, n, q, r


def math_ok(rec: dict) -> bool:
    op, st, a, b, d, q, r = rec["op"], rec["status"], rec["a"], rec["b"], rec["d"], rec["q"], rec["r"]
    if op == 1:
        A, B = a + (b << 256), d + (q << 256)
        ge = 1 if A >= B else 0
        return st == ge and r == ge
    if op == 2:
        return st == 1 and a * b == q + (r << 256)
    n = a + (b << 256) if op == 3 else a * b
    if d == 0:
        return st == -1
    qq, rr = divmod(n, d)
    if qq > U256:
        return st == -2
    return st == 1 and q == qq and r == rr and q * d + r == n


def verify_receipt(path: Path) -> int:
    ev = json.loads(path.read_text())
    recs = []
    for h in ev["lnr1"]["records_hex"]:
        raw = bytes.fromhex(h)
        rec = unpack_lnr1(raw)
        if not math_ok(rec):
            print("FAIL math", rec)
            return 1
        if rec["steps"] == 0:
            print("FAIL steps=0")
            return 1
        recs.append(raw)
    root = merkle_root([leaf_hash(r) for r in recs]).hex()
    if root != ev["lnr1"]["root"]:
        print("FAIL merkle", root, ev["lnr1"]["root"])
        return 1
    print("PASS: %d LNR1 records, root=%s (hashlib + Python int, no LIN)" % (len(recs), root))
    return 0


def ensure_tools() -> None:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
    if not RUN.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "bin/lin_bc1_run"], timeout=120)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
    p = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if p.returncode != 0:
        raise RuntimeError(p.stderr + p.stdout)


class LinImg:
    def __init__(self):
        IMG.parent.mkdir(parents=True, exist_ok=True)
        p = run([str(C0), "image", str(LIN), "-o", str(IMG)], timeout=60)
        if p.returncode != 0:
            raise RuntimeError(p.stdout + p.stderr)
        v = run([str(RUN), str(IMG), "--verify"])
        m = re.search(r'img_sha256="([0-9a-f]+)"', v.stdout)
        if not m:
            raise RuntimeError(v.stdout)
        self.digest = bytes.fromhex(m.group(1))

    def call(self, fn: str, args: list[int]) -> tuple[int, int]:
        p = run([str(RUN), str(IMG), fn, *[str(a) for a in args]], timeout=60)
        if p.returncode != 0 or 'status="EVALUATED"' not in p.stdout:
            raise RuntimeError(p.stdout + p.stderr)
        return int(re.search(r"result=(-?\d+)", p.stdout).group(1)), int(re.search(r"steps=(\d+)", p.stdout).group(1))

    def gather(self, a: int, b: int, d: int, idxs: list[int]) -> tuple[list[int], int]:
        args0 = words(a) + words(b) + words(d)
        out, steps = [], 0
        for i in idxs:
            v, s = self.call("u512_muldiv_word", args0 + [i])
            out.append(v & M64)
            steps += s
        return out, steps


def oracle_line(kind: str, *hexes: str) -> str:
    p = run([str(ORACLE_BIN), kind, *hexes])
    if p.returncode != 0:
        raise RuntimeError(p.stderr + p.stdout)
    return p.stdout.strip()


def hx(x: int, nbytes: int) -> str:
    return x.to_bytes(nbytes, "big").hex()


def claim(cid, status, desc, note=""):
    return {"id": cid, "status": status, "description": desc, "note": note}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-receipt", default=None)
    ap.add_argument("--random", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20260916)
    args = ap.parse_args()
    if args.verify_receipt:
        return verify_receipt(Path(args.verify_receipt))

    ensure_tools()
    claims = []
    gold = json.loads(GOLD.read_text())
    fm = sha256_file(FULLMATH)
    man = json.loads(MANIFEST.read_text())["sources"]["FullMath.sol"]["file_sha256"]
    claims.append(claim("PIN-FULLMATH", "PASS" if fm == PINNED_FULLMATH == man else "FAIL",
                        "pinned FullMath.sol sha256", fm))

    st = run([str(ORACLE_BIN), "selftest"])
    claims.append(claim("C11-SELFTEST", "PASS" if st.returncode == 0 and "PASS" in st.stdout else "FAIL",
                        "C11 32-bit limbs agree with __int128 64-bit mul", st.stdout.strip()))

    chk = run([str(C0), "check", str(LIN)])
    claims.append(claim("LIN-CHECK", "PASS" if chk.returncode == 0 and "typecheck=passed" in chk.stdout else "FAIL",
                        "Compiler 0 typecheck of src/lin_u512_coprocessor.lin"))

    lin = LinImg()
    suite_v, suite_s = lin.call("u512_test_suite", [])
    claims.append(claim("LIN-SUITE", "PASS" if suite_v == 1 else "FAIL",
                        "u512_test_suite == 1 (includes phantom overflow)", "steps=%d value=%d" % (suite_s, suite_v)))

    records = []
    mismatches = []

    def add_mul(a, b):
        n_py = a * b
        o = oracle_line("mul", hx(a, 32), hx(b, 32))
        n_c = int(o.split("n=")[1], 16)
        ws, steps = lin.gather(a, b, 1, list(range(8, 16)))
        n_lin = sum(ws[i] << (64 * i) for i in range(8))
        if not (n_py == n_c == n_lin):
            mismatches.append(("mul", a, b, n_py, n_c, n_lin))
        records.append(pack_lnr1(2, 1, steps, lin.digest, a, b, 0, n_lin & U256, n_lin >> 256))

    def add_ge(a, b):
        ge_py = 1 if a >= b else 0
        o = oracle_line("ge", hx(a, 64), hx(b, 64))
        ge_c = int(o.split("ge=")[1])
        av, bv = words(a, 8), words(b, 8)
        ge_lin, steps = lin.call("u512_ge512", av + bv)
        if not (ge_py == ge_c == ge_lin):
            mismatches.append(("ge", a, b, ge_py, ge_c, ge_lin))
        records.append(pack_lnr1(1, ge_lin, steps, lin.digest, a & U256, a >> 256, b & U256, b >> 256, ge_lin))

    def add_muldiv(a, b, d):
        st_py, n_py, q_py, r_py = py_muldiv(a, b, d)
        o = oracle_line("muldiv", hx(a, 32), hx(b, 32), hx(d, 32))
        st_c = int(re.search(r"status=(-?\d+)", o).group(1))
        st_lin, s0 = lin.call("u512_muldiv_word", words(a) + words(b) + words(d) + [-1])
        steps = s0
        q_lin = r_lin = 0
        if st_lin == 1:
            qw, sq = lin.gather(a, b, d, [0, 1, 2, 3])
            rw, sr = lin.gather(a, b, d, [4, 5, 6, 7])
            steps += sq + sr
            q_lin = sum(qw[i] << (64 * i) for i in range(4))
            r_lin = sum(rw[i] << (64 * i) for i in range(4))
            if q_lin * d + r_lin != n_py:
                mismatches.append(("rem", a, b, d, q_lin, r_lin, n_py))
        if not (st_py == st_c == st_lin) or (st_lin == 1 and (q_lin, r_lin) != (q_py, r_py)):
            mismatches.append(("muldiv", a, b, d, st_py, st_c, st_lin, q_py, q_lin))
        records.append(pack_lnr1(4, st_lin, steps, lin.digest, a, b, d, q_lin, r_lin))

    for v in gold["mul"]:
        add_mul(int(v["a"]), int(v["b"]))
    for v in gold["ge512"]:
        add_ge(int(v["a"]), int(v["b"]))
    for v in gold["muldiv"]:
        add_muldiv(int(v["a"]), int(v["b"]), int(v["d"]))

    rng = random.Random(args.seed)
    for _ in range(args.random):
        add_mul(rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256))
        add_ge(rng.randrange(0, 1 << 512), rng.randrange(0, 1 << 512))
        add_muldiv(rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256))
        n = rng.randrange(0, 1 << 512)
        d = rng.randrange(1, 1 << 256)
        o = oracle_line("div", hx(n, 64), hx(d, 32))
        st_c = int(re.search(r"status=(-?\d+)", o).group(1))
        qn, rn = divmod(n, d)
        want = -2 if qn > U256 else 1
        if st_c != want:
            mismatches.append(("div-c-py", n, d, want, st_c))
        elif want == 1:
            q_c = int(o.split("q=")[1].split()[0], 16)
            r_c = int(o.split("r=")[1], 16)
            if q_c != qn or r_c != rn or qn * d + rn != n:
                mismatches.append(("div-id", n, d, q_c, r_c))

    claims.append(claim("VEC-CONSENSUS", "PASS" if not mismatches else "FAIL",
                        "golden+random: Python int == C11 == LIN", "mismatches=%d records=%d" % (len(mismatches), len(records))))
    claims.append(claim("REM-IDENTITY", "PASS" if not any(m[0] == "rem" for m in mismatches) else "FAIL",
                        "q*d+r == a*b on every approved mulDiv"))
    claims.append(claim("DIV-FULLRANGE", "PASS" if not any(m[0].startswith("div") for m in mismatches) else "FAIL",
                        "C11 restoring 512/256 vs Python int on arbitrary 512-bit numerators"))

    # Phantom is in golden; name it.
    claims.append(claim("PHANTOM", "PASS" if not mismatches else "FAIL",
                        "2^255 * 2 / 3 approves on the 512-bit coprocessor (product 2^256)"))

    root = merkle_root([leaf_hash(r) for r in records]).hex()
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "image_sha256": lin.digest.hex(),
        "fullmath_sha256": fm,
        "claims": claims,
        "mismatches_head": [list(map(str, m))[:8] for m in mismatches[:5]],
        "lnr1": {
            "domain_leaf": DOM_LEAF.decode(),
            "domain_node": DOM_NODE.decode(),
            "record_bytes": 240,
            "count": len(records),
            "root": root,
            "records_hex": [r.hex() for r in records],
        },
        "not_proved": [
            "settle_u256_word FullMath semantics (high-256 of fee*reserve_out still fail-closes -2)",
            "Uniswap/EVM replacement",
            "computational soundness of Merkle (tamper-evidence + recompute only)",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    vr = verify_receipt(EVIDENCE)
    claims.append(claim("RECEIPT-AUDIT", "PASS" if vr == 0 else "FAIL",
                        "stdlib hashlib auditor recomputes LNR1 Merkle + Python int math"))
    evidence["claims"] = claims
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")

    failed = [c for c in claims if c["status"] == "FAIL"]
    for c in claims:
        print("  [%s] %s  %s  %s" % (c["status"], c["id"], c["description"], c["note"]))
    print("LNR1 root", root)
    if mismatches:
        print("mismatches", mismatches[:3])
    return 1 if failed or mismatches else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAIL exception:", e)
        sys.exit(1)
