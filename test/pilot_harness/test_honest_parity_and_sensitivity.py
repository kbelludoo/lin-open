#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suíte HONESTA de paridade e sensibilidade — u256_settlement_engine.lin (R5: no overclaim).

O que esta suíte NÃO faz:
  * não pré-filtra o dataset pela própria fórmula que está testando;
  * não calibra o tamanho de um "ataque" até que ele seja detectado;
  * não chama "oráculo EVM" uma expressão Python.

O que ela FAZ:
  FASE 1  Paridade: executa o motor Lin real (LinVM via transpile/c/bin/lin_bc1_run)
          sobre cada swap e compara com (a) o amount_out do evento Swap on-chain e
          (b) a referência big-int Python. Reporta separadamente por classe do
          dataset (EXACT_INPUT / EXACT_OUTPUT / OVERPAID_INPUT ...). Se o dataset
          for um dos legados pré-filtrados, isso é declarado em letras garrafais.
  FASE 2  Sensibilidade: para uma amostra de swaps, encontra por busca binária o
          MENOR delta em amount_in / reserve_in / reserve_out que altera a saída
          inteira, e confronta com o limite teórico da divisão de chão. Este é o
          resultado honesto no lugar de "100% de detecção": perturbações abaixo do
          limite são INVISÍVEIS para a EVM e, portanto, para qualquer reimplementação
          bit-exata dela.
  FASE 3  Guardas fail-closed (-1 entradas zero, -2 overflow 256 bits) no motor Lin.
  FASE 4  Gera o buffer binário determinístico (128 B/swap: ain, rin, rout, expected;
          big-endian) consumido por examples/defi_settlement_proof/u256_opencl_host.c,
          para que o resultado de GPU seja reproduzível a partir do JSON versionado.

Uso:
  python3 test/pilot_harness/test_honest_parity_and_sensitivity.py \
      [--json test/pilot_harness/mainnet_real_swaps_2000.json] [--limit 300] \
      [--sens-sample 40] [--bin /tmp/swaps.bin]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C0 = ROOT / "transpile/c/bin/lin_c0"
RUN = ROOT / "transpile/c/bin/lin_bc1_run"
CORE = ROOT / "examples/defi_settlement_proof/u256_settlement_engine.lin"
M64 = (1 << 64) - 1
U256 = (1 << 256) - 1


def ref_amount_out(a_in: int, r_in: int, r_out: int) -> int:
    fee = a_in * 997
    return (fee * r_out) // (r_in * 1000 + fee)


class LinEngine:
    def __init__(self):
        for b in (C0, RUN):
            if not b.exists():
                sys.exit(f"[!] {b} ausente. Rode: make -C transpile/c bin/lin_c0 bin/lin_bc1_run")
        self.tmp = Path(tempfile.mkdtemp(prefix="lin_u256_"))
        self.image = self.tmp / "u256.linbc"
        subprocess.run([str(C0), "image", str(CORE), "-o", str(self.image)],
                       check=True, capture_output=True, text=True, timeout=60)
        self.hex = self.image.read_bytes().hex()
        self.calls = 0

    @staticmethod
    def _words(x: int):
        ws = [(x >> (64 * i)) & M64 for i in range(4)]
        return [w - (1 << 64) if w >= (1 << 63) else w for w in ws]  # VM usa int64 com sinal

    def _call(self, args, idx):
        self.calls += 1
        p = subprocess.run([str(RUN), "--hex", self.hex, "settle_u256_word", *map(str, args), str(idx)],
                           check=True, capture_output=True, text=True, timeout=60)
        m = re.search(r"\bresult=(-?\d+)\b", p.stdout)
        if not m or 'status="EVALUATED"' not in p.stdout:
            raise RuntimeError("recibo da VM malformado")
        return int(m[1])

    def settle(self, a_in: int, r_in: int, r_out: int):
        """Retorna (status, amount_out|None). status: 1 ok, -1 entrada zero, -2 overflow."""
        args = self._words(a_in) + self._words(r_in) + self._words(r_out)
        st = self._call(args, -1)
        if st != 1:
            return st, None
        out = 0
        for i in range(4):
            out |= (self._call(args, i) & M64) << (64 * i)
        return 1, out


def load_dataset(path: Path):
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "records" in data:  # formato unfiltered
        recs = [r for r in data["records"] if "amount_in" in r]
        policy = data.get("filter_policy", "?")
        return recs, policy, True
    # legado: lista com amount_in/reserve_in/reserve_out/expected_out_real
    recs = []
    for s in data:
        recs.append({**s, "amount_out": s["expected_out_real"], "class": "EXACT_INPUT (pré-filtrado)"})
    return recs, "LEGADO: dataset pré-filtrado por `(num//den)==expected_out` no ingestor", False


def min_detectable_delta(a_in, r_in, r_out, field, direction, max_exp=90):
    """Menor |delta| (no sentido `direction`) que altera floor(num/den). Busca binária em delta."""
    base = ref_amount_out(a_in, r_in, r_out)

    def out_with(d):
        v = {"amount_in": a_in, "reserve_in": r_in, "reserve_out": r_out}
        v[field] += direction * d
        if v[field] <= 0:
            return None
        return ref_amount_out(v["amount_in"], v["reserve_in"], v["reserve_out"])

    hi = 1
    while hi < (1 << max_exp):
        o = out_with(hi)
        if o is None:
            return None
        if o != base:
            break
        hi *= 2
    else:
        return None
    lo = hi // 2
    while lo + 1 < hi:  # invariante: out_with(lo)==base, out_with(hi)!=base
        mid = (lo + hi) // 2
        o = out_with(mid)
        if o is None or o != base:
            hi = mid
        else:
            lo = mid
    return hi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "test/pilot_harness/mainnet_real_swaps_2000.json"))
    ap.add_argument("--limit", type=int, default=300, help="máx. swaps na fase 1 (cada um = 5 execuções da VM)")
    ap.add_argument("--sens-sample", type=int, default=40)
    ap.add_argument("--bin", default=None, help="caminho do buffer 128B/swap para o host OpenCL")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    recs, policy, unfiltered = load_dataset(Path(args.json))
    print("=" * 88)
    print(" SUÍTE HONESTA: PARIDADE LinVM + ANÁLISE DE SENSIBILIDADE (divisão de chão da EVM)")
    print("=" * 88)
    print(f"[dataset] {args.json}")
    print(f"[dataset] política de filtro: {policy}")
    if not unfiltered:
        print("[AVISO]   Este dataset foi PRÉ-FILTRADO pela fórmula getAmountOut no ingestor.")
        print("          Paridade 100% aqui prova apenas consistência interna, NÃO cobertura da Mainnet.")
        print("          Para cobertura real use tools/ingest_mainnet_unfiltered.py.")
    print(f"[dataset] registros com (amount_in, reserve_in, reserve_out): {len(recs)}")
    dist = Counter(r["class"] for r in recs)
    for k, v in dist.most_common():
        print(f"          {k:<32} {v:>6} ({100 * v / len(recs):6.2f}%)")

    eng = LinEngine()
    print(f"[engine]  {CORE.relative_to(ROOT)} -> LINBC1 sha256={eng.image.read_bytes()[-32:].hex()}")

    # ---------------- FASE 1: paridade por classe ----------------
    print("\n[FASE 1] Paridade Lin <-> referência big-int <-> amount_out on-chain (por classe)")
    rng = random.Random(args.seed)
    sample = recs if len(recs) <= args.limit else rng.sample(recs, args.limit)
    per_class = defaultdict(lambda: Counter())
    lin_vs_ref_mismatch = []
    for r in sample:
        a, ri, ro, onchain = r["amount_in"], r["reserve_in"], r["reserve_out"], r["amount_out"]
        st, lin_out = eng.settle(a, ri, ro)
        ref = ref_amount_out(a, ri, ro)
        c = per_class[r["class"]]
        c["n"] += 1
        if st != 1:
            c["lin_rejected"] += 1
            continue
        if lin_out == ref:
            c["lin==ref"] += 1
        else:
            lin_vs_ref_mismatch.append((r["tx_hash"], lin_out, ref))
        if lin_out == onchain:
            c["lin==onchain"] += 1
    for cls, c in per_class.items():
        print(f"  {cls:<32} n={c['n']:<5} lin==ref {c['lin==ref']:>5}/{c['n']}   "
              f"lin==onchain {c['lin==onchain']:>5}/{c['n']}   rejeitados={c['lin_rejected']}")
    if lin_vs_ref_mismatch:
        print(f"  [FALHA] {len(lin_vs_ref_mismatch)} divergências Lin vs referência big-int:")
        for t, l, rf in lin_vs_ref_mismatch[:5]:
            print(f"     {t} lin={l} ref={rf}")
    else:
        print(f"  [OK] motor Lin == referência big-int em {sum(c['n'] for c in per_class.values())} swaps "
              f"({eng.calls} execuções da VM). Isso é a alegação que o código sustenta.")
    print("  Nota: lin==onchain só é esperado em EXACT_INPUT. Em EXACT_OUTPUT/OVERPAID a divergência\n"
          "        é do comportamento do usuário/roteador, não do motor — e deve ser reportada, não escondida.")

    # ---------------- FASE 2: sensibilidade ----------------
    print("\n[FASE 2] Sensibilidade: menor delta que altera floor(num/den)  (n=%d)" % min(args.sens_sample, len(recs)))
    print("  Limite teórico de invisibilidade (reserve_out): delta < den/(997*a_in)  ⇒ saída inalterada.")
    print("  Qualquer 'detecção de fraude' abaixo desses limites é matematicamente impossível para a EVM.")
    ssample = recs if len(recs) <= args.sens_sample else rng.sample(recs, args.sens_sample)
    rows = []
    for r in ssample:
        a, ri, ro = r["amount_in"], r["reserve_in"], r["reserve_out"]
        den = ri * 1000 + a * 997
        theo_rout = den // (997 * a)  # floor(den/(997 a)): deltas <= isso podem ser invisíveis
        rows.append({
            "tx": r["tx_hash"], "pool": r.get("pool_name", "?"),
            "d_ain+": min_detectable_delta(a, ri, ro, "amount_in", +1),
            "d_ain-": min_detectable_delta(a, ri, ro, "amount_in", -1),
            "d_rin+": min_detectable_delta(a, ri, ro, "reserve_in", +1),
            "d_rout-": min_detectable_delta(a, ri, ro, "reserve_out", -1),
            "theo_rout": theo_rout,
        })
    hdr = f"  {'pool':<10} {'tx':<14} {'Δain+':>8} {'Δain-':>8} {'Δrin+':>14} {'Δrout-':>18} {'den/(997·ain)':>18}"
    print(hdr)
    for w in rows:
        print(f"  {w['pool']:<10} {w['tx'][:12]+'..':<14} {str(w['d_ain+']):>8} {str(w['d_ain-']):>8} "
              f"{str(w['d_rin+']):>14} {str(w['d_rout-']):>18} {w['theo_rout']:>18}")
    invisible_1wei_rout = sum(1 for w in rows if (w["d_rout-"] or 0) > 1)
    invisible_1wei_ain = sum(1 for w in rows if (w["d_ain+"] or 0) > 1)
    invisible_1wei_rin = sum(1 for w in rows if (w["d_rin+"] or 0) > 1)
    print(f"\n  Swaps em que ±1 wei é INVISÍVEL (saída idêntica): amount_in {invisible_1wei_ain}/{len(rows)}, "
          f"reserve_in {invisible_1wei_rin}/{len(rows)}, reserve_out {invisible_1wei_rout}/{len(rows)}")
    # Teorema (divisão de chão): out = floor(997·a·r_out / den). Um passo de 1 unidade em `out`
    # corresponde a den/(997·a) unidades de r_out. Logo: delta ≥ ceil(den/(997·a)) é SEMPRE
    # detectado; delta menor é detectado apenas se cruzar a fronteira do próximo inteiro (depende
    # do resto). O menor delta detectável observado deve portanto satisfazer 1 ≤ Δrout- ≤ ceil(den/(997·a)).
    theo_ok = all(w["d_rout-"] is None or 1 <= w["d_rout-"] <= w["theo_rout"] + 1 for w in rows)
    print(f"  Consistência com o teorema (1 ≤ Δrout- ≤ ceil(den/(997·ain))): {'OK' if theo_ok else 'VIOLAÇÃO — investigar'}")
    print("  Garantia real: adulteração de reserve_out ≥ den/(997·ain) é SEMPRE detectada; abaixo disso, NÃO há garantia.")

    # ---------------- FASE 3: guardas ----------------
    print("\n[FASE 3] Guardas fail-closed do motor Lin")
    checks = [
        ("amount_in = 0", (0, 10**12, 10**21), -1),
        ("reserve_in = 0", (10**6, 0, 10**21), -1),
        ("reserve_out = 0", (10**6, 10**12, 0), -1),
        ("amount_in*997 estoura 256 bits", (U256, 10**12, 10**21), -2),
        ("numerador estoura 256 bits", (U256 // 1000, 10**12, U256 // 2), -2),
    ]
    all_ok = True
    for name, (a, ri, ro), want in checks:
        st, _ = eng.settle(a, ri, ro)
        ok = st == want
        all_ok &= ok
        print(f"  [{'OK' if ok else 'FALHA'}] {name:<34} status={st} (esperado {want})")

    # ---------------- FASE 4: buffer OpenCL ----------------
    if args.bin:
        buf = bytearray()
        n = 0
        for r in recs:
            if not r["class"].startswith("EXACT_INPUT"):
                continue  # o kernel compara com amount_out; só faz sentido em EXACT_INPUT
            for v in (r["amount_in"], r["reserve_in"], r["reserve_out"], r["amount_out"]):
                buf += v.to_bytes(32, "big")
            n += 1
        Path(args.bin).write_bytes(bytes(buf))
        print(f"\n[FASE 4] buffer OpenCL: {n} registros EXACT_INPUT x 128 B -> {args.bin}")
        print(f"         rode: examples/defi_settlement_proof/u256_opencl_host {args.bin}")

    print("\n" + "=" * 88)
    print(" RESUMO HONESTO")
    print("=" * 88)
    print(f"  Motor Lin == big-int em todos os swaps testados: {'SIM' if not lin_vs_ref_mismatch else 'NÃO'}")
    print(f"  Guardas fail-closed: {'SIM' if all_ok else 'NÃO'}")
    print(f"  Dataset cobre a Mainnet sem filtro: {'SIM' if unfiltered else 'NÃO (pré-filtrado)'}")
    print("  'Detecção 100% de adulterações': NÃO ALEGADA — ver limites de sensibilidade acima.")
    return 0 if (not lin_vs_ref_mismatch and all_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
