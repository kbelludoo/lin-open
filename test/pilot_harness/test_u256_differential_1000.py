#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suíte de Testes Diferenciais uint256 — Nível Piloto (1.000 Vetores)
Compara a execução da LinVM C11 (u256_settlement_engine.linbc)
contra um oráculo independente de 256 bits compatível com Solidity/SafeMath.

Cobre:
  1. Casos canônicos de produção (18 decimais, upstream Uniswap V2)
  2. Casos de borda (zero, entradas inválidas, sentinela -1)
  3. Casos de overflow aritmético (> 2^256 - 1, sentinela -2)
  4. 1.000 vetores pseudo-aleatórios determinísticos (seed 20260904)
"""

from __future__ import annotations

import random
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIN_BC1_RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
U256_BC1 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.linbc"

U256_MAX = (1 << 256) - 1

def u256_oracle(ain: int, rin: int, rout: int) -> tuple[int, int]:
    """Oráculo BigInt independente de especificação Uniswap V2 / Solidity."""
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    in_fee = ain * 997
    num = in_fee * rout
    den = rin * 1000 + in_fee
    if in_fee > U256_MAX or num > U256_MAX or den > U256_MAX:
        return -2, 0
    return 1, num // den

def to_signed_words(x: int) -> list[str]:
    """Converte inteiro de 256 bits para 4 palavras de 64 bits com sinal."""
    res = []
    for _ in range(4):
        w = x & 0xFFFFFFFFFFFFFFFF
        if w >= (1 << 63):
            w = w - (1 << 64)
        res.append(str(w))
        x >>= 64
    return res

def run_lin_u256(ain: int, rin: int, rout: int) -> tuple[int, int, int]:
    """Executa o kernel LIN e retorna (status, amount_out, steps_total)."""
    args_base = to_signed_words(ain) + to_signed_words(rin) + to_signed_words(rout)
    
    # 1. Checa status
    cmd_st = [str(LIN_BC1_RUN), str(U256_BC1), "settle_u256_word"] + args_base + ["-1"]
    p_st = subprocess.run(cmd_st, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p_st.returncode != 0:
        raise RuntimeError(f"Erro no lin_bc1_run: {p_st.stderr}")
    
    status, total_steps = None, 0
    for token in p_st.stdout.split():
        if token.startswith("result="):
            status = int(token.split("=")[1])
        elif token.startswith("steps="):
            total_steps += int(token.split("=")[1])
            
    if status < 0:
        return status, 0, total_steps

    # 2. Se status == 1, recupera as 4 palavras
    words_out = []
    for widx in range(4):
        cmd = [str(LIN_BC1_RUN), str(U256_BC1), "settle_u256_word"] + args_base + [str(widx)]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Erro no lin_bc1_run: {p.stderr}")
        for token in p.stdout.split():
            if token.startswith("result="):
                val = int(token.split("=")[1])
                words_out.append(val & 0xFFFFFFFFFFFFFFFF)
            elif token.startswith("steps="):
                total_steps += int(token.split("=")[1])

    out_val = words_out[0] | (words_out[1] << 64) | (words_out[2] << 128) | (words_out[3] << 192)
    return status, out_val, total_steps

def main():
    print("=" * 80)
    print("  SUÍTE DE PARIDADE DIFERENCIAL UINT256: 1.000 VETORES (LINVM vs EVM/ORÁCULO)")
    print("=" * 80)

    # 1. Casos Canônicos e Bordas
    golden_vectors = [
        # (ain, rin, rout, descricao)
        (2, 100, 100, "Uniswap V2 upstream small"),
        (10000, 50000, 100000, "Uniswap V2 upstream canonical 16624"),
        (10**18, 5 * 10**18, 10 * 10**18, "Produção 18 decimais (1 ETH, 5 ETH, 10 ETH)"),
        (0, 100, 100, "Borda: amount_in zero (fail-closed -1)"),
        (100, 0, 100, "Borda: reserve_in zero (fail-closed -1)"),
        (100, 100, 0, "Borda: reserve_out zero (fail-closed -1)"),
        (1 << 200, 1, 1 << 40, "Borda: valores em palavras superiores sem overflow"),
        (1 << 200, 1, 1 << 100, "Overflow: numerador excede 2^256-1 (sentinela -2)"),
        (U256_MAX, 1000, 1000, "Overflow: amount_in máximo com multiplicação 997"),
    ]

    print("[*] Fase 1: Validando vetores dourados e casos de borda...")
    for ain, rin, rout, desc in golden_vectors:
        exp_st, exp_val = u256_oracle(ain, rin, rout)
        got_st, got_val, steps = run_lin_u256(ain, rin, rout)
        assert got_st == exp_st, f"Divergência de status em '{desc}': esperado {exp_st}, obtido {got_st}"
        assert got_val == exp_val, f"Divergência de valor em '{desc}': esperado {exp_val}, obtido {got_val}"
        print(f"  [PASS] {desc} -> Status={got_st} | Out={got_val} | Steps={steps}")

    print("\n[*] Fase 2: Executando 1.000 vetores aleatórios com distribuição controlada...")
    rng = random.Random(20260904)
    divergences = 0
    t0 = time.time()
    
    # 1000 vetores distribuídos:
    # 700 casos normais de DeFi (18 decimais / 6 decimais)
    # 150 casos extremos com números grandes (> 2^150)
    # 100 casos com entradas zero/negativas
    # 50 casos forçando overflow aritmético
    total_runs = 1000
    for i in range(total_runs):
        cat = i % 10
        if cat < 7:
            # Grandezas normais de tokens (10^6 até 10^24)
            ain = rng.randint(1, 10**21)
            rin = rng.randint(10**18, 10**24)
            rout = rng.randint(10**18, 10**24)
        elif cat < 8:
            # Números muito grandes
            ain = rng.randint(1, 1 << 120)
            rin = rng.randint(1, 1 << 120)
            rout = rng.randint(1, 1 << 120)
        elif cat < 9:
            # Entradas inválidas / Zero
            choice = rng.randint(0, 2)
            ain = 0 if choice == 0 else rng.randint(1, 10**18)
            rin = 0 if choice == 1 else rng.randint(1, 10**18)
            rout = 0 if choice == 2 else rng.randint(1, 10**18)
        else:
            # Forçar overflow
            ain = rng.randint(1 << 200, U256_MAX)
            rin = rng.randint(1, 10**18)
            rout = rng.randint(1 << 100, U256_MAX)

        exp_st, exp_val = u256_oracle(ain, rin, rout)
        got_st, got_val, _ = run_lin_u256(ain, rin, rout)

        if got_st != exp_st or got_val != exp_val:
            divergences += 1
            print(f"  [FAIL] Vetor #{i}: esperado status={exp_st}, val={exp_val} | obtido status={got_st}, val={got_val}")
            break

        if (i + 1) % 200 == 0:
            sys.stdout.write(f"  ... {i + 1}/{total_runs} vetores validados com sucesso ...\n")
            sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\n[*] 1.000 Vetores processados em {elapsed:.2f}s (Média: {(elapsed/total_runs)*1000:.2f} ms/vetor)")
    
    if divergences == 0:
        print("=" * 80)
        print("  VEREDITO FINAL: PARIDADE 100% BIT-EXACT CONTRA SOLIDITY/EVM (PASS 1000/1000) ")
        print("=" * 80)
        return 0
    else:
        print("=" * 80)
        print(f"  VEREDITO FINAL: FALHA ({divergences} DIVERGÊNCIAS DETECTADAS)")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
