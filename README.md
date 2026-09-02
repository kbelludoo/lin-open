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
| `bundle-pack` / `bundle-verify` attestation bundle | ✅ real: Git blob OID, MIR + lowering hashes, CPU oracle replay, 8-leaf kernel Merkle trees, ledger root, **Ed25519 seal verified** |
| `cleanroom-verify` | ✅ real: CPU-only cryptographic replay of a signed bundle; fails closed and writes nothing when the bundle does not verify |
| `notary-sign` / `notary-verify` witness quorum | ✅ real Ed25519 M-of-N co-signature verification over a signed tree head (roster file required) |
| N-Version cross-check (`make xver` / `lin crosscheck-c`) | ✅ real: the same 34 vectors through the Zig LinVM and the independent C11 port in `transpile/c/`, comparing canonical Merkle roots — 34/34 agreement, 0 divergences |
| **LIN Gate** (`make gate` / `lin gate-check`) | ✅ real: recomputes the Merkle root of the tracked toolchain (`compiler/**`, `transpile/c/{lin_c,tool,test}/**`) and blocks the PR unless it matches the root attested in `lin_gate_manifest.rulel` |
| Gate attestation signature (`lin gate-keygen` / `gate-attest --key` / `gate-check --roster`) | ✅ real Ed25519: keys generated from `std.crypto.random` (seed written 0600), signature over the manifest body, M-of-N roster quorum, and an explicit "signature NOT VERIFIED" line when no roster is supplied |
| Attestation honesty gate (`make attestation-gate`) | ✅ 35 assertions + 5 unit tests; refuses any command that would publish an uncomputed verdict |
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
- **No 5-language polyglot parity, no federation, no transparency log.** The sub-commands that
  used to claim those (`polyglot-verify`, `federation-verify`, `verify-all`, …) are refused by
  `compiler/lin_attestation_guard.zig` with `error.NotImplemented` until real evidence exists.
  See `SECURITY_AUDIT.md` section 7.

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

### Pre-compiled Stage0 (no Zig needed)

If you just want to **run** `lin` (you are not developing the compiler), you don't need to
install Zig. Pre-compiled `Stage0` binaries are published as GitHub Release assets whenever a
`v*` tag is pushed (and as an artifact on every CI run):

- `lin_native-cpu` — CPU-only build (`zig build -Dgpu=false`). No OpenCL required; GPU
  commands fail gracefully with a clear "no OpenCL platform" message.
- `lin_native-gpu` — OpenCL build (needs an OpenCL runtime, e.g. PoCL/ROCm).

Download the asset for your platform, make it executable, and run it exactly like the built
binary:

```bash
chmod +x lin_native-cpu
./lin_native-cpu version
./lin_native-cpu check src/lin_crypto.lin
./lin_native-cpu receipt create --source "return x * x;" --input 9
```

The asset is built from the exact same `compiler/lin.zig` source that CI verifies, in
`ReleaseFast`, so the reproducible-Merkle-root behavior is identical. SHA-256 of each asset
is printed in the release notes so you can verify the download.

### No Zig at all: Compiler 0 = the LinVM host (C11)

If the machine has **no Zig and no pre-compiled asset** — a clean container, an audit box, an
air-gapped verifier — the chain does not stop: the LinVM host built from C11 sources *is*
Compiler 0 for the `LINVM-1/i64` subset. It needs only `cc`.

```bash
make c0                                            # build transpile/c/bin/lin_c0
./transpile/c/bin/lin_c0 vm file.lin [fn args...]  # drop-in for `lin vm file.lin`
./transpile/c/bin/lin_c0 info file.lin             # per-function eligibility + rejections
./transpile/c/bin/lin_c0 image file.lin -o a.linbc # freeze a LINBC1 image (self-hashed)
./transpile/c/bin/lin_c0 roundtrip file.lin fn     # source == image, same steps
make c0-gate                                       # all of the above, measured
python3 test/verify_gate_manifest.py               # LIN Gate root, without the Zig binary
```

It is faithful rather than approximate: the emitted bytecode, the `VM_REJ_*` codes and the
step counts are transcribed from the frozen Stage0, and the published goldens are reproduced
bit-exactly — `vms_gate` returns `value=1` in **8 511 500 steps** on the C11 host, the same
number the Zig Stage0 measured; `lb_selfhash_fold` reproduces `-178321285347216732`.

**Boundary (read this before trusting it):** this path compiles and runs the integer subset
only. `check` (the full type-checker), `lint`, MIR/GPU lowering, receipts and `integrity`
remain Stage0 — `make test`/`make build-cpu` refuse with a pointer to `make c0-gate` instead of
`zig: command not found`. Scope, evidence and honest limits: `docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel`.

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

Fixed in the attestation-honesty pass (2026-08-31):

11. ✅ **Mock attestation commands can no longer publish verdicts.** `cleanroom-verify` used to
    write `verified_ed25519_seal=true` for *any* file (verified with a bundle containing random
    text); `notary-verify` printed `SIGNATURE VALID` for the placeholder keys `1111…`/`2222…`
    without decoding a signature; `polyglot-verify` reported 6/6 parity by comparing six copies
    of one constant. `cleanroom-verify` and `notary-verify` were rewritten to do the real work
    (bundle replay with Ed25519, and a real witness quorum over a roster file); the remaining
    simulated commands are listed in `compiler/lin_attestation_guard.zig`, refuse to run
    (exit 3, no artifacts) unless `--allow-simulated` is passed, and are covered by
    `make attestation-gate`.

12. ✅ **Real N-Version cross-check (Zig × C).** `lin crosscheck-c` runs the shared
    oracle corpus plus INT64 boundary vectors through this compiler's Pratt parser /
    flat AST / bytecode lowerer / LinVM **and** through the independent C11 port in
    `transpile/c/lin_c`, and compares a canonical 4-leaf SHA-256 Merkle root over
    (source, environment, emitted bytecode, result, steps, final stack depth).
    34/34 vectors agree; a lying second implementation is detected and no receipt is
    written; a missing second implementation fails closed with `error.NotImplemented`.

13. ✅ **LIN Gate — CI integrity checker (the first functional product).** `lin gate-check`
    hashes every tracked file of the toolchain (`compiler/**`, `transpile/c/lin_c|tool|test/**`),
    folds the digests into a real SHA-256 Merkle tree (`LIN_GATE_MANIFEST_v1`) and compares the
    root with the one attested in `lin_gate_manifest.rulel`. Any unattested change — a modified
    compiler file, an injected file, a deletion — reports the exact file and exits 1; a missing
    manifest exits 3; an attested tree exits 0 (GATE OPEN). `.github/workflows/lin_gate.yml` runs
    it on every pull request, together with the honesty suite and the N-Version cross-check, so a
    PR (AI-authored or not) cannot merge with an unattested toolchain. Re-attestation is an
    explicit human act: `make gate-attest`, then commit the new root with the change.
    The attestation can be signed with real Ed25519 (`lin gate-keygen` mints a key from
    `std.crypto.random` and a public roster; `gate-attest --key` signs the manifest body;
    `gate-check --roster` requires an M-of-N quorum). Tampering with a digest, tampering
    with the signature, signing from a non-roster key, missing the quorum or omitting the
    signature all fail closed; with no roster the gate prints `signature NOT VERIFIED`
    instead of implying it checked.

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
