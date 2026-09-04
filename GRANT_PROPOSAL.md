# Grant Proposal — Lin-Audit: Reproducible Ethereum Transaction Verifier & Deterministic DeFi State Reconciliation

**Project Title:** Lin-Audit — A Minimalist, Reproducible Verification Toolkit for Ethereum Transactions, Block Inclusion, and Deterministic DeFi State Reconciliation

**Category:** Public Goods, Developer Tooling, Cryptography, Verification Infrastructure

**Requested Amount:** $30,000 USD (Non-dilutive Grant)
**Duration:** 6 months (3 milestones)
**Repository:** [github.com/kbelludoo/lin-open](https://github.com/kbelludoo/lin-open) (Open Source, MIT / Apache 2.0 compatible)

---

## 1. Executive Summary & Objective

Automated Market Makers (AMMs) and decentralized protocols on Ethereum settle billions of dollars in transaction volume. Today, verifying off-chain trading data or reconciling historical state transitions forces developers, researchers, and institutional auditors to either:
1. Re-simulate blocks inside full archive nodes (expensive, high operational overhead, heavy hardware requirements); or
2. Blindly trust third-party centralized indexers, JSON-RPC endpoints, and ad-hoc floating-point Python/JS scripts.

The objective of **Lin-Audit** is:
> **To build an open-source, reproducible toolkit capable of recalculating Ethereum transaction hashes from raw bytes, verifying their inclusion in finalized blocks, and generating independent cryptographic receipts for deterministic DeFi state reconciliation within the confined LinVM.**

### Crucial Architectural Separation of Layers:
- **Ethereum Identity Layer (Keccak-256 + RLP / EIP-2718):** Proves that raw transaction bytes match the canonical `transaction_hash`.
- **Block Inclusion Layer (Block Number, Index, TransactionsRoot & Finality):** Proves the transaction was accepted by network consensus without relying on trusted indexer attestations.
- **Deterministic Analysis Layer (LinVM + Canonical Merkle SHA-256 Receipts):** Proves the algebraic correctness of state transitions (e.g., AMM invariant $x \cdot y = k$) inside a pure, zero-heap, zero-syscall execution kernel.

Lin-Audit does not attempt to be a full archive node or an all-encompassing EVM indexer. It is a **focused, verifiable, and falsifiable audit toolkit**.

---

## 2. Realistic Scope & Explicit Non-Goals

To maintain rigorous technical integrity and avoid overclaiming:

| What Lin-Audit IS | What Lin-Audit IS NOT (Explicit Non-Goals) |
| :--- | :--- |
| An open-source transaction and log verification toolkit | NOT a replacement for an Ethereum archive node (geth/reth/erigon) |
| A deterministic multiword arithmetic engine (`uint256`) for AMM math | NOT a full EVM emulator or general-purpose smart contract verifier |
| A multi-source incremental ingestor with checkpointing and reorg guards | NOT an attempt to index all 2.7+ billion transactions of Ethereum history |
| A provable receipts engine (LCR4) binding execution inputs and outputs | NOT a Zero-Knowledge (ZK) rollup or SNARK prover |
| A rigorously benchmarked tool with published sensitivity resolution bounds | NOT claiming "faster than LLVM" or "100% fraud detection for sub-threshold wei" |

---

## 3. Current State of Art in Repository (Empirical Evidence)

The repository already features working, reproducible code with zero simulation:

1. **Unbiased Mainnet Dataset (`mainnet_unfiltered.json`):**
   - 157 contiguous swaps captured across 200 blocks (25.900.848..25.901.047) without selection bias.
   - Measures actual network distribution: **88.54% EXACT_INPUT** ($getAmountOut$) and **11.46% OVERPAID_INPUT** (routers/aggregators/dust), with **0 K_VIOLATION**. Full dataset catalog documented in `docs/DATASETS.md`.
2. **Deterministic LinVM Execution Core (`u256_settlement_engine.lin`):**
   - Full 256-bit multiword arithmetic (16 limbs × 16 bits) implementing Uniswap V2 math without floating-point or hardware division.
   - Bit-exact parity against independent Python big-int reference across 157/157 transactions (785 VM runs) and 2,000 legacy vectors.
3. **Formal Mathematical Sensitivity Theorem (`docs/EVM_AMM_MATHEMATICAL_SENSITIVITY.md`):**
   - Documents the exact discrete floor division resolution limit ($\Delta R_{out}^{\text{min}} \ge \lceil \frac{D}{997 \cdot A_{in}} \rceil$), explaining why sub-threshold perturbations are truncated to zero by EVM floor arithmetic.
4. **Reproducible Reference Runners:**
   - Both C11 CPU reference (`u256_kernel_cpu_ref.c`) and physical GPU runner (`u256_opencl_host.c`) verify identical results and detect tampered datasets.
5. **M1-A: Independent Reference Prototype & Test Harness (`tools/lin_audit_tx.py`):**
   - Implemented canonical RLP recursive parser and roundtrip reserializer with fail-closed rejection of non-minimal integers, unconsumed residual bytes, and oversized buffers.
   - Bit-exact pure-Python Keccak-256 reference implementation strictly distinguished from NIST FIPS 202 SHA3-256.
   - Full support for envelopes: Legacy (type `0`), EIP-2930 (type `1`), EIP-1559 (type `2`), and EIP-4844 (type `3`).
   - Automated 17-test compliance and 7-scenario adversarial mutation suite (`test/ethereum_tx/test_m1_compliance.py`) running in GitHub Actions (`.github/workflows/m1-ethereum-tx.yml`).
   - Formal specification (`docs/M1_SPEC.md`), threat model (`docs/M1_THREAT_MODEL.md`), and LinVM implementation specification for profile `LIN-ETH-1` (`docs/M1_KECCAK_IMPLEMENTATION.md`).

---

## 4. Work Plan & Milestones ($30,000 USD / 6 Months)

```
[ Month 1-2: M1 ] ─────────► [ Month 3-4: M2 ] ─────────► [ Month 5-6: M3 ]
Ethereum Tx Verifier          Auditable Ingestion           Lin-Audit DeFi (V2)
RLP, EIP-2718, Keccak-256     Checkpoints, Reorgs, MPT      Receipts, CI, Ext. Review
```

### Milestone 1: Canonical Ethereum Transaction Verifier ($10,000 — Months 1–2)
- **Status:** **M1-A (Independent Reference Prototype)** is completed and verifiable in repository (`tools/lin_audit_tx.py`).
- **M1-B Grant Funding Scope:**
  - Port the Keccak-256 and RLP core into the **LinVM execution kernel** under profile `LIN-ETH-1` (`docs/M1_KECCAK_IMPLEMENTATION.md`).
  - Implement bounds-checked indexing, `rotl64`, bitwise operations, and permutation rounds directly in Lin bytecode (`.linbc`).
  - Differential 3-way cross-verification: **LinVM vs. Python reference vs. C11 host vs. Geth/Reth**.
  - Scale the verified public corpus from seed fixtures to **10,000 Mainnet transactions** (Types 0, 1, 2, 3) with published digest manifests.
- **Deliverables:** Integrated LinVM executable (`.linbc`), minimal C11 host harness, and verified 10,000-tx compliance benchmark.
- **Acceptance Criteria:** Bit-exact parity across LinVM, Python reference, and Ethereum client digests with zero divergence across 10,000 fixtures and 100% fail-closed rejection on mutation tests.

### Milestone 2: Auditable Ingestion Engine & Inclusion Verification ($10,000 — Months 3–4)
- Build an incremental, resilient JSON-RPC ingestion daemon with persistent checkpoints (`checkpoint.json`).
- Implement reorg detection and block finality validation:
  - Verification of `transactionsRoot` against block headers.
  - Multi-source cross-checking (detecting discrepancies or data omission between multiple RPC providers).
- **Deliverable:** Standalone ingestor producing deterministic, byte-for-byte reproducible dataset bundles.
- **Acceptance Criteria:** Re-running the ingestor over identical block ranges produces bit-exact identical binary and JSON manifests across separate executions.

### Milestone 3: Lin-Audit DeFi Reconciliation & External Audit ($10,000 — Months 5–6)
- Integrate ingestion pipeline with the LinVM deterministic execution kernel.
- Automated reconciliation of Uniswap V2 state transitions from verified logs (`Sync` and `Swap`).
- Issuance of immutable cryptographic receipts (LCR4 standard) binding the verified Ethereum `tx_hash` to the LinVM execution digest.
- Independent external security review of the codebase.
- **Deliverable:** End-to-end reproducible pipeline, public GitHub Actions CI, and published audit report.
- **Acceptance Criteria:** CI runs end-to-end verification of Mainnet test corpuses on every pull request, accompanied by an independent external review report.

*(Note: Uniswap V3 concentrated liquidity math and full generalized Merkle-Patricia Trie proofs are formally scoped as roadmap extensions for Phase 2).*

---

## 5. Budget Breakdown

The grant funds independent research and development at modest rates:

| Category | Description | Allocation |
| :--- | :--- | :---: |
| **Core Engineering** | 6 months research and systems development (0.5 FTE) | $21,000 |
| **Independent External Review** | Third-party security/code audit by external reviewer | $4,500 |
| **Infrastructure & CI** | RPC nodes, testing endpoints, GitHub Actions runners | $2,500 |
| **Documentation & Educational Resources** | Formal documentation, reproducibility guides, diagrams | $2,000 |
| **Total** | | **$30,000** |

---

## 6. Public Goods Value for the Ethereum Ecosystem

1. **Client-Independent Auditability:** Enables researchers, DAOs, and protocol treasuries to independently verify on-chain trades without running archival infrastructure.
2. **Defensive DeFi Analytics:** Distinguishes genuine AMM swaps from aggregator slippage, MEV sandwich extraction, and fee-on-transfer token anomalies with exact mathematical proofs.
3. **Reproducible Public Datasets:** Publishes unpruned, verified datasets of on-chain activity for academic and industrial research.
4. **100% Open Source:** Licensed under MIT/Apache 2.0 with all benchmarks reproducible with standard compilers.
