#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared packing/oracles for the u512 coprocessor harness (not the zero-LIN verifier)."""
from __future__ import annotations

import hashlib
import re
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
U256 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
U512A = ROOT / "examples" / "defi_settlement_proof" / "u512_uniswap_v2_core.lin"
PIN_FM = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
LCR_LEAF = b"LIN:LEAF:1"
LCR_NODE = b"LIN:NODE:1"
GE_LEAF = b"LIN:U512:GE:LEAF:1"
GE_NODE = b"LIN:U512:GE:NODE:1"
BN_SRC = ROOT / "test" / "oracles" / "u512_openssl_bn.c"
UMAX = (1 << 256) - 1
OP = {"MUL": 1, "MULDIV": 2}


def run(cmd: list[str], inp: str | bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    text = not isinstance(inp, (bytes, bytearray))
    return subprocess.run(cmd, input=inp, capture_output=True, text=text, timeout=timeout, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def value_steps(out: str) -> tuple[int, int]:
    m = re.search(r"\bvalue=(-?\d+)\b", out)
    s = re.search(r"\bsteps=(\d+)\b", out)
    if not m or not s:
        raise RuntimeError(out)
    return int(m.group(1)), int(s.group(1))


def words(x: int, n: int = 4) -> list[int]:
    out = []
    for _ in range(n):
        w = x & ((1 << 64) - 1)
        out.append(w - (1 << 64) if w >= (1 << 63) else w)
        x >>= 64
    return out


def from_words(ws: list[int]) -> int:
    v = 0
    for i, w in enumerate(ws):
        v |= (w + (1 << 64) if w < 0 else w) << (64 * i)
    return v


def lin(fn: str, *args: int, src: Path = LIN, timeout: int = 120) -> tuple[int, int]:
    p = run([str(C0), "vm", str(src), fn, *[str(a) for a in args]], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(str(p.stdout) + str(p.stderr))
    return value_steps(p.stdout)


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(a * b, d)
    if q > UMAX:
        return -2, 0, 0
    return 1, q, r


def ref_amount_out(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > UMAX or den > UMAX or num > UMAX:
        return -2, 0
    return 1, num // den


def ref_amount_out_full(ain: int, rin: int, rout: int) -> tuple[int, int]:
    """Uniswap v2 getAmountOut with a 512-bit numerator (fee*rout)."""
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    den = rin * 1000 + fee
    if fee > UMAX or den > UMAX:
        return -2, 0
    q = (fee * rout) // den
    if q > UMAX:
        return -2, 0
    return 1, q


def node_bin() -> str:
    return shutil.which("node") or "/exec-daemon/node"


def settle_u512(ain: int, rin: int, rout: int, nwords: int = 4,
                timeout: int = 180) -> tuple[int, int, int]:
    st, ss = lin("settle_u512_swap", *words(ain), *words(rin), *words(rout), -1,
                 src=U512A, timeout=timeout)
    if st != 1:
        return st, 0, ss
    ws: list[int] = []
    s0 = ss
    for i in range(max(1, nwords)):
        wi, si = lin("settle_u512_swap", *words(ain), *words(rin), *words(rout), i,
                     src=U512A, timeout=timeout)
        if i == 0:
            s0 = si
        ws.append(wi)
    while len(ws) < 4:
        ws.append(0)
    return st, from_words(ws), s0


def be32(x: int) -> bytes:
    return int(x).to_bytes(32, "big")


def lnr1(src_d: bytes, run_id: int, vid: int, op: int, a: int, b: int, d: int,
         q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = op
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(a)
    raw[88:120] = be32(b)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle(recs: list[bytes], leaf_d: bytes, node_d: bytes) -> bytes:
    nodes = [hashlib.sha256(leaf_d + r).digest() for r in recs]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            L = nodes[i]
            R = nodes[i + 1] if i + 1 < len(nodes) else L
            nxt.append(hashlib.sha256(node_d + L + R).digest())
        nodes = nxt
    return nodes[0]


def lcr2(img: bytes, run_id: int, tx: int, ain: int, rin: int, rout: int,
         aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def openssl_sha256(data: bytes) -> bytes:
    p = run(["openssl", "dgst", "-sha256", "-binary"], inp=data, timeout=30)
    if p.returncode != 0 or len(p.stdout) != 32:
        raise RuntimeError("openssl dgst failed")
    return p.stdout


def node_root(path: Path) -> str | None:
    node = shutil.which("node") or "/exec-daemon/node"
    if not Path(node).exists():
        return None
    js = (
        "const fs=require('fs');const c=require('crypto');"
        "const b=fs.readFileSync(process.argv[1]);const N=240;"
        "const L=Buffer.from('LIN:U512:LEAF:1');const D=Buffer.from('LIN:U512:NODE:1');"
        "let n=[];for(let i=0;i<b.length;i+=N){"
        "n.push(c.createHash('sha256').update(L).update(b.slice(i,i+N)).digest())}"
        "while(n.length>1){const x=[];for(let i=0;i<n.length;i+=2){"
        "const L=n[i],R=i+1<n.length?n[i+1]:n[i];"
        "x.push(c.createHash('sha256').update(D).update(L).update(R).digest())}n=x}"
        "process.stdout.write(n[0].toString('hex'));"
    )
    p = run([node, "-e", js, str(path)])
    return p.stdout.strip() if p.returncode == 0 else None


def vectors() -> list[tuple[str, int, int, int]]:
    out: list[tuple[str, int, int, int]] = []
    edges = [0, 1, 2, 3, 7, 9, (1 << 64) - 1, 1 << 128, 1 << 255, UMAX]
    for a in edges:
        for b in edges:
            out.append(("MUL", a, b, 0))
            for d in (1, 2, 3, 1997, UMAX, a + 1 or 1):
                out.append(("MULDIV", a, b, d & UMAX or 1))
    rng = 0xC0FFEE
    for _ in range(180):
        rng = (rng * 6364136223846793005 + 1) & ((1 << 64) - 1)
        a = (rng * 0x9E3779B97F4A7C15) & UMAX
        b = (rng * 0xBF58476D1CE4E5B9) & UMAX
        d = (rng * 0x94D049BB133111EB) & UMAX
        out.append(("MUL", a, b, 0))
        out.append(("MULDIV", a, b, d if d else 1))
    return out


def leaf_dict(op: str, a: int, b: int, d: int, q: int, r: int, status: int, steps: int) -> dict:
    return {
        "op": op, "a": hex(a), "b": hex(b), "d": hex(d),
        "q": hex(q), "r": hex(r), "status": status, "steps": steps,
    }


def lcr2_dict(cls: str, tx: int, ain: int, rin: int, rout: int, aout: int,
              steps: int, status: int, cop: int, ref: int, onchain: int) -> dict:
    return {
        "class": cls, "tx": tx,
        "ain": hex(ain), "rin": hex(rin), "rout": hex(rout), "aout": hex(aout),
        "steps": steps, "status": status,
        "coprocessor": hex(cop), "ref": hex(ref), "onchain": hex(onchain),
    }


def lge1(src_d: bytes, run_id: int, vid: int, a: int, b: int, ge: int, steps: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LGE1"
    raw[4] = 1
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(a & UMAX)
    raw[88:120] = be32(a >> 256)
    raw[120:152] = be32(b & UMAX)
    raw[152:184] = be32(b >> 256)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<Q", raw, 192, ge)
    return bytes(raw)


def ge_dict(name: str, a: int, b: int, ge: int, steps: int) -> dict:
    return {"name": name, "a": hex(a), "b": hex(b), "ge": ge, "steps": steps}


def hex512(n: int) -> str:
    return f"{n:0128x}"


def ge_vectors() -> list[tuple[int, int, int, str]]:
    maxsq = UMAX * UMAX
    u512 = (1 << 512) - 1
    return [
        (1 << 256, UMAX, 1, "boundary_2_256_ge_umax"),
        (UMAX, 1 << 256, 0, "boundary_umax_lt_2_256"),
        (0, 0, 1, "zero_eq"),
        (maxsq, 1 << 511, 1, "maxsq_ge_2_511"),
        (1 << 511, maxsq, 0, "two_511_lt_maxsq"),
        (maxsq, maxsq, 1, "maxsq_eq"),
        (u512, 1, 1, "max512_ge_1"),
        (1, u512, 0, "one_lt_max512"),
    ]
