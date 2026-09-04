# Grant Application: Lin-Audit — Verifiable AMM Settlement & Reconciliation

> **Nota de honestidade (mantenedor, ler antes de submeter):**
> A Uniswap Foundation está em processo de fechamento/unificação (aprovado pela
> DAO em dez/2025): a maioria do staff migra para a Uniswap Labs, e os grants
> ficam com um time pequeno administrando o orçamento restante (~US$ 100M
> reservados), depois migram para o "growth budget" sob Labs. Confirme no
> momento da submissão qual canal está ativo (Foundation ou Labs) — o conteúdo
> desta proposta é portável para o Ethereum Foundation ESP, que é o alvo
> primário recomendado (`docs/GRANT_FUNDING_STRATEGY.md`).
> O repositório ainda é **privado**; torne-o público antes de submeter (um
> reviewer clicando no link de um repo privado descarta a candidatura).

## 1. Project Overview
- **Project Name:** Lin-Audit (Verifiable AMM Settlement & Reconciliation Engine)
- **Category:** Developer Tooling / Protocol Infrastructure (alinhado às
  prioridades públicas da UF: *protocol tooling*, *developer onboarding*,
  *open-source contributions*)
- **Requested Amount:** $45,000 USD (non-dilutive grant)
- **Project Duration:** 3 Months (3 Milestones)
- **Repository:** github.com/kbelludoo/lin-open (to be made public)
- **License:** MIT

---

## 2. Problem Statement
AMM trading bots, market makers, and institutional liquidity providers execute
thousands of swaps daily across Uniswap V2/V3. Reconciling their internal
ledgers against on-chain reality is error-prone and expensive:

1. **No cryptographic proof** — off-chain audit logs (Python/JS scripts, SaaS
   databases) can be silently altered and are not reproducible by a third party.
2. **Lack of determinism** — float approximations and integer-width mismatches
   between the off-chain runtime and the EVM cause false alarms or missed
   slippage leaks.
3. **High audit cost** — re-executing traces on full/archival nodes is expensive
   for continuous accounting.

---

## 3. Proposed Solution
Lin-Audit is a **deterministic bytecode engine (LinVM)** specialized in
multiword (`uint256`) arithmetic and fail-closed state reconciliation, with an
independent, dependency-light verifier (Python stdlib + a C11 host).

Key capabilities (all measured, none asserted without evidence):

- **Bit-exact parity** with the canonical Uniswap V2 `getAmountOut` math
  (0.3% fee, integer 256-bit), verified against an independent 256-bit oracle
  and against real Mainnet swaps.
- **Canonical receipts (LCR2/LCR4):** each swap produces a compact binary leaf
  binding image digest, chain ID, transaction hash, pool address, log index,
  reported/actual amounts, exact integer delta, and execution status code;
  block hash is anchored when resolved at ingestion.
- **Cheap client-side verification:** batches of audited operations anchor into
  SHA-256 Merkle roots. Measured: verifying a block ≈ **5.3 µs** (Python stdlib)
  / ≈ **1.6 µs** (C host) vs re-executing it ≈ **26 ms** — ~5,000× cheaper
  (`benchmarks/audit_cost_benchmark.py`). Verification is `O(log B)` in Merkle
  depth, `O(1)` for the fixed `B=4` pilot block.
- **Fail-closed classification:** 5 fraud classes detected inside the LinVM
  (amount mismatch, on-chain revert misreported, slippage breach, pool
  misattribution, decimal-scale error) + 2 admission rules in the host (tx
  uniqueness/replay, completeness vs block). 0 false positives on clean data.

---

## 4. Evidence already completed (reproducible)

1. **Differential fuzz:** 400,003 vectors vs independent oracles (QOI 100k,
   Uniswap math 100,003, SipHash/xxHash 200k) — **0 divergences**
   (`test/prove_all_claims_external.py --iterations 100000`).
2. **uint256 single-shot engine:** 1,000/1,000 vs a 256-bit oracle; 18-decimal
   canonical vector → `1662497915624478906`
   (`test/pilot_harness/test_u256_differential_1000.py`).
3. **Real Ethereum Mainnet settlement:** 50 real swaps from blocks
   25900475–25900661 (USDC/WETH pool `0xb4e16d0…`), reserve-reconstructed from
   `Sync`/`Swap` logs; **50/50 bit-exact** in ~0.5 s (~9 ms/swap, ~58.1M VM
   steps) (`test/pilot_harness/test_live_ethereum_batch_50.py`). Spot-verified
   against Etherscan.
4. **Adversarial reconciliation:** 5 fraud classes classified by the LinVM +
   2 admission rules in the host = 7/7 detected, 0 false positives
   (`test/pilot_harness/test_reconciliation_adversarial_7.py`).
5. **Honest audit-cost benchmark** and **frozen formal spec manifest**
   (`docs/SPEC_FREEZE_1_0.rulel`).

---

## 5. Roadmap & Deliverables

### Milestone 1 — Automated ingestion & multi-pool coverage ($15,000, month 1)
- Continuous `Sync`/`Swap` listener (WebSocket/HTTP RPC) with pre-swap reserve
  reconstruction and **real block-hash anchoring**.
- Coverage for the top Uniswap V2 pairs (DAI, USDT, WBTC, …).
- Dataset publication format + `lin-audit` ingestion command.

### Milestone 2 — Uniswap V3 concentrated-liquidity math ($18,000, month 2)
- Multiword integer implementation of V3 tick math and `SqrtPriceX96`
  square-root price in deterministic Lin bytecode.
- Differential harness vs the official Uniswap V3 core math.
- LCR4 receipts for concentrated-liquidity swaps.

> **Risco declarado:** M2 (V3 tick math) é o item mais difícil e novo; o
> escopo exato (número de curvas/faixas cobertas) será congelado com o reviewer
> no início do milestone.

### Milestone 3 — Production CLI & open-source toolkit ($12,000, month 3)
- Packaged `lin-audit` CLI: audit ingestion, discrepancy report, Merkle proof
  generation/verification.
- Public benchmark suite, docs, tutorials for bot operators and DeFi auditors.
- GitHub Action for automated CI trade reconciliation.

---

## 6. Budget breakdown
- Core engineering & bytecode implementation: $25,000
- RPC/indexing infrastructure: $8,000
- Adversarial testing, documentation, open-source packaging: $12,000
- **Total: $45,000 USD**

---

## 7. What this is NOT (honest scope)
- It is **not a ZK proof system** and does not compete with RISC Zero/SP1/Jolt:
  Lin-Audit provides **Merkle receipts + deterministic fail-closed execution**,
  independently verifiable in plain Python/hashlib.
- It does **not** claim on-chain gas savings, "faster than LLVM/C/Rust", or full
  protocol security (routing, storage, reentrancy are out of scope — see
  `docs/RATIONALIST_PROOF_STATUS.md`).
- The reconciliation classifier is currently scalar i64; amounts above 2^64 are
  truncated (flagged at runtime). Promoting it to multiword u256 is on the M1/M2
  path.
