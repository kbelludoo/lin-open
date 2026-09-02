# Grant Proposal — LIN: Experimental Zero-Heap Verifiable State Kernel

**Project title:** LIN — An Experimental Zero-Heap State Engine for Verifiable
Off-Chain Computation and Cryptographic Auditability

**Category:** Developer Tooling, Cryptography, Formal Verification Infrastructure

**Requested amount:** $25,000 USD
**Duration:** 6 months (3 milestones)

---

## 1. Problem

High-value systems routinely run deterministic numeric code (AMM math, hashing,
serialization, pricing models) either
- on an expensive shared execution machine (EVM/L1), where re-execution is the
  only way to audit a result; or
- on an ordinary server in C/Rust, where a result can be altered without leaving
  a reproducible trace and where dynamic memory corruption is a real risk.

The gap is not "another fast language" — C/Rust/LLVM already win on execution
speed. The gap is **zero-trust auditability**: a compact, deterministic,
externally reproducible proof that `f(input) == output`, with a documented
fail-closed behavior when an operation is outside the accepted subset.

## 2. What LIN is (and is not)

LIN is a deterministic scalar/i64 kernel with:
- a flat, heap-free memory model;
- a tiny VM with a hard step limit and explicit fail-closed rejection;
- a canonical SHA-256 receipt (`source hash + output + steps + sp_at_ret`);
- an independent C11 implementation and an independent Python verifier.

It is **not**: an OS, a database, a blockchain layer, or a replacement for LLVM.
The project states this limitation in `docs/RATIONALIST_PROOF_STATUS.md`.

## 3. Existing evidence in this repository

No simulation. The following run with `cc` + Python only, no Zig:

```bash
make -C transpile/c all
python3 test/prove_all_claims_external.py --iterations 10000
```

Current observable results:
- 5 real upstream files fetched and SHA-256 verified (Uniswap v2/v3, OpenSSL
  SHA-256, QOI, TinyExpr).
- `qoi_color_hash` (from `phoboslab/qoi`) has exact parity against an
  independent Python oracle.
- `tinyexpr_fac` (from `codeplea/tinyexpr`) matches Python factorial over
  `0..20` and fails closed outside that range.
- An experimental `vmfull` profile executes the pure `UniswapV2Library` math
  (`get_amount_out`, `quote`, `get_amount_in`) and the SipHash/xxHash round
  kernels, matching independent Python oracles.
- Differential fuzz run on 2026-09-02: 10k QOI + 11,001 Uniswap + 20k hash
  + 24 TinyExpr vectors, all PASS in 47.771s
  (`benchmarks/evidence/fuzz_differential_20260902.json`).
- `lin_c_receipt` produces a Merkle root that Python independently recomputes;
  a tampered output is rejected.
- Internal audit microbenchmark (1,000 receipts): C11 producer ~1.1s vs Python
  verifier ~0.005s, all verified
  (`benchmarks/evidence/benchmark_audit_20260902.json`).
- Compiler-0 no-Zig gates pass (`verify_c0.sh`, `verify_c0_selfhost.sh`),
  and a standalone `lin_verify.py` CLI exists.

## 4. Milestones

### Milestone 1 — Formal semantics and reference documentation ($8,000, months 1–2)
- Publish grammar/semantics PDF/Markdown based on the `.rulel` specs.
- Make the C0 host behavior table explicit (accepted subset, rejected
  `VM_REJ_*`, wrapping arithmetic, fail-closed edges).
- Deliverable: `docs/AGENTS_EMENDA…` + human-readable `FORMAL_SPECIFICATION.md`.

### Milestone 2 — Standalone no-Zig compiler/interpreter and differential fuzzing ($10,000, months 3–4)
- Continue the existing experimental `vmfull` profile (division/shifts) behind a
  flag; the default `lin_c0` must stay fail-closed.
- Build a differential fuzz harness over the C11 host, Python oracle and (when
  available) the Zig Stage-0 build for 100,000 vectors.
- Deliverable: `make fuzz-differential`, `make c0-selfhost-gate`, external
  proof output. A working harness already exists
  (`test/fuzz_differential.py`); the remaining milestone work is running the
  100k target on CI and adding the Zig side when available.

### Milestone 3 — CLI verifier, docs, final report ($7,000, months 5–6)
- Ship `lin-verify` (Python stdlib, no Zig), consuming `.lin` + receipts and
  emitting PASS/FAIL with the recomputed Merkle root.
- Publish usage docs and a reproducible CI job.
- Deliverable: final report with measured coverage, known non-goals and honest
  security/performance boundaries.

A first stand-alone `lin-verify` already exists in this repository (`lin_verify.py`)
with commands `receipt`, `provenance`, `module`, `selfhost` and `all`. It is the
seed of the Milestone 3 deliverable.

## 5. Budget rationale
Salaries are intentionally modest (independent researcher). Most work is
compiler/runtime engineering, fuzz harnesses and documentation.

| Item | Cost |
|---|---|
| Researcher time (0.4 FTE, 6 months) | $18,000 |
| CI runners / domain / tooling | $2,000 |
| Independent audits (2 small external reviews) | $3,500 |
| Documentation/formatting | $1,500 |
| **Total** | **$25,000** |

## 6. Non-goals
- Do **not** claim "$1.8 trillion savings", "faster than LLVM", or "verified
  production-ready".
- The proof executes the **pure math functions** of `UniswapV2Library` on the
  experimental `vmfull` profile. It does **not** claim full protocol security,
  full OpenSSL execution, on-chain gas savings, or a production-ready
  compiler. Those remain `NOT-PROVEN` in `docs/RATIONALIST_PROOF_STATUS.md`.

## 7. Grant readiness checklist (current vs. missing)

| Item | Now | Missing to submit |
|---|---|---|
| Public repository with MIT license | ✅ | none |
| One-line reproducible command | ✅ `make -C transpile/c all && python3 lin_verify.py all` | install package? optional |
| Standalone external verifier | ✅ `lin_verify.py` (stdlib) | PEP-517 installer only if requested |
| Formal spec/EBNF + VM ISA | ⚠️ `.rulel` + `FORMAL_SPECIFICATION.md` | a frozen version (status `frozen`, not `proposed`) |
| Differential fuzz harness | ✅ `test/fuzz_differential.py`; 10k/11k/20k run | run 100k target in CI, add Zig side |
| Audit-cost microbenchmark | ✅ `test/benchmark_audit_cost.py`; 1k receipts | independent baseline (EVM/OpenSSL) |
| Independent external audit | ❌ | 1 small independent reviewer/company |
| Published benchmark vs baseline | ❌ | baseline measurement against real tool |
| CI evidence on GitHub | ⚠️ local `make verify-grant` passes; GitHub App lacks `workflows` permission | push a workflow or run this in a repo owned by the app owner |

The proof never conflates "is ready for a grant" with "is ready for production".
The remaining technical gaps are the 100k CI fuzz run, a frozen spec, a real
baseline benchmark, and one independent external review.

## 8. Evaluation
A reviewer can verify every claim above by running:

```bash
make -C transpile/c all
python3 lin_verify.py all --iterations 10000
```

and then reading `docs/RATIONALIST_PROOF_STATUS.md` for the exact not-proven
list.
