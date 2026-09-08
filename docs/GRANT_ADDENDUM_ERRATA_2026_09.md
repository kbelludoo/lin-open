# Grant Addendum & Technical Errata (September 2026)

**Project:** LIN — Sovereign GPU AMM Settlement & Rollup Co-processor  
**Repository:** [github.com/kbelludoo/lin-open](https://github.com/kbelludoo/lin-open) (`master` branch)  
**Target:** Ethereum Foundation Ecosystem Support Program (ESP) & Uniswap Foundation Grants  

---

## 1. Executive Errata: Replacing Estimates with Measured Evidence

In strict accordance with project honesty rules (R4: *One digest, one meaning*; R5: *No overclaims*), this addendum supersedes all earlier preliminary estimates with empirically measured, reproducible data from live transaction receipts on EVM and physical AMD GPU hardware.

| Premise / Prior Claim | Prior Figure (Estimated) | Measured Empirical Reality | Verification Command |
|---|:---:|:---:|---|
| **EVM Batch Settlement Gas** | 25,000 – 45,000 gas | **70,133 gas** (`settleBatch`, fresh root)<br>**87,831 gas** (`settleBatchWithProof`) | `make verify-forge-gas` |
| **On-Chain Gas Reduction** | "Up to 99%" | **13,258× to 16,604× reduction** vs L1 re-execution | Live Anvil receipts (Foundry 1.8.1) |
| **GPU Settlement Speed** | 459,000+ TPS in 4.1ms | **Kernel:** 1.70 ms (1.17M swaps/s)<br>**Wall-Clock Cold:** 218 ms (9.1k swaps/s) | `make verify-gpu` |
| **Execution Runtime TCB** | ≤ 1,500 LOC | **809 LOC** core runtime (6.6k LOC full toolchain) | `wc -l transpile/c/lin_c/*.c` |
| **Dataset Parity Claim** | "100% on-chain parity" | Arithmetic corpus (N=2,000) vs Unfiltered (N=157): 88.5% exact, 11.5% router overpaid, 0 K-violations | `docs/DATASETS.md` |

---

## 2. On-Chain EVM Gas Audit (Receipt-Level)

The Solidity on-chain anchor contract ([`contracts/LinReceiptVerifier.sol`](../contracts/LinReceiptVerifier.sol)) was compiled with `solc 0.8.20` (optimizer 200 runs, Cancun EVM) and executed on Anvil using Foundry v1.8.1. All transactions confirmed with `status = 1`:

| Operation | Gas Used | ETH Cost @ 20 gwei | Amortized $/swap (÷2k swaps @ $3k ETH) |
|---|:---:|:---:|:---:|
| **Deploy `LinReceiptVerifier` (one-time)** | 718,682 | 0.01437 ETH | $0.0216 |
| **`settleBatch` (fresh Merkle root)** | **70,133** | 0.00140 ETH | **$0.00210** |
| **`settleBatch` (already anchored root)** | 50,233 | 0.00100 ETH | $0.00151 |
| **`settleBatchWithInclusionProof` (fresh root)** | **87,831** | 0.00176 ETH | **$0.00264** |
| **`settleBatchWithInclusionProof` (anchored root)** | 67,931 | 0.00136 ETH | $0.00204 |
| **L1 Individual Swaps (Dataset 2,000 sum)** | 1,164,504,079 | 23.290 ETH | $34.94 |

*Key finding:* The previous theoretical "25k–45k" estimate underestimated EVM state storage costs (`SSTORE` of new 32-byte roots). The empirical gas is 70k–88k. However, because actual L1 router/multicall swaps average ~582k gas per transaction, anchoring 2,000 swaps in a single batch still achieves an empirical **13,258× to 16,604× reduction** in on-chain gas consumption.

---

## 3. Positioning: Why LIN Instead of zkVMs (RISC Zero / SP1)?

Reviewers frequently ask: *"Why build a bespoke scalar systems co-processor rather than running Rust inside a general-purpose zkVM?"*

1. **Near-Zero Proving Overhead:** General zkVMs impose a $10,000\times$ to $100,000\times$ proving overhead due to STARK/SNARK arithmetization, requiring high-end data-center provers. LIN executes physical OpenCL kernels in **1.7 milliseconds on a $200 commodity consumer GPU** (AMD Radeon RX 6600).
2. **Minimal Verification Cost:** Unlike zk-SNARK verifiers that require ~250,000–400,000 gas for pairing cryptography on-chain, LIN anchors state via standard SHA-256 Merkle roots in **70,133 gas**.
3. **Auditable by Anyone in Seconds:** Receipts are strictly standard NIST SHA-256 leaves. Verification requires no circuit libraries—only standard Python (`hashlib`), WebCrypto in any browser, or C standard library in **< 10 microseconds**.

---

## 4. Formal Spec Freeze & Independent Review Budget

- **Specification Freeze:** The LIN v1.0 specification has been formally frozen in [`docs/SPEC_FREEZE_1_0.rulel`](SPEC_FREEZE_1_0.rulel) with `status = "FROZEN"`, locking the formal specification, LinVM ISA v1, LINBC1 bytecode format, verifiable compute receipt format, and Host C11 ABI to exact SHA-256 digests.
- **External Security Review:** To address the single-maintainer risk, the grant budget explicitly reserves **$4,500 USD** for an independent external audit of the smart contracts, receipt verification logic, and arithmetic invariants prior to mainnet deployment.

---

## 5. Technical Rigor: Architecture Truth, Emitter Scope & N-Version Oracles

To guarantee that the codebase withstands adversarial scrutiny from top-tier cryptographic auditors, the project enforces strict boundary definitions between LIN code, C11 host code, and Python oracles:

> *"Núcleo de execução — matemática AMM, invariantes, gates e front-end auto-hospedado — 100% em LIN, executado na LinVM/GPU. I/O e Merkle de produção rodam no thin host C11 auditado (TCB-809); scripts Python/hashlib existem **somente** como oráculos cleanroom, e todo número citado tem o comando que o reproduz."*

1. **GPU Emitter Scope (Physical GPU vs Roadmap Milestone):**
   - LIN's pure `.lin` OpenCL emitter ([`src/lin_gpu_opencl_emitter.lin`](../src/lin_gpu_opencl_emitter.lin)) currently compiles and dispatches 4 canonical kernel classes (affine, mix, bitfold, Kyber NTT butterfly), fully verified across 77 physical GPU silicon targets on AMD RX 6600 (`make verify-gpu`).
   - The measured 2,000-swap multiword integer kernel ([`examples/defi_settlement_proof/u256_opencl_kernel.cl`](../examples/defi_settlement_proof/u256_opencl_kernel.cl)) is hand-written OpenCL C. **Extending the LIN compiler to emit the u256 settlement kernel directly from pure `.lin` source is an explicit deliverable of Milestone 2.**
2. **Cryptographic Merkle Engine:**
   - Production cryptographic Merkle trees and LCR2 leaf packing are implemented in C11 within the strict 809 LOC runtime boundary ([`transpile/c/lin_c/lin_sha256.c`](../transpile/c/lin_c/lin_sha256.c) and [`examples/defi_settlement_proof/merkle_sha256_u256_host.c`](../examples/defi_settlement_proof/merkle_sha256_u256_host.c)).
   - Early algebraic models like `src/lin_binary_merkle_provenance.lin` are non-cryptographic affine toy models and are excluded from production settlement claims.
3. **True N-Version Cross-Verification Loops:**
   - [`tools/emit_batch_receipt.py`](../tools/emit_batch_receipt.py) functions as the Python test harness and reference big-int oracle.
   - The genuine N-version verification loops in the repository are:
     * **C11 Host (`lin_c0 receipt`) ↔ Cleanroom Verifiers (`lin_verify.py` / `verify_receipt.html`)**
     * **Physical GPU Kernel (AMD RX 6600) ↔ Big-Int Differential Oracle**
     * **LinVM Scalar Execution ↔ Native C Reference Implementations** (100% bit-exact across QOI, SipHash, and TinyExpr).

