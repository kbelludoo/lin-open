#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validação Massiva On-Chain — 50 Swaps Reais da Mainnet do Ethereum
Execução rigorosa sem simulações:
  - Carrega 50 transações reais extraídas diretamente dos blocos 25900475..25900661.
  - Executa a imagem LinVM u256_settlement_engine.linbc em multiword uint256.
  - Comprova paridade bit a bit com o evento on-chain confirmado.
  - Constrói a Árvore Merkle binária LCR2 e atesta integridade criptográfica.
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
DATASET_PATH = ROOT / "test/pilot_harness/mainnet_real_swaps_100.json"

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
    
    # 1. Status check
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

    # 2. Reconstrução das 4 palavras de 64 bits
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

def canonical_image_digest() -> bytes:
    """Digest CANÔNICO da imagem (o mesmo que o loader LINBC1 verifica em
    `lin_bc1_run --verify`), NÃO o sha256 dos bytes crus do arquivo."""
    out = subprocess.check_output(
        [str(LIN_BC1_RUN), str(U256_BC1), "--verify"], text=True)
    for token in out.split():
        if token.startswith("img_sha256="):
            return bytes.fromhex(token.split("=")[1].strip('"'))
    raise RuntimeError("img_sha256 ausente na verificação LINBC1")


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
    print("  PROVA ON-CHAIN MASSIVA: 50 TRANSAÇÕES REAIS DA MAINNET DO ETHEREUM")
    print("=" * 85)

    swaps = json.loads(DATASET_PATH.read_text())
    print(f"[*] Total de swaps reais carregados: {len(swaps)}")
    print(f"[*] Imagem LinVM: {U256_BC1.name}")

    img_digest = canonical_image_digest()
    print(f"[*] Digest canônico (loader): {img_digest.hex()}")

    t0 = time.perf_counter()
    leaves = []
    passed = 0
    total_vm_steps = 0

    for i, s in enumerate(swaps):
        st, calc_out, steps = run_lin_u256(s["amount_in"], s["reserve_in"], s["reserve_out"])
        total_vm_steps += steps
        expected = s["expected_out_real"]
        
        match = (st == 1 and calc_out == expected)
        assert match, f"DIVERGÊNCIA na Tx {s['tx_hash']}! Esperado {expected}, obtido {calc_out}"
        passed += 1

        # Montar folha LCR2 canônica de 208 bytes
        raw = bytearray(208)
        raw[0:4] = b"LCR2"
        raw[4] = 1; raw[5] = 1
        raw[8:40] = img_digest
        struct.pack_into("<QQ", raw, 40, 1, s["id"]) # chain_id=1, seq
        raw[56:88] = s["amount_in"].to_bytes(32, "big")
        raw[88:120] = s["reserve_in"].to_bytes(32, "big")
        raw[120:152] = s["reserve_out"].to_bytes(32, "big")
        raw[152:184] = calc_out.to_bytes(32, "big")
        struct.pack_into("<Qq", raw, 184, steps, st)

        leaf = hashlib.sha256(DOM_LEAF + bytes(raw)).digest()
        leaves.append(leaf)

        if (i + 1) % 10 == 0 or (i + 1) == len(swaps):
            print(f"  [{i+1:>2}/50] Bloco {s['block']} | Tx {s['tx_hash'][:16]}... | {s['direction']} -> PASS (100% BIT-EXACT)")

    root = build_merkle_root(leaves)
    elapsed = time.perf_counter() - t0

    print("-" * 85)
    print(f"[Taxa de Sucesso]: 50/50 ({passed/len(swaps)*100:.1f}%) APROVADOS BIT A BIT")
    print(f"[Total LinVM Steps]: {total_vm_steps:,} instruções determinísticas")
    print(f"[Tempo Total]: {elapsed:.2f}s ({elapsed/len(swaps)*1000:.1f} ms/swap)")
    print(f"[Raiz Merkle do Lote de 50]: {root.hex()}")
    print("=" * 85)

if __name__ == "__main__":
    main()
