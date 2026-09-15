#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Concurrent HTTP Benchmark Client for LIN Cache Gateway
"""

from __future__ import annotations

import concurrent.futures
import json
import time
import urllib.request
from urllib.error import HTTPError

URL = "http://127.0.0.1:9099"


def send_set(idx: int) -> float:
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{URL}/v1/cache/set",
        data=json.dumps({"key": f"user_session_{idx:08d}", "val": f"payload_data_{idx}"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        _ = resp.read()
    return (time.perf_counter() - t0) * 1000.0


def send_get(idx: int) -> float:
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{URL}/v1/cache/get?key=user_session_{idx:08d}")
    with urllib.request.urlopen(req, timeout=5) as resp:
        _ = resp.read()
    return (time.perf_counter() - t0) * 1000.0


def main():
    print("=" * 70)
    print("  LIN CACHE GATEWAY: CONCURRENT REAL-WORLD HTTP LOAD BENCHMARK")
    print("=" * 70)

    # 1. Check health
    with urllib.request.urlopen(f"{URL}/v1/cache/stats") as resp:
        initial_stats = json.loads(resp.read().decode("utf-8"))
    print(f"Connected to: {initial_stats['server']}")
    print(f"Kernel JIT in RAM: {initial_stats['compile_ms']:.2f} ms\n")

    # 2. Benchmark 500 concurrent SET requests
    n_ops = 500
    workers = 10
    print(f"[*] Disparando {n_ops} requisições de escrita (POST /set) com {workers} conexões concorrentes...")
    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        set_latencies = list(ex.map(send_set, range(n_ops)))
    t_total_set = time.perf_counter() - t_start
    set_latencies.sort()

    print(f"    -> Tempo total:    {t_total_set * 1000:.1f} ms")
    print(f"    -> Throughput:     {n_ops / t_total_set:.0f} req/s")
    print(f"    -> Latência p50:   {set_latencies[int(n_ops * 0.50)]:.2f} ms")
    print(f"    -> Latência p95:   {set_latencies[int(n_ops * 0.95)]:.2f} ms")
    print(f"    -> Latência p99:   {set_latencies[int(n_ops * 0.99)]:.2f} ms\n")

    # 3. Benchmark 500 concurrent GET requests
    print(f"[*] Disparando {n_ops} requisições de leitura (GET /get) com {workers} conexões concorrentes...")
    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        get_latencies = list(ex.map(send_get, range(n_ops)))
    t_total_get = time.perf_counter() - t_start
    get_latencies.sort()

    print(f"    -> Tempo total:    {t_total_get * 1000:.1f} ms")
    print(f"    -> Throughput:     {n_ops / t_total_get:.0f} req/s")
    print(f"    -> Latência p50:   {get_latencies[int(n_ops * 0.50)]:.2f} ms")
    print(f"    -> Latência p95:   {get_latencies[int(n_ops * 0.95)]:.2f} ms")
    print(f"    -> Latência p99:   {get_latencies[int(n_ops * 0.99)]:.2f} ms\n")

    # 4. Final stats from server
    with urllib.request.urlopen(f"{URL}/v1/cache/stats") as resp:
        final_stats = json.loads(resp.read().decode("utf-8"))

    print("[*] Estatísticas do Servidor após a Carga Real:")
    for k, v in final_stats.items():
        print(f"    - {k:20s}: {v}")

    print("\n" + "=" * 70)
    print("  RESULTADO: SERVIÇO 100% OPERACIONAL SOB TRÁFEGO DE REDE REAL")
    print("=" * 70)


if __name__ == "__main__":
    main()
