#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN Toom-3 + Goldschmidt + OpenSSL auditor for schema 1.16 evidence.json.

Python only decodes JSON / hex. Toom-3 reconstructs n==a*b.
Goldschmidt checks q*d+r==n. OpenSSL dgst recomputes the LRI1 Merkle
root (FIPS 180-4 abc vector). No LinVM, no gcc, no rustc.

  python3 examples/u512_coprocessor/verify_u512_toom3.py \\
      examples/u512_coprocessor/u512_coprocessor_evidence.json
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test" / "oracles"))
from u512_toom3_goldschmidt import ge_limbs, identity512, le256, mul256, muldiv256  # noqa: E402

SCHEMA = "LIN_U512_COPROCESSOR_EVIDENCE_1.16"
RI_LEAF = b"LIN:U512:RI:LEAF:1"
RI_NODE = b"LIN:U512:RI:NODE:1"
UMAX = (1 << 256) - 1
N = 4
MASK64 = 0xFFFFFFFFFFFFFFFF
FIPS_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def fail(msg: str) -> int:
    print("FAIL", msg)
    return 1


def parse_int(v) -> int:
    return v if isinstance(v, int) else int(v, 0)


def limbs_eq_int(limbs: list[int], v: int) -> bool:
    x = int(v)
    for i in range(len(limbs)):
        if (limbs[i] & MASK64) != (x & MASK64):
            return False
        x >>= 64
    return x == 0


def openssl_sha256(data: bytes) -> bytes:
    p = subprocess.run(
        ["openssl", "dgst", "-sha256", "-binary"],
        input=data, capture_output=True, timeout=30, check=False,
    )
    if p.returncode != 0 or len(p.stdout) != 32:
        raise RuntimeError("openssl dgst failed")
    return p.stdout


def be32(x: int) -> bytes:
    return int(x).to_bytes(32, "big")


def lri1(src_d: bytes, run_id: int, vid: int, n: int, d: int, q: int, r: int,
         steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LRI1"
    raw[4] = 1
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(n & UMAX)
    raw[88:120] = be32(n >> 256)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle_ossl(recs: list[bytes], leaf_d: bytes, node_d: bytes) -> bytes:
    nodes = [openssl_sha256(leaf_d + r) for r in recs]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            L = nodes[i]
            R = nodes[i + 1] if i + 1 < len(nodes) else L
            nxt.append(openssl_sha256(node_d + L + R))
        nodes = nxt
    return nodes[0]


def bind_muldiv(ain: int, rin: int, rout: int, aout: int) -> bool:
    fee, den = ain * 997, rin * 1000 + ain * 997
    if fee > UMAX or den > UMAX:
        return False
    st, q, _rem, _n = muldiv256(le256(fee), le256(rout), le256(den))
    return st == 1 and limbs_eq_int(q, aout)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_toom3.py <evidence.json>")
        return 2
    abc = openssl_sha256(b"abc").hex()
    if abc != FIPS_ABC:
        return fail(f"sha256 fips abc {abc}")
    ev = json.loads(Path(sys.argv[1]).read_text())
    if ev.get("schema") != SCHEMA:
        return fail("schema")
    if ev.get("class") != "EXPERIMENTAL":
        return fail("class")
    src_d = bytes.fromhex(ev["pins"]["lin_src"])
    run_r = int(ev.get("lri1_run_id") or 5)
    leaves = ev.get("lri1_leaves") or []
    if len(leaves) < 8:
        return fail(f"need 8 LRI1 got {len(leaves)}")
    recs = []
    names = []
    for i, leaf in enumerate(leaves):
        a, b, d = parse_int(leaf["a"]), parse_int(leaf["b"]), parse_int(leaf["d"])
        n, q, r = parse_int(leaf["n"]), parse_int(leaf["q"]), parse_int(leaf["r"])
        steps, status = int(leaf["steps"]), int(leaf["status"])
        if steps == 0 or status != 1 or d == 0:
            return fail(leaf.get("name") or "lri1")
        st, prod = mul256(le256(a), le256(b))
        nlo, nhi = n & UMAX, n >> 256
        if st != 1 or not limbs_eq_int(prod[:N], nlo) or not limbs_eq_int(prod[N:], nhi):
            return fail(f"{leaf.get('name')} n!=a*b toom3")
        st, qq, rem, nn = muldiv256(le256(a), le256(b), le256(d))
        if st != 1 or not limbs_eq_int(qq, q):
            return fail(f"{leaf.get('name')} q")
        if not limbs_eq_int(rem, r):
            return fail(f"{leaf.get('name')} r")
        if not identity512(nn, qq, le256(d), rem):
            return fail(f"{leaf.get('name')} identity")
        recs.append(lri1(src_d, run_r, i, n, d, q, r, steps, status))
        names.append(leaf.get("name") or "?")
    root = merkle_ossl(recs, RI_LEAF, RI_NODE).hex()
    if root != ev.get("lri1_merkle"):
        return fail(f"lri1 merkle {root} != {ev.get('lri1_merkle')}")

    n_ex = n_ov = 0
    for leaf in ev.get("lcr2_leaves") or []:
        cls = leaf.get("class")
        if cls not in ("EXACT_INPUT", "OVERPAID_INPUT"):
            continue
        ain, rin = parse_int(leaf["ain"]), parse_int(leaf["rin"])
        rout, aout = parse_int(leaf["rout"]), parse_int(leaf["aout"])
        if int(leaf["steps"]) == 0 or int(leaf["status"]) != 1:
            return fail(f"LCR2 {cls} steps/status")
        if not bind_muldiv(ain, rin, rout, aout):
            return fail(f"LCR2 {cls} toom3 bind")
        n_ex += cls == "EXACT_INPUT"
        n_ov += cls == "OVERPAID_INPUT"
    if n_ex < 3 or n_ov < 3:
        return fail(f"LCR2 counts exact={n_ex} over={n_ov}")

    n_ph = 0
    for leaf in ev.get("lcr2_full_leaves") or []:
        if leaf.get("class") != "PHANTOM_APPROVE":
            continue
        ain, rin = parse_int(leaf["ain"]), parse_int(leaf["rin"])
        rout, aout = parse_int(leaf["rout"]), parse_int(leaf["aout"])
        if int(leaf["status"]) != 1 or not bind_muldiv(ain, rin, rout, aout):
            return fail("PHANTOM_APPROVE")
        n_ph += 1
    if n_ph < 1:
        return fail("need PHANTOM_APPROVE")

    A = [0] * 8
    B = [MASK64] * 4 + [0] * 4
    A[4] = 1
    if not ge_limbs(A, B):
        return fail("ge512 2^256 >= 2^256-1")

    print("PASS toom3_goldschmidt remainder identity + openssl merkle")
    print("lri1_toom3_identity", len(names))
    print("lri1_match", root)
    print("lcr2_toom3_bind", n_ex + n_ov)
    print("lcr2_full_phantom", n_ph)
    print("fips_abc", abc)
    print("names", ",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
