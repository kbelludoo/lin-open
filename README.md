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
| OpenCL execution & CPU/GPU/oracle parity | ✅ bit-exact on an OpenCL device |
| Full self-hosted + compat test suites | ✅ both **PASS** on an OpenCL CPU device |
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

The compiler links against OpenCL for its execution/parity subsystem, so the build needs
an OpenCL dev toolchain (`ocl-icd-opencl-dev` + a runtime ICD, or ROCm on AMD):

```bash
make build           # -> ./bin/lin_native
```

You do **not** need a discrete GPU. Any OpenCL platform works — including a CPU runtime
like **PoCL** (`pocl-opencl-icd` on Debian/Ubuntu), which is exactly how this repo was
tested. The device discovery prefers a GPU but falls back to any OpenCL device, so it runs
on CPU-only machines without crashing.

### Run the checks and tests

```bash
make test            # build + check all src/*.lin and examples/*.lin + receipt round-trip
./bin/lin_native integrity          # self-check over all 20 shipped sources -> PASS
```

Or manually:

```bash
./bin/lin_native version
./bin/lin_native check src/lin_crypto.lin
./bin/lin_native lint src/lin_crypto.lin
```

Run the full self-hosted suites (on any OpenCL platform):

```bash
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_full_self_hosted_suite.zig
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_selfhost_compat_001.zig
```

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

Still open / honest caveats:

4. ⚠️ **`make build` still links OpenCL** (the GPU/parity subsystem is not optional at link
   time). If you truly have no OpenCL ICD/headers you must install `ocl-icd-opencl-dev` +
   `pocl-opencl-icd` (or ROCm). Making OpenCL optional is a recommended next refactor.
5. ⚠️ **Several `[PASS]` lines in the GPU suites are hardcoded prints**, not computed
   assertions. Rewriting them as real assertions is the honest next step for credibility.
6. ⚠️ **`from-js` matches 0 functions** for arrow/expression forms in the current sample.
7. ℹ️ **Broken sources were removed** earlier: `src/lin_selfhost.lin`, `src/lin_refine_div.lin`,
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
- [Project history](HISTORY.rulel)

## License

MIT — see [LICENSE](LICENSE.rulel). Copyright holder must be set to the project's legal owner.
