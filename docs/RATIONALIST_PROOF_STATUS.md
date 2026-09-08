# Rationalist External Proof Status — LIN

> Status: truthful audit, not marketing. Every line below is either reproducible
> from this repository (no Zig required) or explicitly marked as NOT PROVEN.

The previous conversation produced several strong claims ("$1.8T saved", "Uniswap
executed in LinVM with 16,624 in 21 steps", "all claims proven"). In this checkout
the **only** thing those claims had as evidence was a React/TypeScript dashboard
that was not present in this repository, plus a C11 runtime that **rejects** the
Uniswap integer division (`VM_REJ_INT_DIVISION`) on the no-Zig host. Therefore
this document replaces them with a smaller, verifiable claim set.

---

## 1. What is actually proven here

Run the proof yourself (Python 3 + `cc`, no Zig):

```bash
make -C transpile/c all
python3 test/prove_all_claims_external.py --iterations 10000
# or, when network is available:
python3 test/prove_all_claims_external.py --iterations 10000 --fetch
```

Latest rationalist output:

```text
[PASS] C1  Upstream source provenance
          5 pinned upstream files matched published SHA-256
[PASS] C2  QOI index-hash parity  (qoi.h -> LIN -> C0)
          qoi_color_hash: N random vectors exact vs qoi.h spec
[PASS] C3  TinyExpr factorial parity (0..20, fail-closed edges)
          tinyexpr_fac(0..20) equals Python math.factorial
[PASS] C4  Compute receipt root independently recomputed
          x*x receipt root independently recomputed by Python
[PASS] C5  Compiler-0 no-Zig self-host gates
          verify_c0.sh + verify_c0_selfhost.sh pass with no Zig
[PASS] C6  UniswapV2Library scalar math parity (default vm)
          get_amount_out/quote/get_amount_in match Python oracle
[PASS] C7  SipHash/xxHash round parity (profile-full)
          SipHash-2-4 and xxHash64 round match Python oracle
[NOT-PROVEN] NP1  Full protocol/security/performance proof
```

### C1 — Real GitHub provenance, fetched from the GitHub Contents API

Files are pinned under `test/fixtures/external_proof/` and re-fetched with
`--fetch`. Exact digests verified on 2026-09-02.

| Upstream | Path | SHA-256 |
|---|---|---|
| `Uniswap/v2-periphery` | `contracts/libraries/UniswapV2Library.sol` | `4f83e933…d0fd9f2` |
| `Uniswap/v3-core` | `contracts/libraries/FullMath.sol` | `959c52e1…44880e` |
| `openssl/openssl` | `crypto/sha/sha256.c` | `3a967cf8…49f21` |
| `phoboslab/qoi` | `qoi.h` | `7de6fca1…09375a` |
| `codeplea/tinyexpr` | `tinyexpr.c` | `0d7121f2…12f004` |

### C2 — QOI hash parity (a real repo algorithm)

`phoboslab/qoi` specifies:

```c
index_position = (r * 3 + g * 5 + b * 7 + a * 11) % 64;
```

The LIN module `src/lin_siphash_xxhash_qoi.lin::qoi_color_hash` implements the
same formula with `& 63`. The host `lin_c0` (C11, no Zig) is executed against a
seeded random corpus and each result is compared with a pure Python oracle.
Every tested vector matched.

### C3 — TinyExpr factorial parity (a real repo algorithm)

`codeplea/tinyexpr` defines `fac()` for exact integer factorials. The LIN module
`src/lin_tinyexpr_stage1.lin::tinyexpr_fac` is bounded to 20 unrolled steps and
returns the sentinel `-9003` for `n > 20`, `-9002` for `n < 0`. The harness
compares `n = 0..20` to Python `math.factorial` and the sentinel edges to the
declared contract.

> Correction during this audit: the module originally unrolled only to 12 and
> silently returned `12!` for `13..20`. That was a real logic bug, not a feature.
> It is fixed in this branch, and the proof now covers `0..20`.

### C4 — Independent cryptographic receipt

`transpile/c/tool/lin_c_receipt.c` is an independent C11 implementation that
emits a canonical Merkle root. `python3 benchmarks/verify_receipt.py`
recomputes that root from public fields with `hashlib` — no LIN runtime involved.
A committed receipt verifies, and an `output + 1` tamper is rejected.

### C5 — Compiler-0 no-Zig gates

```bash
bash test/verify_c0.sh transpile/c/bin/lin_c0
bash test/verify_c0_selfhost.sh
```

Both pass, using only `cc` + Python. This is a real no-simulation result from
this repository; it is not borrowed from the absent React dashboard.

**Fronteira Explícita do Trusted Computing Base (TCB):**
* **TCB Estrito (Runtime de Execução Core):** **809 LOC**
  `lin_vm.c` (463) + `lin_linbc1.c` (202) + `lin_sha256.c` (114) + `lin_common.c` (30) = **809 LOC**.
* **Front-end & Host C11 (`transpile/c/lin_c/*.c`):** **1.764 LOC**.
* **Toolchain Completa C0 (`transpile/c/tool/*.c` + headers):** **6.6k LOC** (4.382 LOC em `tool/*.c` + 482 em headers).
* *Regra de integridade:* Nunca misturar o TCB estrito do runtime de execução (809 LOC) com a toolchain completa do compilador (6.6k LOC).

### C6 — UniswapV2Library scalar math parity (default vm, 2026-09-08)

Default `lin_c0 vm` now accepts `/` (c0_build allow_div=1; verified
`info total=3 eligible=3 rejected=0`). Shifts (`<<,>>`) stay fail-closed
(`VM_REJ_SHIFT`, QOI module 1/3 eligible) and still need `vmfull`.
The harness executes the three pure functions of the pinned
`UniswapV2Library.sol` on default `vm` (+`vmfull` parity on canonicals)
vs an independent Python oracle. Canonical `(10000, 50000, 100000)` → `16624`.

```bash
transpile/c/bin/lin_c0 vm src/lin_uniswap_v2_library.lin get_amount_out 10000 50000 100000
# .result{ fn="get_amount_out" value=16624 steps=36 }
transpile/c/bin/lin_c0 vmfull src/lin_uniswap_v2_library.lin get_amount_out 10000 50000 100000
# .result{ fn="get_amount_out" value=16624 steps=36 }
```

### C7 — SipHash/xxHash round parity (profile-full)

`src/lin_siphash_xxhash_qoi.lin::siphash_round` and `::xxhash64_round` use
`<<` and `>>`, which the default C0 parser rejected. With `vmfull` they execute
and match an independent Python 64-bit rotate/wrap oracle over 2,000 vectors.

```bash
transpile/c/bin/lin_c0 vmfull src/lin_siphash_xxhash_qoi.lin xxhash64_round 1 2
# .result{ fn="xxhash64_round" value=4536812348109739777 steps=33 }
```

The `vmfull` mode is **experimental and intentionally separate from the default
fail-closed profile**: it does not change what `lin_c0 info`/`vm` report.

---

## 2. What is NOT proven (and must not be sold as proven)

| Claim | Status |
|---|---|
| "LIN saves $1.8T" | **FALSE AS STATED** — the number is cumulative swap volume, not a cost or savings; no benchmark supports a savings figure |
| "LIN is faster than LLVM/C/Rust" | **NOT PROVEN** — no benchmark here |
| "OpenSSL SHA-256 executes in LinVM" | **NOT PROVEN** — the OpenSSL file is only pinned/verified for provenance |
| "Full Uniswap protocol is now protected/replaced" | **NOT PROVEN** — only the three pure math functions are executed; routing addresses, storage, EVM, reentrancy, etc. are outside this test |
| "Heaps are eliminated in all upstream repos" | **NOT PROVEN** — only the compiler host and the selected LIN modules are observed; upstream C/Solidity is not rewritten by this proof |

The proof harness encodes these as `NP1` and prints the `NOT-PROVEN` line rather
than inventing a pass.

---

## 3. Why this narrow claim set is the rationalist answer

1. It starts from an observable artifact: upstream file digests.
2. It verifies equality with an independent oracle (Python) and an independent
   implementation (the C11 port).
3. It verifies tamper detection.
4. It explicitly publishes what it could not prove.

The next real step to enlarge the claim set is no longer "make the C11 host
accept division/shifts" — that now exists as the experimental `vmfull` profile.
Status of the remaining gaps:

1. ✅ a 100k-vector differential corpus over shifts/division — **done**: 400,003
   vectors (100k QOI + 100,003 Uniswap + 200k SipHash/xxHash), 0 divergences.
2. ✅ an actual audit-cost benchmark — **done**: `benchmarks/audit_cost_benchmark.py`
   measures verify ≈5.3 µs vs re-execute ≈26.4 ms (≈4,986×) on the u256 block.
3. ✅ a frozen formal spec — **prepared**: `docs/SPEC_FREEZE_1_0.rulel` pins the
   digests (status `FROZEN_CANDIDATE`, awaiting maintainer blessing).
4. ❌ one independent external review — **open** (not automatable from here).

Until those exist, this document is the honest maximum: **seven reproducible
claims**, one explicit `NOT-PROVEN` scope line.

## 4. Standalone CLI

```bash
# verify a receipt independently (stdlib, no Zig)
python3 lin_verify.py receipt benchmarks/fixtures/receipt_sqr9.json

# upstream provenance
python3 lin_verify.py provenance --fetch

# run a LIN module through the C11 Compiler-0 host
python3 lin_verify.py module src/lin_siphash_xxhash_qoi.lin qoi_color_hash 50 60 70 80

# run through the experimental profile-full host
python3 lin_verify.py module-full src/lin_uniswap_v2_library.lin get_amount_out 10000 50000 100000

# no-Zig self-host gates
python3 lin_verify.py selfhost

# full proof
python3 lin_verify.py all --iterations 10000
```

For grant readiness, the remaining technical gaps are listed in
`GRANT_PROPOSAL.md` §7: a frozen formal spec, 100k differential fuzz vectors
over shifts/division, one independent external reviewer, and an honest audit-cost
benchmark.
