#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validação Massiva Multi-Pool / Multi-Token — Ethereum Mainnet
Comprova paridade bit a bit exata em múltiplos tokens heterogêneos:
  - USDC (6 decimais)
  - USDT (6 decimais)
  - DAI  (18 decimais)
  - WBTC (8 decimais)
  - WETH (18 decimais)

Executa u256_settlement_engine.linbc em LinVM pura para cada um dos 192 swaps reais.
Atesta com provas Merkle SHA-256 (LCR2) que a matemática não depende de sorte nem de pool específico.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIN_BC1_RUN = ROOT / "transpile/c/bin/lin_bc1_run"
U256_BC1 = ROOT / "examples/defi_settlement_proof/u256_settlement_engine.linbc"
DATASET_PATH = ROOT / "test/pilot_harness/mainnet_real_swaps_multi_pools_500.json"

DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"

def to_signed_words(x: int) -> list[str]:
    res = []
    for _ in range(4):
        w = x & 0xFFFFFFFFFFFFFFFF
        if w >= (1 << 63):
            w = w - (1 << 64)
        res.append(str(w))
        x >>= 64
    return res

def run_lin_u256(ain: int, rin: int, rout: int) -> tuple[int, int, int]:
    args_base = to_signed_words(ain) + to_signed_words(rin) + to_signed_words(rout)
    
    cmd_st = [str(LIN_BC1_RUN), str(U256_BC1), "settle_u256_word"] + args_base + ["-1"]
    out_st = subprocess.check_output(cmd_st, text=True)
    status, total_steps = None, 0
    for token in out_st.split():
        if token.startswith("result="):
            status = int(token.split("=")[1])
        elif token.startswith("steps="):
            total_steps += int(token.split("=")[1])

    if status != 1:
        return status, 0, total_steps

    words_out = []
    for widx in range(4):
        cmd = [str(LIN_BC1_RUN), str(U256_BC1), "settle_u256_word"] + args_base + [str(widx)]
        out = subprocess.check_output(cmd, text=True)
        for token in out.split():
            if token.startswith("result="):
                words_out.append(int(token.split("=")[1]) & 0xFFFFFFFFFFFFFFFF)
            elif token.startswith("steps="):
                total_steps += int(token.split("=")[1])

    out_val = words_out[0] | (words_out[1] << 64) | (words_out[2] << 128) | (words_out[3] << 192)
    return status, out_val, total_steps

def build_merkle_root(leaves: list[bytes]) -> bytes:
    curr = list(leaves)
    while len(curr) > 1:
        next_level = []
        for i in range(0, len(curr), 2):
            left = curr[i]
            right = curr[i+1] if (i+1 < len(curr)) else curr[i]
            h = hashlib.sha256(DOM_NODE + left + right).digest()
            next_level.append(h)
        curr = next_level
    return curr[0]

def main():
    print("=" * 85)
    print("  PROVA ON-CHAIN MASSIVA MULTI-TOKEN: 192 SWAPS REAIS DA MAINNET DO ETHEREUM")
    print("=" * 85)

    swaps = json.loads(DATASET_PATH.read_text())
    print(f"[*] Total de swaps reais carregados: {len(swaps)}")
    print(f"[*] Imagem LinVM: {U256_BC1.name}")

    t0 = time.perf_counter()
    leaves = []
    passed = 0
    total_vm_steps = 0
    pool_stats = {}

    for i, s in enumerate(swaps):
        pname = s["pool_name"]
        st, calc_out, steps = run_lin_u256(s["amount_in"], s["reserve_in"], s["reserve_out"])
        total_vm_steps += steps
        expected = s["expected_out_real"]
        
        match = (st == 1 and calc_out == expected)
        assert match, f"DIVERGÊNCIA na Tx {s['tx_hash']}! Esperado {expected}, obtido {calc_out}"
        passed += 1

        pool_stats[pname] = pool_stats.get(pname, 0) + 1

        raw = bytearray(208)
        raw[0:4] = b"LCR2"
        raw[4] = 1; raw[5] = 1
        raw[8:40] = hashlib.sha256(U256_BC1.read_bytes()).digest()
        struct.pack_into("<QQ", raw, 40, 1, s["id"])
        raw[56:88] = s["amount_in"].to_bytes(32, "big")
        raw[88:120] = s["reserve_in"].to_bytes(32, "big")
        raw[120:152] = s["reserve_out"].to_bytes(32, "big")
        raw[152:184] = calc_out.to_bytes(32, "big")
        struct.pack_into("<Qq", raw, 184, steps, st)

        leaf = hashlib.sha256(DOM_LEAF + bytes(raw)).digest()
        leaves.append(leaf)

        if (i + 1) % 25 == 0 or (i + 1) == len(swaps):
            print(f"  [{i+1:>3}/192] ({pname:<9}) {s['direction']:<11} | Tx {s['tx_hash'][:14]}... | Bloco {s['block']} -> PASS (100% BIT-EXACT)")

    root = build_merkle_root(leaves)
    elapsed = time.perf_counter() - t0

    print("-" * 85)
    print(f"[Distribuição Aprovada]: {pool_stats}")
    print(f"[Taxa de Sucesso]: {passed}/{len(swaps)} ({passed/len(swaps)*100:.1f}%) APROVADOS BIT A BIT")
    print(f"[Total LinVM Steps]: {total_vm_steps:,} instruções determinísticas")
    print(f"[Tempo Total]: {elapsed:.2f}s ({elapsed/len(swaps)*1000:.1f} ms/swap)")
    print(f"[Raiz Merkle Multi-Pool]: {root.hex()}")
    print("=" * 85)

if __name__ == "__main__":
    main()
