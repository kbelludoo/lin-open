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
[NOT-PROVEN] NP1  Full UniswapV2Library LinVM execution
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

---

## 2. What is NOT proven (and must not be sold as proven)

| Claim | Status |
|---|---|
| "LIN runs UniswapV2Library and returns 16,624" | **NOT PROVEN** — `lin_c0` rejects `/` with `VM_REJ_INT_DIVISION`; no Zig compiler is available in this environment |
| "LIN saves $1.8T" | **FALSE AS STATED** — the number is cumulative swap volume, not a cost or savings; no benchmark supports a savings figure |
| "LIN is faster than LLVM/C/Rust" | **NOT PROVEN** — no benchmark here |
| "OpenSSL SHA-256 executes in LinVM" | **NOT PROVEN** — the OpenSSL file is only pinned/verified for provenance |
| "Heaps are eliminated in all upstream repos" | **NOT PROVEN** — only the compiler host and the selected LIN modules are observed; upstream C/Solidity is not rewritten by this proof |

The proof harness deliberately encodes the Uniswap limitation as `NP1` and
prints it as `NOT-PROVEN` rather than inventing a pass.

---

## 3. Why this narrow claim set is the rationalist answer

1. It starts from an observable artifact: upstream file digests.
2. It verifies equality with an independent oracle (Python) and an independent
   implementation (the C11 port).
3. It verifies tamper detection.
4. It explicitly publishes what it could not prove.

The next real step to enlarge the claim set is not another dashboard; it is a
Zig-native `zig-out/bin/lin_native` build (or a C11 front-end that accepts the
currently rejected operations), followed by a differential fuzz harness over the
full Uniswap/OpenSSL module and an actual benchmark. Until that exists, this
document is the honest maximum: five reproducible claims, one explicitly
unproven.
