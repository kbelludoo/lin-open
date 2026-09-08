# Ethereum Ecosystem Support Program (ESP) — Project Inquiry

## 1. Project Title & Applicant Information
- **Project Name:** Lin-Audit: Reproducible Ethereum Transaction Verifier & Deterministic DeFi State Reconciliation
- **Applicant:** Lin Core Contributors
- **Repository:** [github.com/kbelludoo/lin-open](https://github.com/kbelludoo/lin-open) (Public Open Source Repository)
- **Track:** Cryptography & Infrastructure / Developer Tooling & Verification
- **Requested Funding:** $30,000 USD (Non-dilutive Grant)
- **Duration:** 6 Months (3 Milestones)
- **License:** Open Source (MIT / Apache 2.0 Compatible)

---

## 2. Objective & Executive Summary
Automated Market Makers (AMMs) on Ethereum settle billions in daily trading volume. Today, validating that off-chain records match confirmed on-chain events forces participants and researchers to either re-simulate blocks inside expensive archive nodes or blindly trust third-party centralized indexers and unverified floating-point scripts.

**Lin-Audit** is an open-source, reproducible toolkit built to:
1. **Recalculate Ethereum transaction hashes** directly from raw bytes across all envelope types (Legacy, EIP-2930, EIP-1559, EIP-4844) using canonical RLP and Keccak-256;
2. **Verify transaction inclusion in finalized blocks** via block headers, transaction indices, and `transactionsRoot`;
3. **Produce independent cryptographic receipts** for deterministic DeFi state transitions (Uniswap V2 AMM invariant $x \cdot y = k$) executed inside a confined, zero-heap, multiword integer engine (`LinVM`).

Lin-Audit does not attempt to replace archive nodes or index the entire history of Ethereum. It is a focused, falsifiable verification and audit toolkit.
 
### Architectural Boundary: Deterministic LinVM Kernel + Thin I/O Host
Lin-Audit balances high technical differentiation with strict risk control by maintaining a clean separation:
- **LinVM Execution Kernel (Profile `LIN-ETH-1`):** Canonical RLP parsing, typed transaction envelope identification (Types 0, 1, 2, 3), Keccak-256 permutation, hash comparison, and receipt generation.
- **Thin Host (C11 / Reference Tooling):** Operational I/O, file reading, RPC transport, and JSON receipt formatting.
- **Independent Oracles:** Python reference (`tools/lin_audit_tx.py`), C11 host, Geth, and Reth for multi-way differential verification.
- **Explicit Non-Goals for LinVM in M1:** No HTTP/TLS networking, no database engines, and no full chain indexing in bytecode.

---

## 3. Empirical Proofs in Repository (Already Verifiable)
The repository features working, reproducible code:
- **Unbiased Mainnet Dataset (`mainnet_unfiltered.json`):** 157 contiguous swaps across 200 blocks (25.900.848..25.901.047) without selection bias. Identifies 88.54% EXACT_INPUT and 11.46% OVERPAID_INPUT (routers/aggregators). Cataloged in `docs/DATASETS.md`.
- **Deterministic 256-bit Settlement Engine (`u256_settlement_engine.lin`):** Multiword integer arithmetic (16 limbs × 16 bits) implementing Uniswap V2 math without floating-point or hardware division. Parity verified against Python big-int in 157/157 transactions (785 VM runs) and 2,000 legacy vectors.
- **Formal Sensitivity Theorem (`docs/EVM_AMM_MATHEMATICAL_SENSITIVITY.md`):** Documents the exact discrete floor division resolution limit ($\Delta R_{out}^{\text{min}} \ge \lceil \frac{D}{997 \cdot A_{in}} \rceil$), explaining why sub-threshold perturbations are truncated to zero by EVM floor arithmetic.
- **Reproducible Reference Runners:** Both C11 CPU reference (`u256_kernel_cpu_ref.c`) and physical GPU runner (`u256_opencl_host.c`) verify identical results and detect tampered datasets.
- **M1-A: Independent Reference Implementations in Python & Pure Mojo (`tools/lin_audit_tx.py` & `tools/lin_audit_tx.mojo`):** Canonical RLP parser/reserializer, bit-exact Keccak-256 in Python and pure Mojo 1.0+ (zero Python imports), envelope support for Legacy (0), EIP-2930 (1), EIP-1559 (2), and EIP-4844 (3), 17-test compliance/mutation harness (`test/ethereum_tx/test_m1_compliance.py`), specifications ([`docs/M1_SPEC.md`](M1_SPEC.md), [`docs/M1_THREAT_MODEL.md`](M1_THREAT_MODEL.md), [`docs/M1_KECCAK_IMPLEMENTATION.md`](M1_KECCAK_IMPLEMENTATION.md), [`docs/MIGRATION_PATH_MOJO_TO_LIN.md`](MIGRATION_PATH_MOJO_TO_LIN.md)), and CI workflow (`.github/workflows/m1-ethereum-tx.yml`).
- **M1-B.1: First Executable Keccak-256 Core in LinVM (`src/lin_ethereum_keccak.lin` & `test/ethereum_tx/test_linvm_keccak.py`):**
  - AST structurally accepted by the frozen bootstrap compiler (`compiler/lin.zig -- verify`).
  - Implementation with fixed arrays and without dynamic heap allocation in Lin code.
  - Executes Keccak-f[1600] across 24 rounds on 25 lanes (64-bit) in LinVM via minimal C11 host.
  - Automated bit-exact parity demonstrated for `Keccak-256("")` against Python reference (`c5d246...`), with explicit fail-closed word mismatch rejection and NIST SHA3-256 distinction.
  - Formal 3-tier tracking documented in [`docs/m1_phase_comparison.csv`](m1_phase_comparison.csv) and [`docs/m1_phase_comparison.svg`](m1_phase_comparison.svg).

---

## 4. Work Plan & Milestones ($30,000 USD / 6 Months)

| Milestone | Deliverables | Target Timeline | Allocation |
| :--- | :--- | :---: | :---: |
| **M1: Canonical Transaction Verifier** | **M1-A (Delivered):** Independent pure Mojo reference verifier (`tools/lin_audit_tx.mojo`, zero CPython runtime dependency) with bit-exact Keccak-256 recalculation, baseline Python prototype, and mutation suite.<br>**M1-B (Grant Scope):** Execute migration trajectory (`Python -> Mojo -> LinVM`), port Keccak-256/RLP to the LinVM execution kernel under profile `LIN-ETH-1` with fail-closed bounds, 4-way differential validation (LinVM vs. Mojo vs. Python vs. Geth/Reth), and scaling to 10,000 Mainnet fixtures. | Months 1–2 | $10,000 |
| **M2: Auditable Ingestion & Block Inclusion** | Incremental JSON-RPC ingestion daemon with persistent checkpoints, reorg detection, `transactionsRoot` validation, and multi-source cross-checking to detect data omission. | Months 3–4 | $10,000 |
| **M3: Lin-Audit DeFi & External Review** | Integration of verified logs (`Sync`/`Swap`) with the LinVM execution kernel for Uniswap V2 reconciliation, issuance of cryptographic LCR4 receipts, public CI, and an independent third-party external security review. *(Uniswap V3 and full MPT scoped as roadmap extensions).* | Months 5–6 | $10,000 |

---

## 5. Budget Allocation
- **Core Engineering (0.5 FTE, 6 months):** $21,000
- **Independent External Review:** $4,500
- **Testing Infrastructure, RPC endpoints & CI:** $2,500
- **Documentation & Educational Resources:** $2,000
- **Total:** **$30,000 USD**
