# LIN — Deterministic Scalar Systems Language & Compute Receipts

> CLI reports version `2.0.0` (the "lin-rewrite v2" lineage: AIL → LIA → LIN).

**LIN** is a deterministic scalar/numeric procedural language with a small bytecode VM
(`LinVM`), a heap-free flat AST arena, and cryptographic **compute receipts** that bind
(source hash, inputs, outputs, VM steps, stack depth) into a single SHA-256 Merkle root.

It is designed for small, verifiable numeric kernels: math, hashing, bit operations, and
execution receipts that prove *"this code, given this input, produced this output"*.

---

## 1. What LIN actually does (verified in this repo)

These were verified by building and running the compiled binary:

| Capability | Status |
|---|---|
| Parse + type-check + lint `.lin` sources | ✅ 20/20 files pass `check` |
| `from-c` transpile of scalar C functions → `.lin` | ✅ works |
| LinVM execution of scalar functions (`receipt create`) | ✅ works |
| Compute receipt **create → verify** round-trip (RULEL + JSON) | ✅ works (deterministic Merkle root) |
| `integrity` / `hypo --all` self-check | ✅ **PASS** (20/20 sources confirmed) |
| OpenCL execution & CPU/GPU/oracle parity | ✅ bit-exact on an OpenCL device (conformance, not proof) |
| `gpu-verify` | ✅ PASS (21/21 bit-exact) on any OpenCL device |
| Full self-hosted + compat test suites | ✅ both **PASS**; all 17 compat subgates are computed assertions |
| `from-js` transpile | ⚠️ narrow subset only (arrow/expr fns match 0) |

`receipt create --source "return x * x;" --input 9` produces a deterministic root
`sha256:b96fecee…` that re-verifies identically on every run — a reproducible CPU receipt.

The two self-hosted suites (`test_lin_full_self_hosted_suite.zig` and
`test_lin_selfhost_compat_001.zig`) run to **`status=PASS`** and print
`R_cpu == R_gpu == R_oracle` bit-exact, a stable Merkle root
`sha256:62b7d202…`, and `17/17` compat subgates with `1000/1000` fuzz cases, 0 mismatches.

### What LIN is NOT (honest scope)

- **Not a universal transpiler** to `js|ts|py|go|rust`. It transpiles a small scalar C
  subset to LIN; JS support is experimental and limited. Do not market it as a 5-language compiler.
- **No** strings, floats (`f32`/`f64`), dynamic structs, heap `malloc`, OS file I/O, or OOP.
- **Target domain:** deterministic integer kernels, hashing/bit-manipulation, small math, receipts.

---

## 2. Build & run

There is a `build.zig` (Zig 0.13.0) with a **compile-time `gpu` option**, plus convenience
Makefile targets.

### GPU mode (default) — needs an OpenCL toolchain

The compiler links OpenCL for its execution/parity subsystem, so this mode needs an OpenCL
dev toolchain (`ocl-icd-opencl-dev` + a runtime ICD, or ROCm on AMD):

```bash
zig build -Doptimize=ReleaseFast     # -> zig-out/bin/lin_native
# or
make build
```

You do **not** need a discrete GPU. Any OpenCL platform works — including a CPU runtime like
**PoCL** (`pocl-opencl-icd` on Debian/Ubuntu), which is exactly how this repo was tested.
Device discovery prefers a GPU but falls back to any OpenCL device, so it runs on CPU-only
machines without crashing.

### CPU-only mode — no OpenCL toolchain required

```bash
zig build -Dgpu=false -Doptimize=ReleaseFast
# or
make build-cpu
```

This compiles the **same source** against a bundled OpenCL stub (`stubs/CL/`), so it builds
and runs on any machine with just Zig 0.13 — no OpenCL headers, ICD, or GPU. All CPU
functionality works; GPU/attestation commands fail gracefully with a clear "no OpenCL
platform" message instead of crashing.

### Run the checks and tests

```bash
make test         # GPU build + check all src/*.lin + receipt round-trip
make test-cpu     # CPU-only build + same checks (no OpenCL needed)
$BIN integrity    # self-check over all 20 shipped sources -> PASS
```

Or manually:

```bash
$BIN version
$BIN check src/lin_crypto.lin
$BIN lint src/lin_crypto.lin
```

Run the full self-hosted suites (GPU mode, any OpenCL platform):

```bash
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_full_self_hosted_suite.zig
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_selfhost_compat_001.zig
```

### Reproducibility & CI

`.github/workflows/ci.yml` pins **Zig 0.13.0**, installs OpenCL + PoCL, builds both modes,
runs `make test`, both self-hosted suites, and `integrity`, then **captures and publishes the
Merkle roots** in the run summary and as an artifact. Use those published roots as the
canonical reference to verify receipts on your own machine.

---

## 3. Compute receipts (create & verify)

```bash
# Create (prints a RULEL receipt to stdout)
./bin/lin_native receipt create --source "return x * x;" --input 9

# Save it and cryptographically verify
./bin/lin_native receipt create --source "return x * x;" --input 9 > receipt.rulel
./bin/lin_native receipt verify --receipt receipt.rulel
# -> PASS: ... Merkle root valid: sha256:b96fecee...

# JSON form also round-trips
./bin/lin_native receipt create --source "return x * x;" --input 9 --export json > receipt.json
./bin/lin_native receipt verify --receipt receipt.json
```

### Independent verification — no LIN binary needed (zero-trust)

The receipt is an **open format**: any third-party tool can validate it with only a
SHA-256 implementation (NIST FIPS 180-4). The 64-byte leaf is built as:

| Bytes  | Field       | Encoding                    |
|--------|-------------|-----------------------------|
| 0..32  | source hash | SHA-256 of source (raw)     |
| 32..40 | output      | i64, little-endian          |
| 40..48 | steps       | u64, little-endian          |
| 48..56 | sp_at_ret   | u64, little-endian          |
| 56..64 | input       | i64, little-endian          |

`merkle_root = SHA-256(leaf)`

Shipped independent verifiers (Python stdlib / Bash+OpenSSL / Node / WebCrypto —
`benchmarks/`), none of them touch the LIN compiler:

```bash
python3 benchmarks/verify_receipt.py receipt.json              # Python 3 stdlib
bash benchmarks/verify_receipt.sh receipt.rulel                # Bash + OpenSSL
node benchmarks/verify_receipt.js receipt.json                 # Node.js crypto
python3 benchmarks/verify_receipt.py receipt.json --source "return x * x;"  # also binds artifact to source
# benchmarks/verify_receipt.html → static page, browser WebCrypto, works offline
```

`benchmarks/fixtures/receipt_sqr9.json` / `.rulel` are **real receipts emitted by
this compiler** (`return x * x;`, input 9 → output 81, merkle
`sha256:b96fecee…`). `make verify-receipt` runs all three verifiers plus a tamper
check (a receipt with `output` changed to 82 must FAIL) — and CI runs it too.

Honest scope: this verifies the receipt fields are **self-consistent** and that the
artifact hash binds to the source. It does **not** re-execute the code — a receipt
with arbitrary fields and a recomputed Merkle root still verifies. For execution
proof, re-run the source with an independent runner (the `--source` flag is the
bridge) or use TEE/ZK (see `SECURITY_AUDIT.md`).

---

## 4. Known issues & what needs fixing (honest status)

Fixed in this revision (2026-08-31):

1. ✅ **`integrity` / `hypo --all` now passes.** It previously iterated 36 deleted
   `test/corpus/*.lin` files (`refuted=36, FAIL`). It now self-checks the 20 `.lin` sources
   that actually ship in this repo → `confirmed=20, refuted=0, status=PASS`. The same fix was
   applied to `verify-cert` and `cert` (they no longer reference the deleted corpus).
2. ✅ **No longer crashes without a GPU.** The test suites queried only
   `CL_DEVICE_TYPE_GPU` and indexed `platforms[0]`/`devices[0]` unconditionally. Device
   discovery now falls back to any OpenCL device (e.g. a PoCL CPU device) and skips
   gracefully when none exist.
3. ✅ **Runs on any OpenCL platform.** The hard-coded `-cl-std=CL2.0` kernel build flag was
   replaced with the device default, so kernels build on OpenCL 1.2 CPU runtimes like PoCL.

Also fixed in this revision (2026-08-31, "all corrections" pass):

4. ✅ **Hardcoded `[PASS]` prints rewritten as real computed assertions.** All 17 subgates of
   `test_lin_selfhost_compat_001.zig` now perform actual checks (parse accept/reject, integer
   wrap-around, deterministic MIR hash, real LinVM execution with `sp_at_ret==1`, CPU/GPU/oracle
   parity, JIT/AOT determinism, error rejection, real source parsing, dual-run determinism,
   reduction performance, fuzz, corpus parse, self-host build, real kernel emission).
5. ✅ **Self-referential certificate fixed.** `@LIN:SEMANTIC_CERTIFICATE` no longer hashes the
   running binary (`/proc/self/exe`). `compiler_sha256` is now the SHA-256 of the compiler
   **source** (`compiler/lin.zig`), which is reproducible and independently verifiable.
6. ✅ **`gpu-verify` repaired.** It previously failed opening the deleted
   `test/corpus/gpu_parallel_map_kernels.lin`. It now defaults to `examples/map_kernels.lin`
   (real scalar unary kernels) and runs to `PASS` (21/21 bit-exact) on any OpenCL device,
   with device discovery falling back to CPU.

Remaining honest caveats:

7. ⚠️ **GPU parity is a conformance test, not a cryptographic proof.** The `R_cpu==R_gpu==R_oracle`
   comparison trusts the OpenCL runtime to report execution faithfully; a malicious/compromised
   runtime could fabricate results (see `SECURITY_AUDIT.md` for a working red-team PoC). This is
   determinism/consistency testing, not adversarial proof. For true proof-of-execution, use
   TEE/attestation or ZK instead of OpenCL.
8. ⚠️ **`from-js` matches 0 functions** for arrow/expression forms in the current sample.
9. ℹ️ **OpenCL is optional at compile time** (`zig build -Dgpu=false`), but the GPU code is
   compiled-but-stubbed in CPU-only mode (reports "no OpenCL platform") rather than being fully
   excluded from the binary.
10. ℹ️ **Broken sources were removed** earlier: `src/lin_selfhost.lin`, `src/lin_refine_div.lin`,
    `src/lin_pow_simd.lin` failed the project's own `check` and were not referenced by tests.
    Restore via git history if needed.

Additional corrections in the 2026-08-31 review pass (see `docs/REVIEW_SUGESTOES_E_CORRECOES.md`):

11. ✅ **`cert build` → `cert verify` round-trip fixed.** `cert verify` was still hashing the
    running binary (`/proc/self/exe`) and the deleted `test/corpus/*.lin` set, so it failed
    against every freshly built certificate. It now anchors on `compiler/lin.zig` and the 20
    shipped sources, exactly like `cert build`/`integrity`.
12. ✅ **`receipt verify` without `--receipt` now fails** (it previously printed an
    unconditional `PASS` — a verifier that cannot fail).
13. ✅ **`receipt create --input` rejects invalid values** instead of silently falling back to 7.
14. ✅ **Malformed JSON receipts are rejected gracefully** (missing/wrong-typed fields no
    longer crash with a Zig panic).
15. ✅ **`INT64_MIN / -1` and `INT64_MIN % -1` no longer trap** in the LinVM, the `_lia_mod`
    helper, the Zig runtime prelude, and the C-expression evaluator (wrapping convention:
    `div → INT64_MIN`, `mod → 0`).
16. ✅ **`opcodes=28` hardcoded replaced** with the computed count (33) in `lin vm`.
17. ✅ **`lin test` no longer probes `/home/k/.local/bin/zig`** — uses `$LIN_ZIG` or `zig`
    from PATH.
18. ✅ **`integrity` computes `.equivalent`/`.proof`** from the actual confirmed/refuted
    counts instead of printing `equivalent=true` / `…100_PASS` unconditionally.
19. ✅ **`cert verify` actually parses certificate fields now.** The `certFieldValue`
    helper was returning an empty string for every claimed field (it did not skip the
    opening quote), so `cert build` → `cert verify` still failed after the anchor fix.
    Round-trip now passes: `CERTIFICATE_VALID`, all `*_match=true` (verified by running).
20. ✅ **`lin test` repaired.** It referenced `src/lin.zig` (removed in the cleanup) and
    wrote `src/lin_test_run.zig` into the working tree. It now uses the embedded
    `ZIG_RUNTIME_PRELUDE` and writes to `.zig-cache/` — runs to `ok N`, exit 0.
21. ✅ **`lin rebuild` fails with a clear message** (its bootstrap modules were removed
    in the cleanup) instead of a raw `FileNotFound` trace.

Remaining review caveats (not fixed, see report):

22. ⚠️ **`receipt verify` is self-consistent but does not re-execute** the source; a
    consistent tamper (input+output+steps+merkle) still verifies. A `--execute` mode is
    recommended before claiming "proved execution" in marketing.
23. ⚠️ **`storage/dynamic_rules.rulel` in the CWD silently rewrites sources** before
    `check`/`compile`/`test` (`apply_dynamic_rules_if_present`). Recommend removing the hook
    or gating it behind an explicit flag.
24. ⚠️ **Duplicate `verify-cert` handlers**: the hash-based verifier is only reachable via
    the `verify-certificate` alias; the `verify-cert` name hits an older 32-basis-case
    verifier. Merge into one command.
25. ⚠️ **Corpus is 20 sources while the repo ships 21 `.lin` files**
    (`examples/map_kernels.lin` is not in the corpus list). Either add it or document the
    exclusion.
26. ⚠️ **`test/corpus/gpu_parallel_map_kernels.lin` is an orphan**: the README says the
    corpus was removed, but this file remains and fails `check` (`LIN_TYPE_ERROR`),
    breaking `lin test test/`. Remove it or fix its types.
27. ⚠️ **`lin rebuild` is unavailable**: its bootstrap modules (`src/lin_zig_bootstrap.lin`,
    `src/lin_zig_emit.lin`, `src/lin_zig_match.lin`, `src/lin_js_expr.lin`,
    `src/lin_js_driver.lin`) were removed and the repo is shallow — no history to restore.
28. ⚠️ **`lin test` harness**: only calls parameterless `test_*()` functions and requires
    them to return exactly `1`.

---

## 5. Repository layout

```
compiler/          Zig bootstrap compiler (LinVM, MIR, GPU lowering, receipts)
src/               Native LIN specification modules & transpilers (.lin)
examples/          Runnable .lin examples
docs/              Prompt guide & verification spec
*.zig at root      Self-hosted test suites (run on any OpenCL platform)
```

## 6. Documentation

- [AI Safe Prompting Guide & Spec](docs/LIN_PROMPT_GUIDE.md)
- [Verifiable Spec v1.0](docs/LIN_VERIFIABLE_SPEC_v1.0.rulel)
- [Security audit & red-team PoC](SECURITY_AUDIT.md) — why the GPU "proof" is conformance, not proof
- [Project history](HISTORY.rulel)

## License

MIT — see [LICENSE](LICENSE.rulel). Copyright holder must be set to the project's legal owner.
