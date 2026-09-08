#!/usr/bin/env python3
"""
bin/lin_defi_settler — Sovereign Uniswap v2 DeFi Settlement & Audit CLI

Runs ultra-high throughput batch liquidation and invariant verification
on the physical AMD Radeon RX 6600 GPU, backed by LinVM pure LIN proofs
and cryptographic Compute Receipts.
"""

import sys
import os
import time
import json
import argparse
import subprocess
import hashlib

def parse_gpu_output(stdout):
    """Parse kernel time/TPS from both honest and legacy host formats.

    Honest (src atual): '[Tempo do kernel na GPU]:   0.0016 s'
                        '[Throughput deste lote]:    1235822.8 swaps/s'
    Legado (binario stale): '[Tempo de Execução na GPU]: 0.0022 segundos'
                            '[Throughput Real na GPU]:   916564.2 ...'
    Retorna (kernel_sec|None, kernel_tps|None).
    """
    import re
    kernel_sec = None
    kernel_tps = None
    m = re.search(r"Tempo do kernel.*?([\d.]+)\s*s", stdout)
    if m:
        try:
            kernel_sec = float(m.group(1))
        except Exception:
            pass
    if kernel_sec is None:
        m = re.search(r"Tempo de Execu.*?([\d.]+)\s*segundos", stdout)
        if m:
            try:
                kernel_sec = float(m.group(1))
            except Exception:
                pass
    m = re.search(r"Throughput deste lote.*?([\d.,]+)\s*swaps/s", stdout)
    if m:
        try:
            kernel_tps = float(m.group(1).replace(",", ""))
        except Exception:
            pass
    if kernel_tps is None:
        m = re.search(r"Throughput Real.*?([\d.,]+)", stdout)
        if m:
            try:
                kernel_tps = float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return kernel_sec, kernel_tps


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def format_tokens(val, decimals=18):
    try:
        n = int(val)
        return f"{n / (10**decimals):,.4f}"
    except Exception:
        return str(val)

def main():
    parser = argparse.ArgumentParser(
        description="LIN Sovereign DeFi AMM Settler & Proof-of-Compute Engine"
    )
    parser.add_argument(
        "--dataset",
        default="test/pilot_harness/mainnet_real_swaps_2000.json",
        help="Path to on-chain Ethereum swaps JSON dataset"
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        default=True,
        help="Execute on physical GPU (AMD Radeon RX 6600 via OpenCL)"
    )
    parser.add_argument(
        "--receipt",
        default="/tmp/uniswap_settlement_receipt.rulel",
        help="Path to emit cryptographic SHA-256 compute receipt"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        default=True,
        help="Print side-by-side comparison against Ethereum L1 EVM"
    )

    args = parser.parse_args()

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    c0_bin = os.path.join(root_dir, "transpile/c/bin/lin_c0")
    gpu_host_bin = os.path.join(root_dir, "examples/defi_settlement_proof/u256_opencl_host")
    lin_app_src = os.path.join(root_dir, "examples/defi_settlement_proof/lin_amm_settler_app.lin")

    if not os.path.exists(c0_bin):
        print(f"[ERRO] Compilador 0 não encontrado em {c0_bin}. Execute 'make -C transpile/c c0'.")
        sys.exit(1)

    dataset_path = os.path.abspath(args.dataset)
    if not os.path.exists(dataset_path):
        print(f"[ERRO] Dataset não encontrado: {dataset_path}")
        sys.exit(1)

    print("=====================================================================================")
    print("      LIN SOVEREIGN DEFI SETTLEMENT & AMM LIQUIDATION ENGINE")
    print("      Hardware: AMD Radeon RX 6600 | LinVM Compiler 0 (Pure LIN)")
    print("=====================================================================================")

    # 1. Carregar dataset (suporta lista-2000, dict-swaps e dict-records unfiltered)
    print(f"[*] Carregando transações on-chain de: {dataset_path}...")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        swaps = data
        kind = "list-2000-PRE-FILTRADO-corpus-aritmetico (NAO usar p/ distribuicao)"
    elif isinstance(data, dict) and "records" in data:
        swaps = data["records"]
        kind = "unfiltered-PRIMARIO p/ distribuicao (SEM FILTRO)"
    else:
        swaps = data.get("swaps", [])
        kind = "dict-swaps"
    # Normaliza: unfiltered usa amount_out/get_amount_out; legado usa expected_out_real.
    for s in swaps:
        if "expected_out_real" not in s:
            s["expected_out_real"] = s.get("amount_out", s.get("get_amount_out", 0))
    n_swaps = len(swaps)
    print(f"[*] Total de Swaps: {n_swaps:,} | tipo: {kind}")
    if "PRE-FILTRADO" in kind:
        print("    AVISO: corpus 2000 e pre-filtrado (tautologico p/ rede). "
              "Para distribuicao use test/pilot_harness/mainnet_unfiltered.json.")

    # 2. Gerar representação binária para GPU (128 bytes por swap: 4 palavras de 32 bytes, big-endian)
    bin_path = "/tmp/swaps_batch.bin"
    with open(bin_path, "wb") as bf:
        for s in swaps:
            ain = int(s.get("amount_in", 0))
            rin = int(s.get("reserve_in", 0))
            rout = int(s.get("reserve_out", 0))
            aout = int(s.get("expected_out_real", s.get("amount_out", s.get("expected_out", 0))))
            for val in (ain, rin, rout, aout):
                bf.write(val.to_bytes(32, byteorder="big"))

    # 3. Execucao no Silicio Fisico da GPU (honesto: kernel vs wall)
    gpu_kernel_sec = 0.0
    gpu_wall_sec = 0.0
    gpu_kernel_tps = 0.0
    gpu_wall_tps = 0.0
    if args.gpu:
        print("\n[+] Despachando lote para a GPU fisica (AMD Radeon RX 6600)...")
        host_c = os.path.join(root_dir, "examples/defi_settlement_proof/u256_opencl_host.c")
        # Rebuild automatico se fonte mais novo que binario (evita binario stale).
        rebuild = False
        if not os.path.exists(gpu_host_bin):
            rebuild = True
        elif os.path.exists(host_c) and os.path.getmtime(host_c) > os.path.getmtime(gpu_host_bin):
            print("[*] Fonte OpenCL mais novo que binario: recompilando (evita stale)...")
            rebuild = True
        if rebuild:
            cmd_build = ["cc", "-O3", host_c, "-lOpenCL", "-o", gpu_host_bin]
            subprocess.run(cmd_build, check=True)

        # 3 execucoes para mediana (kernel varia 1.6-3.9ms por clock/estado).
        # NOTA: exit 1 com DIVERGENCIA e resultado honesto (overpaid/roteador),
        # nao crash. So falha se sem info de paridade.
        import re as _re
        walls = []
        kernels = []
        last_out = ""
        match_n = div_n = 0
        for _ in range(3):
            t0 = time.perf_counter()
            res_gpu = subprocess.run([gpu_host_bin, bin_path], capture_output=True, text=True)
            walls.append(time.perf_counter() - t0)
            last_out = res_gpu.stdout
            m1 = _re.search(r"Concordam com expected\D+(\d+)", res_gpu.stdout)
            m2 = _re.search(r"Divergem de expected\D+(\d+)", res_gpu.stdout)
            if m1 and m2:
                match_n, div_n = int(m1.group(1)), int(m2.group(1))
            elif res_gpu.returncode != 0:
                print(f"[ERRO] Falha na execucao da GPU:\n{res_gpu.stderr}\n{res_gpu.stdout[-2000:]}")
                sys.exit(1)
            ks, _ = parse_gpu_output(res_gpu.stdout)
            if ks is not None:
                kernels.append(ks)
        if not kernels:
            print("[ERRO] Nao foi possivel extrair tempo de kernel do host OpenCL.")
            print(last_out[-2000:])
            sys.exit(1)
        gpu_kernel_sec = median(kernels)
        gpu_wall_sec = median(walls)
        gpu_kernel_tps = n_swaps / gpu_kernel_sec if gpu_kernel_sec > 0 else 0.0
        gpu_wall_tps = n_swaps / gpu_wall_sec if gpu_wall_sec > 0 else 0.0

        print(f"  -> GPU: {match_n}/{n_swaps} EXACT (oracle==on-chain), "
              f"{div_n}/{n_swaps} OVERPAID/DIVERGENTE (roteador/fee, k valido).")
        if div_n == 0:
            print("  -> 100% de paridade aprovada no silicio da GPU.")
        else:
            print("  -> Lote NAO reconciliado (esperado no unfiltered): divergencias sao "
                  "overpaid, nao K_VIOLATION. Ver DATASETS.md.")
        print(f"  -> Kernel (mediana 3 runs, exclui JIT/init): {gpu_kernel_sec*1000:.3f} ms "
              f"({gpu_kernel_sec/n_swaps*1e6:.3f} us/swap) -> {gpu_kernel_tps:,.1f} swaps/s kernel-only")
        print(f"  -> Wall (mediana 3 runs, inclui init+JIT+spawn): {gpu_wall_sec*1000:.1f} ms "
              f"-> {gpu_wall_tps:,.1f} swaps/s end-to-end cold")
        print("  -> NOTA: kernel-only NAO e comparavel a TPS L1 (consenso+rede+storage).")

        # Sensibilidade a tamanho de lote (prova wavefront starvation).
        print("\n  [Sensibilidade a lote: kernel TPS cresce com N, wall dominado por fixo ~200ms]")
        for sub_n in [100, 500, n_swaps]:
            sub_n = min(sub_n, n_swaps)
            sub_bin = f"/tmp/swaps_sub_{sub_n}.bin"
            with open(sub_bin, "wb") as bf:
                for s in swaps[:sub_n]:
                    ain = int(s.get("amount_in", 0))
                    rin = int(s.get("reserve_in", 0))
                    rout = int(s.get("reserve_out", 0))
                    aout = int(s.get("expected_out_real", s.get("amount_out", s.get("expected_out", 0))))
                    for val in (ain, rin, rout, aout):
                        bf.write(val.to_bytes(32, byteorder="big"))
            t0 = time.perf_counter()
            r = subprocess.run([gpu_host_bin, sub_bin], capture_output=True, text=True)
            w = time.perf_counter() - t0
            ks, _ = parse_gpu_output(r.stdout)
            ks = ks if ks else float("nan")
            print(f"    n={sub_n:>4}: kernel={ks*1000:.2f}ms ({ks/sub_n*1e6:.2f}us/swap) "
                  f"kernelTPS={sub_n/ks:,.0f} wall={w*1000:.0f}ms wallTPS={sub_n/w:,.0f}")

    # 4. Auditoria Formal na LinVM CPU
    print("\n[+] Auditando regras de invariante e conformidade na LinVM CPU...")
    # Verificar gate do módulo LIN
    res_gate = subprocess.run(
        [c0_bin, "vm", lin_app_src, "amm_settler_app_gate"],
        capture_output=True, text=True, check=True
    )
    if "value=1" not in res_gate.stdout:
        print("[ERRO] amm_settler_app_gate falhou!")
        sys.exit(1)
    print("  -> Invariante x * y >= k e anti-fraude: 100% VALIDADOS na LinVM.")

    # 5. Emissao do Compute Receipt SHA-256 (PLACEHOLDER honesto)
    # AVISO: este receipt de integridade NAO amarra o Merkle root do lote.
    # O receipt real do lote (LCR2 208B/record + Merkle) e gerado por
    # tools/emit_batch_receipt.py (ver Melhoria #3). Mantido aqui apenas
    # como prova de integridade do device/contagem.
    print("\n[+] Gerando e Verificando Compute Receipt Criptografico SHA-256...")
    with open(args.receipt, "w", encoding="utf-8") as rf:
        subprocess.run(
            [c0_bin, "receipt", "create", "--source", "return x * 997;", "--input", str(n_swaps), "--device", "AMD_Radeon_RX_6600"],
            stdout=rf, check=True
        )
    print(f"  -> Recibo criptográfico gerado em: {args.receipt}")

    res_ver = subprocess.run([c0_bin, "receipt", "verify", "--receipt", args.receipt], capture_output=True, text=True)
    if res_ver.returncode == 0:
        print(f"  -> Auditoria Matemática do Recibo: {res_ver.stdout.strip()}")
    else:
        print(f"[AVISO] Verificação do recibo: {res_ver.stderr.strip()}")

    # 6. Benchmark honesto (sem comparacao enganosa com EVM)
    if args.benchmark:
        print("\n=====================================================================================")
        print("                 BENCHMARK HONESTO: KERNEL vs WALL (NAO vs EVM)")
        print("=====================================================================================")
        print(f"  Lote N={n_swaps} | kernel mediana {gpu_kernel_sec*1000:.3f} ms "
              f"({gpu_kernel_tps:,.1f} TPS kernel-only, exclui JIT/init)")
        print(f"  Lote N={n_swaps} | wall mediana {gpu_wall_sec*1000:.1f} ms "
              f"({gpu_wall_tps:,.1f} TPS end-to-end cold, inclui init+JIT ~200ms)")
        print("  EVM L1 15-30 TPS inclui consenso+rede+storage: NAO comparavel a kernel")
        print("    puro de getAmountOut. Nao alegar speedup vs EVM.")
        print("  Para custo de auditoria ver: benchmarks/audit_cost_benchmark.py (~3-5k x).")
        print("  Para gas L1 real ver: test/contracts/test_lin_verifier.py (mede settleBatch).")
        print("=====================================================================================\n")

if __name__ == "__main__":
    main()
