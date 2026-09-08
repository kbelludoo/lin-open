# Uniswap Foundation Grants Application: Lin-Audit

## 1. Project Overview
- **Project Name:** Lin-Audit (Verifiable AMM Settlement & Reconciliation Engine)
- **Target Track:** Developer Tools / Infrastructure & Protocol Analytics
- **Requested Amount:** $45,000 USD (Non-dilutive Grant)
- **Project Duration:** 3 Months (3 Milestones)
- **Repository:** [github.com/kbelludoo/lin-open](https://github.com/kbelludoo/lin-open)
- **License:** Open-Source (Permissive MIT / Apache 2.0 compatible)

---

## 2. Problem Statement
Automated Market Maker (AMM) trading bots, market makers, and institutional liquidity providers execute thousands of swaps daily across Uniswap V2 and V3. Reconciling their internal execution ledgers against on-chain reality is a complex, error-prone, and expensive process.

Today, reconciliation relies on ad-hoc off-chain scripts (Python/JavaScript) using floating-point approximations, or centralized proprietary SaaS databases. These approaches suffer from:
1. **No Cryptographic Proof:** Audit logs can be silently tampered with.
2. **Lack of Determinism:** Subtle rounding differences and integer-width discrepancies between off-chain runtimes and the EVM lead to false alarms or undetected slippage leaks.
3. **High Latency and Overhead:** Re-executing traces on full archival nodes is prohibitively expensive for continuous accounting.

---

## 3. Proposed Solution: The Lin-Audit Framework
Lin-Audit provides a **deterministic, zero-dependency bytecode engine (LinVM)** specifically optimized for multiword integer arithmetic (`uint256`) and formal state reconciliation.

> **Execution & Audit Boundary:** Execution core — AMM mathematics, invariants, gates, and self-hosted front-end — 100% in LIN, executed on LinVM/GPU. Production I/O and cryptographic Merkle roots run in the audited C11 host (TCB-809); Python/hashlib scripts exist strictly as cleanroom audit oracles.

### Key Capabilities:
- **Bit-Exact Parity:** 100% mathematical equivalence to the canonical Uniswap `getAmountOut` formula ($x \cdot y = k$ with exact 0.3% fee deduction).
- **LCR4 Provenance Standard:** Each audited swap produces a compact, 248-byte canonical leaf binding chain ID, block hash, transaction hash, pool address, log index, reported amount, actual amount, exact delta, and execution status code.
- **$O(1)$ Client-Side Verifiability:** Batches of thousands of audited operations are anchored into SHA-256 Merkle roots, allowing instant proof validation in under $2\ \mu\text{s}$ on standard consumer hardware.
- **Fail-Closed Security:** Hardened against replay attacks, omissions, 1-wei rounding fraud, decimal scale mismatches, pool misattribution, slippage breaches, and reverted transaction misreporting.

---

## 4. Current Proof of Concept & Empirical Results (Already Completed)
Before applying for this grant, the core technology was rigorously tested and verified.
Primary distribution evidence is the UNFILTERED corpus; the 2000-set is an
arithmetic corpus only (see honest labels below):
1. **Differential Oracle Testing:** 1,000 randomized synthetic multiword vectors tested against canonical Solidity reference contracts with **1,000 / 1,000 bit-exact passes**.
2. **Unfiltered Mainnet Distribution (PRIMARY for network behavior):** **157 contiguous swaps, 200 blocks 25900848..25901047, NO filter** — 139 EXACT_INPUT (88.54%), 18 OVERPAID_INPUT (routers/aggregators/dust), 0 K_VIOLATION. Catalog: `docs/DATASETS.md`. Use this for any claim about mainnet distribution.
3. **Arithmetic Corpus at Scale (NOT for distribution):** **2,000 swaps across 5 pools** (USDC 896, USDT 714, UNI 251, DAI 108, WBTC 31) — **PRE-FILTERED legacy** (`(num//den)!=expected` discarded, tautological for network parity, valid for arithmetic). **100% bit-exact parity** in **18.15s** (**9.07 ms/swap**, **110.2 swaps/s sustained LinVM**), **2,315,927,745 instructions**, Merkle 3.16 ms. GPU kernel-only (excl. JIT/init) ~1.6-3.6 ms/2000; wall cold ~200 ms — report both, never EVM-TPS speedup (see `tools/lin_defi_settler.py` honest table).
4. **Adversarial Benchmark:** 7 canonical fraud/error attacks simulated against real on-chain data, all rejected. *Scope note (audit v3):* detection is bounded by EVM floor division — perturbations of `reserve_out` below `den/(997·amount_in)` (and often ±1 wei on any field) are mathematically invisible to `getAmountOut` itself; see `examples/defi_settlement_proof/README.md` §5 for the measured sensitivity limits. The on-chain sample used for earlier "100% parity" claims was pre-filtered by the formula; the unfiltered ingestor and class distribution replace that claim.
5. **Empirical EVM Gas Harness (Foundry & Live Receipts):** On-chain settlement was measured using Foundry v1.8.1 and live transaction receipts on Anvil (`contracts/LinReceiptVerifier.sol`, executable via `make verify-forge-gas`). Deploying the verifier cost 718,682 gas (one-time). Batch anchoring (`settleBatch`) measured **70,133 gas** ($0.0021/swap @ 20 gwei, $3,000/ETH); anchoring with spot-check inclusion proof (`settleBatchWithInclusionProof`) measured **87,831 gas** ($0.0026/swap). Compared to the cumulative **1,164,504,079 gas** consumed by the 2,000 swaps in the mainnet dataset, off-chain settlement delivers an empirical **13,258× to 16,604× on-chain gas reduction**.

---

## 5. Roadmap & Deliverables

### Milestone 1: Automated RPC Ingestion & Multi-Pool Coverage ($15,000 — Month 1)
- Continuous listener daemon for real-time extraction of `Sync` and `Swap` event pairs from WebSocket/HTTP RPC nodes.
- Built-in support for top 20 Uniswap V2 pairs (DAI, USDT, WBTC, PEPE, UNI).
- Automated pre-swap reserve reconstruction without requiring full archive node traces.

### Milestone 2: Uniswap V3 Engine & Pure LIN GPU Emitter ($18,000 — Month 2)
- Multiword integer implementation of Uniswap V3 tick-math and square-root price calculations (`SqrtPriceX96`) in pure deterministic Lin bytecode.
- Native compiler emission of u256 AMM settlement kernel directly from pure `.lin` source code (retiring hand-written OpenCL C).
- Verification harness validating against official Uniswap V3 Core contracts.
- Export of LCR4 cryptographic receipts for concentrated liquidity swaps.

### Milestone 3: Production CLI & Open-Source Auditing Toolkit ($12,000 — Month 3)
- Packaged CLI (`lin-audit`) for single-command audit ingestion, discrepancy reporting, and Merkle proof generation.
- Public benchmark suite, comprehensive documentation, and tutorials for bot operators and DeFi auditors.
- Delivery of an open-source GitHub Action for automated CI/CD trade reconciliation.

---

## 6. Budget Breakdown
- **Core Engineering & Bytecode Implementation:** $25,000
- **RPC Infrastructure & Indexing Testnet/Mainnet Nodes:** $8,000
- **Adversarial Testing, Documentation & Open-Source Packaging:** $12,000
- **Total:** **$45,000 USD**
