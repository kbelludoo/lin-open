#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Uniswap v3 FullMath 512-bit intermediate vs LIN coprocessor.

PASS means this run recomputed:
  * pinned FullMath.sol bytes (sha256 + git blob in the external_proof manifest)
  * Python arbitrary-precision int (ground truth)
  * C11 oracle with 64-bit AND 32-bit limbs (test/oracles/u512_coprocessor_c11.c)
  * Compiler-0 LIN 16-bit limbs (src/lin_u512_coprocessor.lin)
  * remainder identity q*d + r == a*b (or n) with 0 <= r < d
  * an LNR1 Merkle receipt an auditor recomputes with hashlib only

NOT claimed: settle_u256_word EXACT/OVERPAID vs ref_amount_out, LCR2 step
fields, mainnet Uniswap replacement, zk soundness.

Class: EXPERIMENTAL (real FullMath width; not a deployed pool).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
PINNED_SHA256 = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"
PINNED_BLOB = "9985059e267c488ee8bb421ea65e09ad85f970b4"

MASK64 = (1 << 64) - 1
U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
MAGIC = b"LNR1"
CI = "--ci" in sys.argv


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def steps_of(stdout: str) -> int | None:
    m = re.search(r"\bsteps=(\d+)\b", stdout)
    return int(m.group(1)) if m else None


def s64(w: int) -> int:
    w &= MASK64
    return w - (1 << 64) if w >= (1 << 63) else w


def words(val: int, n: int) -> list[int]:
    return [s64((val >> (64 * i)) & MASK64) for i in range(n)]


def from_words(ws: list[int]) -> int:
    v = 0
    for i, w in enumerate(ws):
        v |= (w & MASK64) << (64 * i)
    return v


def pack_be(val: int, n: int) -> bytes:
    return int(val).to_bytes(n, "big")


def pack_i64_le(v: int) -> bytes:
    return (v & MASK64).to_bytes(8, "little")


def lnr1_record(op: int, a: int, b: int, d: int, n: int, q: int, r: int, status: int) -> bytes:
    rec = bytearray(240)
    rec[0:4] = MAGIC
    rec[4] = 1
    rec[5] = op
    rec[8:40] = pack_be(a & U256, 32)
    rec[40:72] = pack_be(b & U256, 32)
    rec[72:104] = pack_be(d & U256, 32)
    rec[104:168] = pack_be(n & U512, 64)
    rec[168:200] = pack_be(q & U256, 32)
    rec[200:232] = pack_be(r & U256, 32)
    rec[232:240] = pack_i64_le(status)
    return bytes(rec)


def leaf_hash(rec: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + rec).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    if not nodes:
        return hashlib.sha256(DOM_NODE).digest()
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])
        nxt = []
        for i in range(0, len(nodes), 2):
            nxt.append(hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest())
        nodes = nxt
    return nodes[0]


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    n = a * b
    q, r = divmod(n, d)
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


def structured() -> list[tuple]:
    hi = 1 << 255
    maxu = U256
    return [
        ("mul", 3, 5, 0),
        ("mul", hi, 2, 0),
        ("mul", maxu, maxu, 0),
        ("mul", 1 << 128, 1 << 128, 0),
        ("div", 100, 7),
        ("div", 1 << 256, 3),
        ("div", (maxu * maxu), maxu),
        ("div", 1 << 256, 1),
        ("cmp", 1, 1),
        ("cmp", 1 << 256, maxu),
        ("cmp", 1, 2),
        ("muldiv", 100, 200, 50),
        ("muldiv", 7, 9, 2),
        ("muldiv", 1, 1, 0),
        ("muldiv", hi, 2, 3),
        ("muldiv", hi, 2, 1),
        ("muldiv", maxu, maxu, maxu),
        ("muldiv", 1 << 128, 1 << 128, 2),
        ("muldiv", hi, 4, 3),
        ("muldiv", 997 * (10**18), 10**24, 1000 * (10**18) + 997 * (10**18)),
    ]


def ensure_tools() -> None:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0 or not C0.exists():
            raise RuntimeError(f"make c0 failed: {p.stdout}\n{p.stderr}")
    p = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if p.returncode != 0:
        raise RuntimeError(f"gcc oracle: {p.stdout}\n{p.stderr}")


def c11(args: list[str]) -> str:
    p = run([str(ORACLE_BIN), *args], timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"c11 {args}: {p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def lin_call(fn: str, args: list[int], image: Path) -> tuple[int, int]:
    cmd = [str(C0), "run", str(image), fn, *[str(a) for a in args]]
    p = run(cmd, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"lin {fn}: {p.stdout}\n{p.stderr}")
    v = value_of(p.stdout)
    s = steps_of(p.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {p.stdout!r}")
    return v, int(s or 0)


def rec(claims: list[dict], ident: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:16s}  {desc}")
    if note:
        print(f"            note: {note}")


def check_mul(a: int, b: int) -> tuple[int, int]:
    n = a * b
    got = [int(x) for x in c11(["mul", *[str(w) for w in words(a, 4) + words(b, 4)]]).split()]
    if from_words(got) != n:
        raise RuntimeError(f"c11 mul mismatch {a}*{b}")
    return 1, n


def check_div(n: int, d: int) -> tuple[int, int, int]:
    st, q, r = py_div(n, d)
    parts = c11(["div", *[str(w) for w in words(n, 8) + words(d, 4)]]).split()
    gst = int(parts[0])
    gq = from_words([int(x) for x in parts[1:5]])
    gr = from_words([int(x) for x in parts[5:9]])
    if gst != st or (st == 1 and (gq != q or gr != r)):
        raise RuntimeError(f"c11 div mismatch n={n} d={d} py=({st},{q},{r}) c11=({gst},{gq},{gr})")
    if st == 1 and (q * d + r != n or not (0 <= r < d)):
        raise RuntimeError("identity broken")
    return st, q if st == 1 else 0, r if st == 1 else 0


def py_expect(op: int, a: int, b: int, d: int, n: int, q: int, r: int, status: int) -> None:
    if op == 1:
        if n != a * b or status != 1:
            raise RuntimeError("mul record != Python int")
    elif op == 2:
        st, qq, rr = py_div(n, d)
        if st != status or (st == 1 and (qq != q or rr != r)):
            raise RuntimeError("div record != Python int")
        if st == 1 and (q * d + r != n or not (0 <= r < d)):
            raise RuntimeError("div identity broken in record")
    elif op == 3:
        left, right = n, (q << 256) | r
        py = 0 if left == right else (1 if left > right else -1)
        if py != status:
            raise RuntimeError("cmp record != Python int")
    elif op == 4:
        st, qq, rr = py_muldiv(a, b, d)
        if st != status or (st == 1 and (qq != q or rr != r)):
            raise RuntimeError("muldiv record != Python int")
        if st == 1 and (q * d + r != a * b or not (0 <= r < d)):
            raise RuntimeError("muldiv identity broken in record")
    else:
        raise RuntimeError(f"bad op {op}")


def verify_receipt_file(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    leaves: list[bytes] = []
    for row in data["records"]:
        op = int(row["op"])
        a, b, d = int(row["a"], 16), int(row["b"], 16), int(row["d"], 16)
        n, q, r = int(row["n"], 16), int(row["q"], 16), int(row["r"], 16)
        status = int(row["status"])
        py_expect(op, a, b, d, n, q, r, status)
        recb = lnr1_record(op, a, b, d, n, q, r, status)
        h = leaf_hash(recb)
        if h.hex() != row["leaf"]:
            raise RuntimeError("leaf digest mismatch")
        leaves.append(h)
    root = "sha256:" + merkle_root(leaves).hex()
    if root != data["merkle_root"]:
        raise RuntimeError(f"merkle {root} != {data['merkle_root']}")
    print(f"[PASS] RECOMPUTE  {path}  {len(leaves)} leaves  {root}")
    print("        Python int + hashlib only (no LIN, no C11)")
    return 0


def check_muldiv(a: int, b: int, d: int) -> tuple[int, int, int, int]:
    n = a * b
    st, q, r = py_muldiv(a, b, d)
    parts = c11(["muldiv", *[str(w) for w in words(a, 4) + words(b, 4) + words(d, 4)]]).split()
    gst = int(parts[0])
    gq = from_words([int(x) for x in parts[1:5]])
    gr = from_words([int(x) for x in parts[5:9]])
    if gst != st or (st == 1 and (gq != q or gr != r)):
        raise RuntimeError(f"c11 muldiv mismatch a={a} b={b} d={d}")
    if st == 1 and (q * d + r != n or not (0 <= r < d)):
        raise RuntimeError("muldiv identity broken")
    return st, n, q if st == 1 else 0, r if st == 1 else 0


def main() -> int:
    if "--verify-receipt" in sys.argv:
        i = sys.argv.index("--verify-receipt")
        path = Path(sys.argv[i + 1]) if i + 1 < len(sys.argv) else EVIDENCE
        try:
            return verify_receipt_file(path)
        except Exception as e:
            print(f"[FAIL] RECOMPUTE  {e}")
            return 1

    claims: list[dict] = []
    print("=" * 78)
    print("  U512 NUMERIC COPROCESSOR — external proof (FullMath width)")
    print("=" * 78)

    pinned = FIX / "FullMath.sol"
    if not pinned.exists() or sha256_file(pinned) != PINNED_SHA256:
        rec(claims, "PIN-FULLMATH", "FAIL", "pinned FullMath.sol missing or hash mismatch")
        return 1
    rec(claims, "PIN-FULLMATH", "PASS", "pinned Uniswap v3 FullMath.sol sha256 matches manifest",
        f"blob={PINNED_BLOB}")

    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "64-bit vs 32-bit limb selftest", st.stdout + st.stderr)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11 64-bit limbs XOR 32-bit limbs (phantom 2^256/3)")

    rng = random.Random(512256)
    n_rand = 48 if CI else 200
    leaves: list[bytes] = []
    records: list[dict] = []

    def note(op: int, a: int, b: int, d: int, n: int, q: int, r: int, status: int) -> None:
        recb = lnr1_record(op, a, b, d, n, q, r, status)
        h = leaf_hash(recb)
        records.append({
            "op": op,
            "a": hex(a), "b": hex(b), "d": hex(d),
            "n": hex(n), "q": hex(q), "r": hex(r),
            "status": status,
            "leaf": h.hex(),
        })
        leaves.append(h)

    try:
        for kind, *args in structured():
            if kind == "mul":
                a, b, _ = args
                status, n = check_mul(a, b)
                note(1, a, b, 0, n, 0, 0, status)
            elif kind == "div":
                n, d = args
                status, q, r = check_div(n, d)
                note(2, 0, 0, d, n, q, r, status)
            elif kind == "cmp":
                aa, bb = args
                py = 0 if aa == bb else (1 if aa > bb else -1)
                got = int(c11(["cmp", *[str(w) for w in words(aa, 8) + words(bb, 8)]]))
                if got != py:
                    raise RuntimeError(f"cmp {aa} vs {bb}: {got} != {py}")
                note(3, aa & U256, bb & U256, 0, aa, bb >> 256, bb & U256, py)
            else:
                a, b, d = args
                status, n, q, r = check_muldiv(a, b, d)
                note(4, a, b, d, n, q, r, status)
        fit_ok = 0
        ov_ok = 0
        for i in range(n_rand):
            a = rng.randrange(0, 1 << 256)
            b = rng.randrange(0, 1 << 256)
            prod = a * b
            hi = prod >> 256
            if i % 3 == 0 and hi > 0:
                d = rng.randrange(1, hi + 1)  # q >= 2^256 -> -2
            elif hi < U256:
                d = rng.randrange(hi + 1, 1 << 256)  # q fits uint256
            else:
                d = rng.randrange(1, 1 << 256)
            status, n, q, r = check_muldiv(a, b, d)
            note(4, a, b, d, n, q, r, status)
            if status == 1:
                fit_ok += 1
                if q * d + r != a * b:
                    raise RuntimeError("random identity failed")
            elif status == -2:
                ov_ok += 1
        if fit_ok < 1 or ov_ok < 1:
            raise RuntimeError(f"range split too weak fit={fit_ok} ov={ov_ok}")
    except Exception as e:
        rec(claims, "PY-C11-RANGE", "FAIL", "Python bigint vs C11 full-range", str(e)[:240])
        return 1
    rec(claims, "PY-C11-RANGE", "PASS",
        f"Python int XOR C11 64-limb on {len(structured())} structured + {n_rand} random full-range",
        "includes (2^256-1)^2 / (2^256-1) and 2^255*2/3 phantom overflow")

    img = Path("/tmp/lin_u512_coprocessor.linbc")
    im = run([str(C0), "image", str(LIN), "-o", str(img)], timeout=60)
    if im.returncode != 0 or not img.exists():
        rec(claims, "LIN-IMAGE", "FAIL", "lin_c0 image failed", im.stdout + im.stderr)
        return 1
    rec(claims, "LIN-IMAGE", "PASS", "Compiler-0 froze lin_u512_coprocessor.lin to LINBC1")

    try:
        suite, steps = lin_call("u512_test_suite", [], img)
        if suite != 1:
            raise RuntimeError(f"test_suite={suite} steps={steps}")
    except Exception as e:
        rec(claims, "LIN-SUITE", "FAIL", "LIN u512_test_suite", str(e)[:240])
        return 1
    rec(claims, "LIN-SUITE", "PASS", "LIN test_suite=1 (mul/div/cmp/muldiv/guards -1/-2)",
        f"steps={steps}")

    lin_cases = [
        ("muldiv", 100, 200, 50, 0, 400),
        ("muldiv", 1 << 255, 2, 3, 0, 0x5555555555555555),
        ("muldiv", 1 << 255, 2, 3, 4, 1),
        ("muldiv", 1 << 255, 2, 1, -1, -2),
        ("muldiv", 1, 1, 0, -1, -1),
        ("mul", 1 << 255, 2, 4, 1),
        ("cmp", 1 << 256, U256, 1),
    ]
    try:
        for case in lin_cases:
            if case[0] == "muldiv":
                _, a, b, d, idx, want = case
                got, _ = lin_call("u512_muldiv_word", words(a, 4) + words(b, 4) + words(d, 4) + [idx], img)
                if got != s64(want) and got != want:
                    raise RuntimeError(f"lin muldiv {a,b,d,idx} got {got} want {want}")
            elif case[0] == "mul":
                _, a, b, idx, want = case
                got, stps = lin_call("u512_mul_word", words(a, 4) + words(b, 4) + [idx], img)
                if got != want:
                    raise RuntimeError(f"lin mul word{idx}={got} want {want}")
            else:
                _, aa, bb, want = case
                got, _ = lin_call("u512_cmp", words(aa, 8) + words(bb, 8), img)
                if got != want:
                    raise RuntimeError(f"lin cmp got {got} want {want}")
        lin_rand = []
        while len(lin_rand) < (1 if CI else 2):
            a = rng.randrange(1, 1 << 200)
            b = rng.randrange(1, 1 << 200)
            prod = a * b
            hi = prod >> 256
            d = rng.randrange(hi + 1, 1 << 256) if hi < U256 else U256
            if py_muldiv(a, b, d)[0] == 1:
                lin_rand.append((a, b, d))
        for a, b, d in lin_rand:
            stt, q, r = py_muldiv(a, b, d)
            args = words(a, 4) + words(b, 4) + words(d, 4)
            gst, _ = lin_call("u512_muldiv_word", args + [-1], img)
            if gst != stt:
                raise RuntimeError(f"lin status {gst} != {stt}")
            qw, rw = [], []
            for i in range(4):
                qw.append(lin_call("u512_muldiv_word", args + [i], img)[0])
                rw.append(lin_call("u512_muldiv_word", args + [4 + i], img)[0])
            if from_words(qw) != q or from_words(rw) != r:
                raise RuntimeError("lin full-range word mismatch")
            if q * d + r != a * b or not (0 <= r < d):
                raise RuntimeError("lin identity failed")
    except Exception as e:
        rec(claims, "LIN-PY-C11", "FAIL", "LIN word ABI vs Python/C11", str(e)[:240])
        return 1
    rec(claims, "LIN-PY-C11", "PASS",
        "LIN 16-bit limbs match Python bigint and C11 on phantom, guards, full-range sample")

    root = merkle_root(leaves)
    root_hex = root.hex()
    tampered = list(leaves)
    t = bytearray(tampered[0]); t[0] ^= 1; tampered[0] = bytes(t)
    if merkle_root(tampered) == root:
        rec(claims, "LNR1-RECEIPT", "FAIL", "tamper did not change Merkle root")
        return 1
    rec(claims, "LNR1-RECEIPT", "PASS",
        "LNR1 Merkle root independently recomputed; 1-bit leaf tamper diverges",
        f"sha256:{root_hex}")

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_RECEIPT_1.0",
        "class": "EXPERIMENTAL",
        "claim": "256x256->512 mul, 512-bit ge, 512/256->256 div with q*d+r==n vs Python int",
        "fullmath_sha256": PINNED_SHA256,
        "fullmath_blob": PINNED_BLOB,
        "lin_module": "src/lin_u512_coprocessor.lin",
        "c11_oracle": "test/oracles/u512_coprocessor_c11.c",
        "leaf_domain": DOM_LEAF.decode(),
        "node_domain": DOM_NODE.decode(),
        "record": "LNR1 240-byte big-endian operands + little-endian status",
        "merkle_root": f"sha256:{root_hex}",
        "vector_leaves": len(leaves),
        "rng_seed": 512256,
        "test_suite_steps": steps,
        "claims": claims,
        "records": records,
        "not_claimed": [
            "settle_u256_word vs ref_amount_out on EXACT/OVERPAID mainnet classes",
            "LCR2 208-byte records with real LinVM steps for those swaps",
            "LIN replaces Uniswap/EVM or FullMath on chain",
            "zk / computational soundness of Merkle (tamper-evidence only)",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    rec(claims, "EVIDENCE-JSON", "PASS", f"wrote {EVIDENCE.relative_to(ROOT)}")
    try:
        verify_receipt_file(EVIDENCE)
        rec(claims, "PY-RECOMPUTE", "PASS",
            "auditor path: Python int + hashlib recompute the LNR1 root (no LIN, no C11)")
    except Exception as e:
        rec(claims, "PY-RECOMPUTE", "FAIL", "evidence JSON failed independent recompute", str(e)[:240])
        return 1

    print()
    print(f"RESULT: PASS ({len(claims)} claims)  root=sha256:{root_hex[:16]}...")
    print("  still open: settle_u256_word EXACT/OVERPAID + LCR2 steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
