#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/verify_batch_receipt.py — Verificador independente do receipt de lote LCR2.
So stdlib (hashlib/struct/json). Nao importa o emissor.
Recomputa records_sha256 + folhas + raiz Merkle a partir do .bin,
e re-executa o oraculo big-int independente para cada record.

Uso:
  python3 tools/verify_batch_receipt.py --manifest /tmp/batch_receipt.json --bin /tmp/batch_records.bin
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path

DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
RECORD_BYTES = 208

def oracle(ain, rin, rout):
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > (1 << 256) - 1 or num > (1 << 256) - 1 or den > (1 << 256) - 1:
        return -2, 0
    return 1, num // den

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bin", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.manifest).read_text())
    blob = Path(a.bin).read_bytes()
    assert m["record_bytes"] == RECORD_BYTES, "record_bytes inesperado"
    assert len(blob) == m["count"] * RECORD_BYTES, f"bin len {len(blob)} != count*208"
    rh = hashlib.sha256(blob).hexdigest()
    if rh != m["records_sha256"]:
        print(f"FAIL: records_sha256 calc={rh} != manifest={m['records_sha256']}")
        return 1
    img = bytes.fromhex(m["img_digest"])
    leaves = []
    bad_magic = 0
    oracle_mismatch = 0
    for i in range(m["count"]):
        rec = blob[i*208:(i+1)*208]
        if rec[0:4] != b"LCR2" or rec[4] != 1:
            bad_magic += 1
        if rec[8:40] != img:
            print(f"FAIL: record {i} img_digest diverge")
            return 1
        run_id = struct.unpack_from("<Q", rec, 40)[0]
        tx_id = struct.unpack_from("<Q", rec, 48)[0]
        ain = int.from_bytes(rec[56:88], "big")
        rin = int.from_bytes(rec[88:120], "big")
        rout = int.from_bytes(rec[120:152], "big")
        aout = int.from_bytes(rec[152:184], "big")
        steps = struct.unpack_from("<Q", rec, 184)[0]
        status = struct.unpack_from("<q", rec, 192)[0]
        if run_id != m["run_id"] or tx_id != i + 1:
            print(f"FAIL: record {i} run/tx id inesperado")
            return 1
        if steps != 0:
            print(f"FAIL: steps_bound=false mas steps={steps} no record {i}")
            return 1
        wst, waout = oracle(ain, rin, rout)
        if wst != status or waout != aout:
            oracle_mismatch += 1
            if oracle_mismatch <= 3:
                print(f"  oracle mismatch rec{i}: record(status={status},aout={aout}) vs oracle({wst},{waout})")
        leaves.append(hashlib.sha256(DOM_LEAF + rec).digest())
    if bad_magic:
        print(f"FAIL: {bad_magic} records com magic invalido")
        return 1
    if oracle_mismatch:
        print(f"FAIL: {oracle_mismatch}/{m['count']} records divergem do oraculo big-int")
        return 1
    cur = leaves
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]; r = cur[i+1] if i+1 < len(cur) else cur[i]
            nxt.append(hashlib.sha256(DOM_NODE + l + r).digest())
        cur = nxt
    root = cur[0].hex()
    if root != m["merkle_root"]:
        print(f"FAIL: root calc={root} != manifest={m['merkle_root']}")
        return 1
    print(f"PASS: {m['count']} records LCR2 verificados")
    print(f"  records_sha256 ok: {rh}")
    print(f"  oraculo big-int ok: {m['count']}/{m['count']}")
    print(f"  merkle root ok: {root}")
    print(f"  nota: steps_bound=false (steps=0), aout=oraculo (overpaid diverge on-chain por design)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
