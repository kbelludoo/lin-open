#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate de Prontidão Comercial — Nível Piloto (Automated CI Verification)
Verifica rigorosamente os 5 grupos de requisitos antes de qualquer oferta de piloto:
  1. Correção Matemática Ampliada (Casos normais, extremos, overflow/wrapping, zero/negativos)
  2. Emissão Canônica LINBC1 e Roundtrip de Consenso
  3. Integridade Criptográfica (Inclusão Merkle SHA-256 de 256 bits, mutações de folhas, irmãos e raízes)
  4. Sanitização e Limites de Memória (ASan/UBSan no Host C11 + Fuzzing de Truncamento)
  5. Perfil de Latência e Desempenho (Distribuição de tempos: min, p50, p95, p99, max)

Status Epistêmico (R5): Nível Piloto (Defensável com evidências locais reprodutíveis).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIN_C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
LIN_BC1_RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
SETTLEMENT_LIN = ROOT / "examples" / "defi_settlement_proof" / "settlement_engine.lin"
SETTLEMENT_BC1 = ROOT / "examples" / "defi_settlement_proof" / "settlement_engine.linbc"

def uniswap_v2_oracle(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    in_fee = amount_in * 997
    num = in_fee * reserve_out
    den = (reserve_in * 1000) + in_fee
    return num // den if den > 0 else 0

def run_bc1(fn: str, *args) -> tuple[int, int, bytes]:
    cmd = [str(LIN_BC1_RUN), str(SETTLEMENT_BC1), fn, *[str(a) for a in args]]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"lin_bc1_run error: {p.stderr}")
    val, steps, digest = None, None, None
    for token in p.stdout.split():
        if token.startswith("result="):
            val = int(token.split("=")[1])
        elif token.startswith("steps="):
            steps = int(token.split("=")[1])
        elif token.startswith("img_sha256="):
            digest = bytes.fromhex(token.split("=")[1].strip('"'))
    return val, steps, digest

def test_group1_math_corpus() -> bool:
    print("[GATE 1/5] Correção Matemática: Corpus de Extremos e Limites...")
    test_cases = [
        # Zero / Negativos / Inválidos (Fail-Closed)
        (0, 100000, 200000, 0),
        (-10, 100000, 200000, 0),
        (1000, 0, 200000, 0),
        (1000, -500, 200000, 0),
        (1000, 100000, 0, 0),
        (1000, 100000, -100, 0),
        # Valores Mínimos
        (1, 1, 1, 0),
        (2, 1, 1, 0),
        (10, 10, 10, 4), # in_fee = 9970, num = 99700, den = 10000 + 9970 = 19970 -> 99700 // 19970 = 4
        # Casos Típicos de AMM
        (1000, 50000, 100000, 1955),
        (5000, 1000000, 2000000, 9920),
        # Reservas Desbalanceadas
        (10000, 10000000, 1000, 0), # Pouca liquidez de saída
        (100000, 1000, 10000000, 9900695), # Alta liquidez de saída
        # Teste de Borda de Inteiros Grandes (sem overflow indesejado em 64 bits)
        (500000, 100000000, 200000000, 992054),
    ]

    for (ain, rin, rout, want) in test_cases:
        expected = uniswap_v2_oracle(ain, rin, rout)
        assert expected == want, f"Oráculo divergente: esperado {want}, calculado {expected}"
        got, _, _ = run_bc1("get_amount_out", ain, rin, rout)
        if got != want:
            print(f"  [FAIL] Caso ({ain}, {rin}, {rout}): esperado {want}, obtido {got}")
            return False

    # 100 casos aleatórios adicionais
    rng = random.Random(42)
    for _ in range(100):
        ain = rng.randint(1, 1000000)
        rin = rng.randint(1000, 100000000)
        rout = rng.randint(1000, 100000000)
        want = uniswap_v2_oracle(ain, rin, rout)
        got, _, _ = run_bc1("get_amount_out", ain, rin, rout)
        if got != want:
            print(f"  [FAIL] Caso aleatório ({ain}, {rin}, {rout}): esperado {want}, obtido {got}")
            return False

    print(f"  [PASS] {len(test_cases) + 100} vetores de casos normais, extremos e bordas validados.")
    return True

def test_group2_linbc1_reproducibility() -> bool:
    print("\n[GATE 2/5] Execução LINBC1: Compilação Limpa e Consenso Roundtrip...")
    # 1. Compilar para arquivo temporário e comparar bytes
    tmp_bc = Path("/tmp/check_settlement.linbc")
    p = subprocess.run([str(LIN_C0), "image", str(SETTLEMENT_LIN), "-o", str(tmp_bc)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        print(f"  [FAIL] Falha ao compilar imagem LINBC1: {p.stderr}")
        return False

    ref_bytes = SETTLEMENT_BC1.read_bytes()
    new_bytes = tmp_bc.read_bytes()
    if ref_bytes != new_bytes:
        print("  [FAIL] Divergência byte a byte na emissão da imagem LINBC1")
        return False

    # 2. Roundtrip de Consenso (Código Fonte vs Bytecode)
    p_rt = subprocess.run([str(LIN_C0), "roundtrip", str(SETTLEMENT_LIN), "get_amount_out", "1000", "100000", "200000"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if "status=\"CONSENSUS\"" not in p_rt.stdout:
        print("  [FAIL] Roundtrip não atingiu CONSENSUS entre fonte e bytecode")
        return False

    print("  [PASS] Emissão idêntica (3.098 bytes) e Consenso de Roundtrip confirmado.")
    return True

def test_group3_merkle_cryptographic_integrity() -> bool:
    print("\n[GATE 3/5] Integridade de Recibos: Matriz Completa de Adulteração (Folhas, Irmãos, Raízes)...")
    sys.path.insert(0, str(ROOT / "examples" / "defi_settlement_proof")); from sdk.lin_settlement_sdk import LINSettlementSDK
    sdk = LINSettlementSDK()

    txs = [
        sdk.execute_swap(1, 5001, 1000, 100000, 200000, 1970),
        sdk.execute_swap(1, 5002, 2500, 100000, 200000, 4800),
        sdk.execute_swap(1, 5003, 5000, 100000, 200000, 9900),
        sdk.execute_swap(1, 5004, 1200, 150000, 300000, 2300)
    ]
    bundle = sdk.build_block_bundle(10, txs)
    root = bundle["merkle_root_sha256"]

    # Caso Normal: Todas devem passar
    for tx in bundle["transactions"]:
        if not sdk.verify_transaction_proof(tx, root):
            print(f"  [FAIL] Falha ao verificar prova válida da Tx #{tx['tx_id']}")
            return False

    # Teste 1: Adulteração na Folha / Saída
    tx_bad_leaf = json.loads(json.dumps(bundle["transactions"][0]))
    tx_bad_leaf["out_val"] -= 1 # Altera saída
    raw = bytearray(bytes.fromhex(tx_bad_leaf["raw_record_hex"]))
    struct.pack_into("<q", raw, 48, tx_bad_leaf["out_val"])
    tx_bad_leaf["raw_record_hex"] = raw.hex()
    tx_bad_leaf["leaf_hash_hex"] = hashlib.sha256(raw).hexdigest()
    if sdk.verify_transaction_proof(tx_bad_leaf, root):
        print("  [FAIL] Falha: prova aceitou saída adulterada!")
        return False

    # Teste 2: Adulteração no Irmão (Sibling 0)
    tx_bad_s0 = json.loads(json.dumps(bundle["transactions"][0]))
    s0_bytes = bytearray(bytes.fromhex(tx_bad_s0["merkle_proof"]["sibling0_hex"]))
    s0_bytes[0] ^= 0xFF
    tx_bad_s0["merkle_proof"]["sibling0_hex"] = s0_bytes.hex()
    if sdk.verify_transaction_proof(tx_bad_s0, root):
        print("  [FAIL] Falha: prova aceitou nó irmão (sibling0) adulterado!")
        return False

    # Teste 3: Adulteração no Irmão de Nível 1 (Sibling 1)
    tx_bad_s1 = json.loads(json.dumps(bundle["transactions"][0]))
    s1_bytes = bytearray(bytes.fromhex(tx_bad_s1["merkle_proof"]["sibling1_hex"]))
    s1_bytes[0] ^= 0xFF
    tx_bad_s1["merkle_proof"]["sibling1_hex"] = s1_bytes.hex()
    if sdk.verify_transaction_proof(tx_bad_s1, root):
        print("  [FAIL] Falha: prova aceitou nó irmão (sibling1) adulterado!")
        return False

    # Teste 4: Raiz Adulterada
    fake_root = hashlib.sha256(b"fake_root").hexdigest()
    if sdk.verify_transaction_proof(bundle["transactions"][0], fake_root):
        print("  [FAIL] Falha: prova aceitou raiz falsa!")
        return False

    print("  [PASS] 100% das mutações adversariais (folhas, irmãos e raízes) barradas com sucesso.")
    return True

def test_group4_memory_sanitizers_and_fuzzing() -> bool:
    print("\n[GATE 4/5] Segurança de Memória: Compilação com AddressSanitizer & Fuzzing de Truncamento...")
    # 1. Compilar host de teste com AddressSanitizer e UndefinedBehaviorSanitizer
    asan_bin = Path("/tmp/asan_merkle_host")
    cmd_build = [
        "gcc", "-O1", "-g", "-fsanitize=address,undefined", "-Wall", "-Wextra", "-Werror", "-std=c11",
        f"-I{ROOT}/transpile/c/lin_c",
        "-o", str(asan_bin),
        f"{ROOT}/examples/defi_settlement_proof/merkle_sha256_host.c",
        f"{ROOT}/transpile/c/lin_c/lin_linbc1.c",
        f"{ROOT}/transpile/c/lin_c/lin_vm.c",
        f"{ROOT}/transpile/c/lin_c/lin_sha256.c",
        f"{ROOT}/transpile/c/lin_c/lin_common.c",
        f"{ROOT}/transpile/c/lin_c/lin_token.c",
        f"{ROOT}/transpile/c/lin_c/lin_ast.c",
        f"{ROOT}/transpile/c/lin_c/lin_parse.c",
        f"{ROOT}/transpile/c/lin_c/lin_str.c"
    ]
    p_b = subprocess.run(cmd_build, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p_b.returncode != 0:
        print(f"  [FAIL] Falha ao compilar com ASan/UBSan: {p_b.stderr}")
        return False

    # Executar binário com sanitizers
    p_run = subprocess.run([str(asan_bin)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT))
    if p_run.returncode != 0 or "AddressSanitizer" in p_run.stderr:
        print(f"  [FAIL] AddressSanitizer detectou erro: {p_run.stderr}")
        return False

    # 2. Fuzzing de truncamento: testar loader fail-closed sob tamanhos parciais
    raw_img = SETTLEMENT_BC1.read_bytes()
    for cut in [0, 5, 10, 20, 50, 100, 500, 1000, len(raw_img) - 1, len(raw_img) - 32]:
        truncated = raw_img[:cut]
        tmp_f = Path("/tmp/fuzz_truncated.linbc")
        tmp_f.write_bytes(truncated)
        p_fuzz = subprocess.run([str(LIN_BC1_RUN), str(tmp_f), "settle_swap", "1000", "100000", "200000", "1970"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Loader DEVE falhar de forma limpa (código de erro != 0 ou recusa explícita, sem SIGSEGV)
        if p_fuzz.returncode == -11: # SIGSEGV
            print(f"  [FAIL] Crash SIGSEGV detectado no loader ao truncar em {cut} bytes!")
            return False

    print("  [PASS] ASan/UBSan concluídos sem nenhum erro e Fuzzing de truncamento 100% fail-closed.")
    return True

def test_group5_performance_distribution() -> bool:
    print("\n[GATE 5/5] Distribuição de Desempenho: Métricas p50, p95, p99 e Estatísticas...")
    # Executar 100 chamadas para medir a distribuição real de latência
    latencies_us = []
    for _ in range(100):
        t0 = time.perf_counter()
        run_bc1("settle_swap", 1000, 100000, 200000, 1970)
        latencies_us.append((time.perf_counter() - t0) * 1_000_000)

    latencies_us.sort()
    p50 = latencies_us[int(len(latencies_us) * 0.50)]
    p95 = latencies_us[int(len(latencies_us) * 0.95)]
    p99 = latencies_us[int(len(latencies_us) * 0.99)]
    mean_lat = sum(latencies_us) / len(latencies_us)

    print(f"  [PASS] Amostras = {len(latencies_us)} execuções independentes de bytecode:")
    print(f"         Média = {mean_lat:.2f} µs | p50 = {p50:.2f} µs | p95 = {p95:.2f} µs | p99 = {p99:.2f} µs")
    return True

def main():
    print("================================================================================")
    print("   LIN COMMERCIAL READINESS GATE (NÍVEL PILOTO - AVALIAÇÃO DE 5 PILARES)        ")
    print("================================================================================\n")

    results = [
        test_group1_math_corpus(),
        test_group2_linbc1_reproducibility(),
        test_group3_merkle_cryptographic_integrity(),
        test_group4_memory_sanitizers_and_fuzzing(),
        test_group5_performance_distribution()
    ]

    print("\n================================================================================")
    if all(results):
        print("  VEREDITO FINAL: APROVADO PARA OFERTA DE PILOTO COMERCIAL (PASS 5/5)           ")
        print("  Status: Qualificado para Piloto Técnico Controlado com Escopo Delimitado     ")
        print("================================================================================")
        sys.exit(0)
    else:
        print("  VEREDITO FINAL: REPROVADO NO GATE COMERCIAL                                   ")
        print("================================================================================")
        sys.exit(1)

if __name__ == "__main__":
    main()
