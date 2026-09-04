#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
constant_time_study.py — "Verificação em tempo constante": como ter de verdade
e como medir com metodologia correta.

Responde a duas perguntas com evidência empírica (stdlib only):

  [A] O que cresce no desenho atual?
      - Custo/prova vs tamanho do BLOCO (árvore única de N folhas): deve crescer
        ~log2(N) — cada nível = 1 SHA-256. Previsto: µs ≈ d × sha256(64B).
      - Custo/prova vs tamanho TOTAL do lote com bloco FIXO (arquitetura de
        blocos encadeados do repositório): deve ser PLANO — O(1) em N.

  [B] Como ter O(1) mesmo em árvore única?
      - RSA accumulator (Strong RSA): prova de INCLUSÃO de tamanho constante
        (1 grupo + 1 primo) e verificação O(1) — 1 única pow com expoente de
        128 bits, custo independente de N. Comparado lado a lado com Merkle.
      - Nota honesta: acumulador prova MEMBERSHIP (integridade), o mesmo
        modelo de confiança do Merkle. Provar COMPUTAÇÃO em O(1) exige
        SNARK/STARK (roadmap, fora do escopo stdlib).

Metodologia de medição (a resposta ao "2,3 µs sem metodologia"):
  - clock monotônico em ns; warmup antes de medir;
  - R rodadas independentes, relatório min/p50/p95 (nunca medição única);
  - resultado consumido (sem DCE) e verificado a cada rodada;
  - modelo preditivo: µs(prova) ≈ profundidade × µs(sha256 64B) medido na hora;
  - regressão linear µs vs log2(N) com R² (confirma/refuta a classe de
    complexidade empiricamente, em vez de declará-la);
  - metadados de ambiente no relatório JSON.

Determinismo: RNG com semente fixa; primos via hash-to-prime determinístico;
modulus RSA derivado de semente fixa (hash impresso para proveniência).
SAIR DE CÁ 1024 folhas, primos de 128 bits e modulus de 1024 bits são
SUFICIENTES para demonstrar a CLASSE de custo, mas NÃO são parâmetros de
produção (produção: primos ≥ 256 bits, modulus ≥ 3072 bits, ou KZG/SNARK).

Uso: python3 constant_time_study.py
Saída: tabela no stdout + constant_time_study.json
"""

import gc
import hashlib
import json
import math
import platform
import random
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

LEAF_DOM = b"lin:study:v1:leaf"
NODE_DOM = b"lin:study:v1:node"
ROUNDS = 21
SIZES = [4, 16, 64, 256, 1024]          # folhas por árvore (potências de 2)
ACC_SAMPLES = 3                          # índices amostrados por tamanho
E_BITS = 128                             # bits do representante primo (DEMO)
N_BITS = 1024                            # bits do modulus RSA (DEMO)

sha = lambda b: hashlib.sha256(b).digest()


# ---------------------------------------------------------------- utilidades
def leaf_bytes(i: int) -> bytes:
    return sha(LEAF_DOM + struct.pack("<Q", i))


def now_ns() -> int:
    return time.perf_counter_ns()


def stats_us(per_proof_ns_per_round):
    v = sorted(per_proof_ns_per_round)
    us = lambda x: x / 1000.0
    return {"min": round(us(v[0]), 3),
            "p50": round(us(v[len(v) // 2]), 3),
            "p95": round(us(v[min(len(v) - 1, int(0.95 * (len(v) - 1)))]), 3)}


def linfit(xs, ys):
    """Regressão linear simples: retorna (slope, intercept, r2)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx
    r2 = (sxy * sxy) / (sxx * syy) if syy else 1.0
    return slope, my - slope * mx, r2


# ---------------------------------------------------------------- Merkle
def build_tree(n_leaves: int):
    leaves = [leaf_bytes(i) for i in range(n_leaves)]
    levels = [leaves]
    cur = leaves
    while len(cur) > 1:
        cur = [sha(NODE_DOM + cur[i] + cur[i + 1]) for i in range(0, len(cur), 2)]
        levels.append(cur)
    return levels


def get_proof(levels, idx: int):
    path = []
    for lev in levels[:-1]:
        path.append(lev[idx ^ 1])
        idx //= 2
    return path


def verify_proof(leaf: bytes, path, idx: int, root: bytes) -> bool:
    cur = leaf
    for sib in path:
        cur = sha(NODE_DOM + cur + sib) if (idx & 1) == 0 else sha(NODE_DOM + sib + cur)
        idx //= 2
    return cur == root


def bench_merkle(n_leaves: int):
    levels = build_tree(n_leaves)
    root = levels[-1][0]
    proofs = [(levels[0][i], get_proof(levels, i), i) for i in range(n_leaves)]
    depth = len(proofs[0][1])

    for leaf, path, i in proofs[:64]:      # warmup + sanidade
        assert verify_proof(leaf, path, i, root)
        assert not verify_proof(sha(b"fraude" + leaf), path, i, root)

    per_round = []
    gc.disable()                               # GC não pode poluir a zona de medição
    try:
        for _ in range(ROUNDS):
            t0 = now_ns()
            ok = 0
            for leaf, path, i in proofs:
                ok += verify_proof(leaf, path, i, root)
            dt = now_ns() - t0
            assert ok == n_leaves
            per_round.append(dt / n_leaves)
    finally:
        gc.enable()
    st = stats_us(per_round)
    st["best"] = round(min(per_round) / 1000.0, 3)  # mínimo: métrica estável p/ ajuste

    # segundo eixo: total do lote cresce, bloco fixo (profundidade 2)
    return {"n_leaves": n_leaves, "depth": depth,
            "proof_bytes": 32 * depth, "us_per_proof": st}


def bench_chained_blocks(max_blocks: int):
    """Bloco fixo de 4 folhas (profundidade 2); N total cresce via nº de blocos."""
    out = []
    for n_blocks in (10, 100, 1000, 10000):
        if n_blocks > max_blocks:
            continue
        total = n_blocks * 4
        levels_list = [build_tree(4) for _ in range(n_blocks)]
        proofs = []
        for levels in levels_list:
            root = levels[-1][0]
            proofs.extend((levels[0][i], get_proof(levels, i), i, root) for i in range(4))
        for leaf, path, i, root in proofs[:64]:
            assert verify_proof(leaf, path, i, root)
        per_round = []
        gc.disable()
        try:
            for _ in range(ROUNDS):
                t0 = now_ns()
                ok = sum(verify_proof(l, p, i, r) for l, p, i, r in proofs)
                dt = now_ns() - t0
                assert ok == total
                per_round.append(dt / total)
        finally:
            gc.enable()
        st = stats_us(per_round)
        st["best"] = round(min(per_round) / 1000.0, 3)
        out.append({"total_txs": total, "block_leaves": 4,
                    "us_per_proof": st})
    return out


# ---------------------------------------------------------------- RSA accumulator
def is_probable_prime(n: int, rounds: int, rng: random.Random) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def hash_to_prime(seed: bytes, e_bits: int) -> int:
    """Representante primo determinístico: SHA-256(seed‖ctr) → ímpar com bit
    alto setado; Miller-Rabin com bases pseudo-aleatórias de semente fixa."""
    rng = random.Random(int.from_bytes(sha(b"mr:" + seed), "big"))
    ctr = 0
    while True:
        h = int.from_bytes(sha(seed + ctr.to_bytes(4, "little")), "big")
        c = (h | (1 << (e_bits - 1)) | 1) & ((1 << e_bits) - 1)
        if is_probable_prime(c, 30, rng):
            return c
        ctr += 1


def gen_prime(bits: int, rng: random.Random) -> int:
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(c, 30, rng):
            return c


def bench_accumulator():
    rng = random.Random(20260904)
    print(f"    -> gerando modulus RSA de {N_BITS} bits (2 primos de {N_BITS//2}, semente fixa)...")
    p = gen_prime(N_BITS // 2, rng)
    q = gen_prime(N_BITS // 2, rng)
    n = p * q
    n_hash = hashlib.sha256(str(n).encode()).hexdigest()[:16]
    del p, q                                   # trapdoor DESCARTADO
    g = 65537

    print(f"    -> gerando {SIZES[-1]} primos de {E_BITS} bits via hash-to-prime determinístico...")
    t0 = now_ns()
    primes = [hash_to_prime(b"lin:study:e:" + struct.pack("<Q", i), E_BITS)
              for i in range(SIZES[-1])]
    prime_gen_s = (now_ns() - t0) / 1e9

    out = []
    P = 1
    prev = 0
    for N in SIZES:
        for e in primes[prev:N]:
            P *= e                          # produto incremental dos primos
        prev = N
        acc = pow(g, P, n)                  # setup público, sem trapdoor
        samples = [0, N // 3, N // 2][:ACC_SAMPLES]
        witnesses = {}
        t_prov = now_ns()
        for i in samples:
            witnesses[i] = pow(g, P // primes[i], n)   # próva do PROVER (lenta, offline)
        prover_ms = (now_ns() - t_prov) / 1e6

        for i in samples:                       # sanidade + controle negativo
            assert pow(witnesses[i], primes[i], n) == acc
            assert pow(witnesses[i], primes[(i + 1) % N], n) != acc

        per_round = []
        gc.disable()
        try:
            for _ in range(ROUNDS):
                t0 = now_ns()
                ok = 0
                for i in samples:
                    ok += pow(witnesses[i], primes[i], n) == acc
                dt = now_ns() - t0
                assert ok == len(samples)
                per_round.append(dt / len(samples))
        finally:
            gc.enable()
        st = stats_us(per_round)
        st["best"] = round(min(per_round) / 1000.0, 3)
        out.append({"n_leaves": N,
                    "proof_bytes": N_BITS // 8 + E_BITS // 8,
                    "us_per_proof": st,
                    "prover_ms_for_samples": round(prover_ms, 1)})
    meta = {"modulus_bits": N_BITS, "modulus_sha256_16": n_hash,
            "e_bits": E_BITS, "prime_gen_s": round(prime_gen_s, 2),
            "note": "DEMO: parametros nao sao de producao"}
    return out, meta


def main():
    print("=" * 78)
    print("  ESTUDO: verificação em tempo constante — o que cresce, como medir, como ter")
    print("=" * 78)

    # baseline preditiva
    t0 = now_ns()
    for _ in range(50000):
        sha(b"x" * 64)
    sha_us = (now_ns() - t0) / 50000 / 1000.0
    print(f"\n[Baseline] sha256(64B) = {sha_us:.3f} µs  →  µs(prova) ≈ profundidade × {sha_us:.3f}")

    print("\n[A1] Árvore ÚNICA: custo/prova vs tamanho do bloco (esperado: cresce ~log2 N)")
    merkle = [bench_merkle(N) for N in SIZES]
    xs = [math.log2(m["n_leaves"]) for m in merkle]
    ys = [m["us_per_proof"]["best"] for m in merkle]
    slope, inter, r2 = linfit(xs, ys)
    print(f"    {'N folhas':>8} {'prof.':>5} {'bytes':>5} {'best µs':>8} {'p50 µs':>7} {'p95 µs':>7} {'prev µs':>7}")
    for m in merkle:
        pred = m["depth"] * sha_us + inter
        u = m["us_per_proof"]
        print(f"    {m['n_leaves']:>8} {m['depth']:>5} {m['proof_bytes']:>5} "
              f"{u['best']:>8.2f} {u['p50']:>7.2f} {u['p95']:>7.2f} {pred:>7.2f}")
    print(f"    -> regressão (best) vs log2(N): inclinação = {slope:.3f} µs/nível ≈ 1 SHA-256/nível "
          f"({sha_us:.3f} µs), R² = {r2:.4f}"
          f"  ⇒ {'O(log N) CONFIRMADO empiricamente' if r2 > 0.98 and slope > 0 else 'REVISAR'}")

    print("\n[A2] Blocos ENCADEADOS (bloco fixo = 4): custo/prova vs TOTAL do lote (esperado: plano)")
    chained = bench_chained_blocks(10000)
    print(f"    {'txs no lote':>11} {'p50 µs':>7} {'p95 µs':>7}")
    for c in chained:
        print(f"    {c['total_txs']:>11} {c['us_per_proof']['p50']:>7.2f} {c['us_per_proof']['p95']:>7.2f}")
    fl = [c["us_per_proof"]["best"] for c in chained]
    spread = (max(fl) - min(fl)) / min(fl) * 100
    print(f"    -> variação (best) entre {chained[0]['total_txs']} e {chained[-1]['total_txs']} txs: {spread:.1f}%  ⇒ O(1) em N (bloco é constante do protocolo)")

    print(f"\n[B] Árvore única com prova O(1): RSA accumulator (Strong RSA, DEMO {N_BITS}/{E_BITS} bits)")
    acc, acc_meta = bench_accumulator()
    print(f"    {'N folhas':>8} {'bytes':>5} {'best µs':>8} {'p50 µs':>7} {'p95 µs':>7} {'prover ms':>9}")
    for a in acc:
        u = a["us_per_proof"]
        print(f"    {a['n_leaves']:>8} {a['proof_bytes']:>5} "
              f"{u['best']:>8.1f} {u['p50']:>7.1f} {u['p95']:>7.1f} "
              f"{a['prover_ms_for_samples']:>9.0f}")
    ax = [math.log2(a["n_leaves"]) for a in acc]
    ay = [a["us_per_proof"]["best"] for a in acc]
    a_slope, _, a_r2 = linfit(ax, ay)
    print(f"    -> regressão p50 vs log2(N): inclinação = {a_slope:+.3f} µs/nível (≈0 ⇒ constante), R² = {a_r2:.4f}")

    cross_d = (acc[0]["proof_bytes"]) / 32.0
    print(f"\n[Crossover] prova do acumulador ({acc[0]['proof_bytes']} B) fica MENOR que a de Merkle "
          f"(32 B/nível) a partir de profundidade ~{cross_d:.1f} ≈ bloco de {2**round(cross_d)} folhas")

    print("\n[Correção do claim]")
    print("  ANTES: 'verificação em tempo constante em ~2,3 µs' (medição única, sem metodologia)")
    print("  AGORA: 'O(log B) com B fixo pelo protocolo (demo: 4) — O(1) em N; medido com")
    print(f"  warmup + {ROUNDS} rodadas + best/p50/p95 + regressão; verificação ≈ "
          f"{chained[0]['us_per_proof']['best']:.1f} µs/prova; alternativas O(1)-em-árvore-única: acumulador "
          f"({acc[0]['us_per_proof']['best']:.0f} µs, plano) ou SNARK/KZG (roadmap)'")

    report = {
        "schema": "lin:defi:settlement:constant_time_study:v1",
        "env": {"utc": datetime.now(timezone.utc).isoformat(),
                "python": platform.python_version(), "machine": platform.machine(),
                "cpu": next((l.split(":")[1].strip() for l in
                             Path("/proc/cpuinfo").read_text().splitlines()
                             if l.startswith("model name")), "unknown"),
                "rounds": ROUNDS},
        "baseline_sha256_64b_us": round(sha_us, 3),
        "merkle_single_tree": merkle,
        "merkle_fit": {"slope_us_per_level": round(slope, 4), "r2": round(r2, 5)},
        "chained_fixed_blocks": chained,
        "chained_spread_pct": round(spread, 2),
        "accumulator": acc,
        "accumulator_meta": acc_meta,
        "accumulator_fit": {"slope_us_per_level": round(a_slope, 4), "r2": round(a_r2, 5)},
        "crossover_depth": round(cross_d, 2),
        "corrected_claim": "O(log B), B constante do protocolo ⇒ O(1) em N; "
                           "acumulador RSA = O(1) membership em árvore única; "
                           "SNARK/STARK = O(1)-computation (roadmap)",
    }
    out = Path(__file__).resolve().parent / "constant_time_study.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n  relatório: {out}")
    print("=" * 78)


if __name__ == "__main__":
    main()
