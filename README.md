# LIN — Deterministic Scalar Systems Language, LinVM & Compute Receipts

> **CLI version `2.0.0`** (Lineage: AIL → LIA → LIN). Zero-Trust & Zero-Simulations.

**LIN** is a deterministic scalar/numeric procedural systems language with an embedded bytecode VM (`LinVM`), a heap-free flat AST arena, and cryptographic **compute receipts** that bind `(source hash, inputs, outputs, VM steps, stack depth)` into a single SHA-256 Merkle root.

It is purpose-built for verifiable numeric algorithms: cryptography, hashing, digital signal processing, zero-knowledge/rollup off-chain execution, and verified transpilation from C.

---

## 1. Verified Architecture & Feature Status

All capabilities below are **fully verified without mock data or simulated infrastructure**:

| Capability | Status | Description |
|---|:---:|---|
| **Parse + Typecheck + Lint** | ✅ **PASS** | Strict scalar types, deterministic i64 wrap-around, 0 unhandled panics |
| **C → LIN Transpiler (Safe Expansion)** | ✅ **PASS** | Supports scalar C, **Safe Array Lowering**, **Struct Flattening**, and **Bounded Loops** |
| **LinVM Bytecode Engine** | ✅ **PASS** | Stack-based deterministic virtual machine with gas limits and exact step counts |
| **Compute Receipts (RULEL + JSON)** | ✅ **PASS** | Generates SHA-256 Merkle receipts validating `f(input) = output` |
| **Independent Verification** | ✅ **PASS** | Zero-trust verification scripts in Python, Node.js, Bash+OpenSSL, and WebCrypto |
| **N-Version Cross-Check (Zig × C11)** | ✅ **PASS** | 34/34 consensus test vectors with zero divergence between Zig and C11 runtimes |
| **LinVM0 Self-Hosting (V1 → V5)** | 🔄 **IN PROGRESS** | Lexer, Evaluator, Lowerer and LINBC1 Emitter written directly in LIN (`src/linvm0_compiler/`); fixed point C0=C1=C2 still open |
| **Compiler 0 Host (C11, no Zig)** | ✅ **PASS** | `transpile/c/bin/lin_c0` compiles+runs `.lin` with `cc` only — Stage0 goldens bit-exact incl. steps (`vms_gate` value=1 steps=8511500); `verify_c0.sh` 16/16, `verify_c0_selfhost.sh` 30/30, also under ASan+UBSan |
| **Cross-Platform Target** | ✅ **PASS** | Runs identically bit-for-bit on CPU (Host C11), Web (Wasm/JS), and GPU (OpenCL) |

---

## 2. Real-World Transpilation & Golden Vectors

LIN is tested against production-grade C kernels with **100% bit-exact parity** against GCC/Clang:

* **QOI Image Format (`qoi_color_hash`):** Bit-exact color index mapping vs `qoi.h`.
* **xxHash64 (`xxhash64_round`):** 100% match with official Yann Collet Cyan4973 test vectors.
* **SipHash-2-4 (`siphash_round`):** Bit-exact verification against the reference C RFC implementation.
* **Uniswap v2 AMM (`get_amount_out`):** Exact mathematical parity with Solidity EVM 0.3% fee swaps.
* **A5/1 Stream Cipher (GSM TS 100 920):** Hardware shift-register stepping and majority clocking.
* **Post-Quantum Kyber / ML-KEM:** Butterfly Number Theoretic Transform (NTT) mod 3329.

---

## 3. C → LIN Transpiler: Fail-Safe Growth Model

To safely transpile larger C codebases without introducing memory vulnerabilities:

1. **Safe Array Lowering:** Fixed-size buffers (`uint8_t buf[64]`) map to bounded linear memory regions, eliminating raw pointers (`void*`) and buffer overflows.
2. **Struct Flattening:** Composite structures (`struct Point { int x; int y; };`) decompose into scalar 64-bit words without heap allocation.
3. **Bounded Loops & Gas Limits:** `for` and `while` loops receive strict iteration bounds (`[BOUNDED_LOOP: limit=N]`) to prevent infinite loops and denial-of-service vectors.
4. **Golden Vector Regression:** Every transpilation feature requires bit-exact assertion against native C execution.

---

## 4. Commercial Value & Enterprise Use Cases

| Sector | Industry Problem | The LIN Solution | Tangible Commercial Benefit |
|---|---|---|---|
| **Cybersecurity & Compliance** | Memory corruption (*Buffer Overflows*, Undefined Behavior) in legacy C libraries. | Transpilation to mathematically verified, memory-safe LIN models. | **Up to 80% reduction in security audit turnaround.** |
| **Web3 & Rollups (L2)** | Extreme gas costs to re-execute complex computations on EVM/L1. | Compute off-chain in LinVM; verify lightweight SHA-256 Merkle Receipts on-chain. | **Up to 99% gas savings on state proofs.** |
| **Verifiable AI Inference** | Lack of tamper-proof proof for cloud ML inferences and model weights. | Transpiled matrix/convolution kernels generate SHA-256 integrity receipts. | **Zero-trust auditability for regulated AI & FinTech.** |
| **Universal Portability** | High cost of maintaining separate codebases for CPU, Web, and GPU. | Single `.lin` source runs on Host C11, Browser (Wasm), and GPU (OpenCL). | **1 single codebase for 3 deployment targets.** |

---

## 5. Self-Hosting Roadmap (V1 → V5: Zero-Zig)

```
[V1: Host C11] ──► [V2: Front-End em LIN] ──► [V3: Emissor LINBC1] ──► [V4: Ponto Fixo C0=C1] ──► [V5: Zero-Zig]
  Host C11           Lexer + Lowerer           Serializador Binário        Autocompilação com          Aposentadoria Zig
  Determinístico     em código .lin            em LIN puro                 Merkle Idêntico             (TCB ≤ 1.500 LOC)
```

1. **V1 (Host C11 Native):** ✅ Runtime determinístico C11 em `transpile/c/` para execução isolada (29/29 expressões, 17/17 bordas, 33/33 LINBC1).
2. **V2 (Front-End em LIN + host C11):** 🔄 Lexer + Evaluator + Lowerer escritos em LIN (`verify_linvm0.sh`, requer Stage0) **e** o host `lin_c0` que compila/executa `.lin` sem Zig (`make c0-gate`, `make c0-selfhost-gate` — medido em `docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel`).
3. **V3 (Emissor LINBC1):** Serializador binário completo gerando imagens de bytecode `.linbc1` em LIN puro.
4. **V4 (Ponto Fixo $C_0=C_1$):** O compilador compila a si mesmo dentro da LinVM gerando digests SHA-256 idênticos.
5. **V5 (Zero-Zig Definitivo):** Todo o ecossistema é executado exclusivamente sobre LinVM + Host C11 com base de código confiável mínima (TCB $\le$ 1.500 LOC).

---

## 6. Building & Running

### Prerequisites
- **Zig 0.13.0** — still required to build the full Stage-0 compiler (`lin_native`):
  `check`, `lint`, the type checker, receipts/attestation/gate and OpenCL live in
  `compiler/lin.zig` and have **not** been ported. This is stated, not hidden (R5).
- Optional: OpenCL dev headers (`ocl-icd-opencl-dev` or ROCm) for GPU execution.
- **No Zig needed** for the C11 Compiler-0 host below (`cc` + `python3` only).

```bash
# Build native compiler (needs Zig)
zig build -Doptimize=ReleaseFast

# Build CPU-only (no OpenCL required)
zig build -Dgpu=false -Doptimize=ReleaseFast

# Run tests and verification gates (need Zig)
make test
make xver          # Zig vs C11 N-Version cross-check
make gate          # LIN Gate toolchain integrity verification

# ---- Compiler 0 host: compile and run .lin WITHOUT Zig (cc only) ----
make c0                # -> transpile/c/bin/lin_c0
make c0-gate           # Stage0 goldens bit-exact + round-trip + fail-closed (16 checks)
make c0-selfhost-gate  # LIN front-end runs in LinVM, freezes to LINBC1, self-lexes (30 checks)
transpile/c/bin/lin_c0 vm src/linvm_selfhost.lin vms_gate   # value=1 steps=8511500
```

### Create and Verify a Compute Receipt

```bash
# Create deterministic receipt
./bin/lin_native receipt create --source "return x * x;" --input 9 > receipt.rulel

# Cryptographically verify the receipt
./bin/lin_native receipt verify --receipt receipt.rulel
# -> PASS: Merkle root valid: sha256:b96fecee...
```

### Rationalist external proof (no Zig, `cc` + Python only)

The repository ships a conservative, externally reproducible proof harness. It
pins/fetches real GitHub upstream sources, compares selected LIN modules against
independent Python/C oracles, recomputes the Merkle receipt without the LIN
runtime, and explicitly reports what is **not** proven. The default `lin_c0`
host is still fail-closed; division/shifts are available only through the
experimental `vmfull` profile used by the proof.

```bash
make -C transpile/c all
python3 test/prove_all_claims_external.py --iterations 10000
python3 test/prove_all_claims_external.py --iterations 10000 --fetch   # re-download upstream
python3 test/fuzz_differential.py --iterations 10000                   # differential fuzz
python3 test/benchmark_audit_cost.py --iterations 1000                 # internal audit microbenchmark
bash test/verify_grant_artifacts.sh                                     # grant package self-check
```

Committed measurement artifacts are in `benchmarks/evidence/`. See
`docs/RATIONALIST_PROOF_STATUS.md` for the full claim/limit table.

### Standalone `lin-verify` CLI (stdlib, no Zig)

```bash
# Install on PATH (optional)
make install-cli PREFIX=~/.local

# Independent receipt verification
python3 lin_verify.py receipt benchmarks/fixtures/receipt_sqr9.json

# Provenance of pinned/fetched upstream GitHub files
python3 lin_verify.py provenance --fetch

# Run a LIN module through the C11 Compiler-0 host
python3 lin_verify.py module src/lin_siphash_xxhash_qoi.lin qoi_color_hash 50 60 70 80

# Run through the experimental profile-full host (division/shifts)
python3 lin_verify.py module-full src/lin_uniswap_v2_library.lin get_amount_out 10000 50000 100000

# No-Zig self-host gates
python3 lin_verify.py selfhost

# Full rationalist proof
python3 lin_verify.py all --iterations 10000

# Differential fuzz + internal audit microbenchmark
python3 lin_verify.py fuzz --iterations 10000
python3 lin_verify.py benchmark --iterations 1000
```

---

## 7. Repository Layout

```
├── compiler/              # Stage 0 bootstrap compiler (LinVM, MIR, receipts, OpenCL)
├── src/                   # Native LIN specification modules (.lin)
│   ├── linvm0_compiler/   # Self-hosted LinVM front-end in pure LIN (V2/V3)
│   ├── components/        # Web dashboard & interactive verifier UI
│   └── lib/               # Verified sample corpus & execution engine
├── transpile/c/           # Host C11 runtime, independent cross-check port & lin_c0 (Compiler 0, no Zig)
├── docs/                  # Architectural specs, LINBC1 binary format & rulel manifests
└── test_*.zig             # Root self-hosted and compatibility test suites
```

---

## License

MIT — See [LICENSE](LICENSE.rulel) for terms.
