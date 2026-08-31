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
| Attestation honesty gate (`make attestation-gate`) | ✅ 19 assertions + 5 unit tests; refuses any command that would publish an uncomputed verdict |
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
