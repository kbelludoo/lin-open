# Deterministic AMM Settlement Co-processor & Merkle Compute Receipts: Empirical Benchmarks on Commodity GPUs

**Author:** [@kbelludoo](https://github.com/kbelludoo)  
**Implementation & Reproducibility:** [github.com/kbelludoo/lin-open](https://github.com/kbelludoo/lin-open)  
**License:** MIT / Apache-2.0  

---

### Abstract
Offloading verifiable state transitions from Ethereum L1 or rollups is traditionally approached through zkVMs (STARKs/SNARKs) or optimistic execution with dispute games. While general zkVMs provide succinct verification of arbitrary execution traces, their arithmetization and polynomial commitment phases impose a $10,000\times$ to $100,000\times$ prover overhead, requiring server clusters and substantial memory. 

In this post, we present empirical results from **LIN**, a deterministic numeric procedural systems language and GPU co-processor specifically designed for fixed-point AMM batch settlement and verifiable audit reconciliation. On a commodity consumer GPU ($200 AMD Radeon RX 6600, 28 CUs), our sovereign OpenCL pipeline processes **2,000 real Ethereum mainnet Uniswap v2 swaps in 1.70 milliseconds of kernel compute** (218 ms end-to-end cold wall-clock), enforces constant-product invariants ($x \cdot y \ge k$), and emits canonical **208-byte LCR2 SHA-256 Merkle compute receipts**. On-chain anchoring in Solidity (`contracts/LinReceiptVerifier.sol`) was measured on EVM (Foundry / Cancun) at **70,133 gas** for fresh root storage and **87,831 gas** with on-chain spot-check inclusion proofs.

---

### 1. Problem & Trade-off Space

Auditing DEX trade execution and reconciling internal trading ledgers against on-chain block execution is computationally expensive:
- **Full node re-execution:** Running millions of EVM traces across archival nodes requires high I/O and CPU overhead.
- **General zkVMs (RISC Zero, SP1, Jolt):** Proving a batch of 2,000 multiword integer swaps takes dozens of seconds to minutes and gigabytes of RAM.
- **The middle path:** For known deterministic numerical primitives (like AMM constant-product curves, multiword integer division, and cryptographic hashing), a **pure scalar numeric systems language** can run at native hardware speed on consumer GPUs, binding outputs to lightweight Merkle receipts.

---

### 2. Architecture: Zero-Heap Co-processor & LCR2 Receipts

```
[Mainnet Swaps] ──► [Sovereign GPU Kernel] ──► [LinVM Host C11] ──► [LCR2 Merkle Root]
2,000 swaps         AMD RX 6600 (1.7 ms)       TCB: 809 LOC         Anchored in L1
(USDC/USDT/UNI)     Parallel invariant check   Zero runtime heap    (70,133 gas)
```

1. **Physical GPU Execution:** The measured 2,000-swap settlement benchmark executes on physical AMD GPUs via hand-written OpenCL C (`examples/defi_settlement_proof/u256_opencl_kernel.cl`, 28 CUs, 1.70 ms kernel time). LIN's pure `.lin` native OpenCL C emitter (`src/lin_gpu_opencl_emitter.lin`) is currently proven across 4 canonical kernel families (affine, mix, bitfold, Kyber NTT) with 77 silicon targets on physical GPU hardware. Emitting the u256 AMM kernel directly from pure `.lin` source is an active roadmap milestone.
2. **Strict Host Runtime TCB & Cryptographic Merkle Engine:** The C11 host execution runtime (`lin_vm.c`, `lin_linbc1.c`, `lin_sha256.c`, `lin_common.c`) contains only **809 lines of C11 code**. No dynamic heap allocation occurs during settlement execution. Production cryptographic Merkle trees and LCR2 leaf packing are implemented in C (`merkle_sha256_u256_host.c`, `lin_sha256.c`). Python scripts serve strictly as cleanroom audit oracles for independent cross-verification.
3. **LCR2 Canonical Leaf Format (208 Bytes):**
   - Bytes `[0:4]`: Magic `LCR2`
   - Bytes `[8:40]`: `img_digest` (SHA-256 of the executed bytecode)
   - Bytes `[40:56]`: `run_id` and `tx_id` (u64 LE)
   - Bytes `[56:184]`: `amount_in`, `reserve_in`, `reserve_out`, `amount_out` (4 × 32-byte big-endian integers)
   - Bytes `[184:200]`: `steps` count and execution `status` code

Leaves are hashed with domain separation (`LIN:LEAF:1` and `LIN:NODE:1`) into a balanced SHA-256 Merkle tree. Any client or auditor can verify an inclusion proof in standard Python (`hashlib`) or in-browser WebCrypto in **~7.3 µs per block**.

---

### 3. Empirical EVM Gas Benchmarks (Foundry v1.8.1 + Live Anvil Receipts)

Rather than relying on theoretical estimates, the Solidity anchoring contract ([`contracts/LinReceiptVerifier.sol`](file:///home/k/Downloads/lin-master/contracts/LinReceiptVerifier.sol)) was deployed and tested with live receipts on Anvil (Cancun EVM, optimizer 200):

| Contract Call | Measured Gas | Status | Effective $/swap (÷2,000 @ 20 gwei, $3k ETH) |
|---|:---:|:---:|:---:|
| **Deploy `LinReceiptVerifier` (one-time)** | 718,682 | `0x1` | $0.0216 |
| **`settleBatch` (fresh Merkle root)** | **70,133** | `0x1` | **$0.00210** |
| **`settleBatch` (already anchored root)** | 50,233 | `0x1` | $0.00151 |
| **`settleBatchWithInclusionProof` (fresh root)** | **87,831** | `0x1` | **$0.00264** |
| **`settleBatchWithInclusionProof` (anchored root)** | 67,931 | `0x1` | $0.00204 |
| **Original L1 Tx Gas (Sum of 2,000 dataset swaps)** | 1,164,504,079 | - | $34.94 |

**Measured On-Chain Reduction:** **13,258× to 16,604× reduction** in on-chain gas consumption compared to direct L1 execution.

---

### 4. Dataset Honesty & Mainnet Realities

A critical lesson learned from analyzing on-chain datasets:
1. **Pre-filtered datasets create tautologies:** Traditional benchmarks filtered out swaps where `getAmountOut != actual_amount_out`, masking router behavior and slippage parameters.
2. **Unfiltered Mainnet Corpus ($N=157$, blocks 25900848..25901047):**
   - **88.54% (`EXACT_INPUT`):** Exactly matches the constant-product formula bit-for-bit.
   - **11.46% (`OVERPAID_INPUT`):** Swaps via router aggregators where users provided extra input or experienced dust rounding. The $k$-invariant was strictly preserved, but the output differed from pure atomic swap math.
   - **0% (`K_VIOLATION`):** Zero invariant violations detected across the sample.

---

### 5. Why Not General zkVMs?

| Feature | General zkVMs (RISC Zero / SP1) | LIN Deterministic Co-processor |
|---|---|---|
| **Proving Latency** | Tens of seconds to minutes | **1.70 milliseconds** (physical GPU) |
| **Hardware Reqs** | High-end data center GPUs, >32GB RAM | **$200 consumer GPU** (AMD RX 6600) |
| **On-Chain Gas** | ~250k–400k (Groth16/Plonk verifier) | **70k–88k gas** (Merkle anchor + spot check) |
| **Audit Tooling** | Complex circuit compilers | Python stdlib, C, or WebCrypto in <10 µs |

---

### 6. Next Steps & Invitation for Feedback

We are opening this work to the community for feedback on:
1. **Multi-pool topological ordering:** Handling atomic multi-hop swaps across interdependent pools without serial execution bottlenecks.
2. **Uniswap v3/v4 concentrated liquidity:** Extending the multiword numeric co-processor to handle `SqrtPriceX96` tick traversal.
3. **Dispute games:** Combining LIN's sub-millisecond receipts with an optimistic dispute game for rollup sequencers.

The codebase is fully open-source and reproducible in under 60 seconds:
```bash
git clone https://github.com/kbelludoo/lin-open.git
cd lin-open
make test-lin-sovereign
make verify-forge-gas
```

Feedback and peer review from EVM and L2 researchers are warmly welcomed!
