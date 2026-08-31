# LIN — Deterministic Verified Systems Language & Compute Receipts

@RULEL:LIN_SPEC:1.4.0
~R{.v=version .s=status .c=certificate .r=receipts}

**LIN** is a deterministic numeric and procedural systems language engineered for formal verification, in-memory execution, and cryptographic execution receipts on heterogeneous hardware (AMD Zen3 CPU + AMD Radeon gfx1030 GPU).

---

## 1. What LIN Is (Actual Executable Capabilities)

- **Deterministic C Subet Pratt Parser**: 29/29 arithmetic & logical expression test vectors passing bit-exact.
- **Flat AST Arena**: 256 nodes fixed arena, 0 heap allocations, post-order traversal.
- **LinVM**: 28 opcodes (`.add`, `.sub`, `.mul`, `.div`, `.mod`, `.cmp_*`, `.jump`, `.call`, `.ret`) with stack discipline verified (`sp_at_ret == 1`).
- **Procedural Statements & Control Flow**: Variable assignments, scoped blocks, `if/else`, `while`, and desugared `for` loops with symbolic fixup backpatching (13/13 test vectors).
- **Functions & Stack Frames**: Parameter binding, nested calls, recursion (`fact(6) == 720`), and frame unwinding (4/4 test vectors).
- **AI Agent Structured Feedback (`--ai-feedback`)**: High-fidelity JSON diagnostic protocol with stable taxonomy (`E_SYNTAX_*`, `E_SEMANTIC_*`, `E_EXEC_*`, `E_RESOURCE_*`).
- **LIN Compute Receipts (`lin receipt create / verify`)**: In-memory execution receipts binding code hash, inputs, outputs, VM steps, stack depth, and hierarchical Merkle roots.

---

## 2. What LIN Is NOT (Explicit Honest Scope)

- **Not a Universal Transpiler**: Does not translate to arbitrary Python, JavaScript, Rust, or Go applications.
- **No Complex Types**: No floating-point (`f32`/`f64`), strings, dynamic structs, heap `malloc`, or OS file I/O.
- **Targeted Domain**: Small, deterministic numeric kernels, mathematical algorithms, hashing/cryptography, and verification-native AI code generation.

---

## 3. Quickstart & Commands

### Building Native Executable
```bash
make build
# Binary created at ./bin/lin_native
```

### Creating & Verifying Compute Receipts
```bash
# Generate native RULEL execution receipt for sqr(9)
./bin/lin_native receipt create --source "return x * x;" --input 9

# Export execution receipt as JSON
./bin/lin_native receipt create --source "return x * x;" --input 9 --export json

# Cryptographically verify a receipt file (.rulel or .json)
./bin/lin_native receipt verify --receipt receipt.rulel
```

### Running Comprehensive Self-Hosted Test Suite
```bash
zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL test_lin_full_self_hosted_suite.zig
```

---

## 4. Formal Provenance Certificate (1.4.0)

```rulel
@LIN:FULL_SELF_HOSTED_SUITE_CERTIFICATE:1.4.0
.status="PASS_FULL_SELF_HOSTED_LIN"
.target_device="gfx1030"
.host_device="CPU_ZEN3"
.compiler_0_runtime="ZIG_BOOTSTRAP_STAGE_0_MINIMAL"
.c_expr_vectors=29
.c_stmt_vectors=13
.c_fn_call_vectors=4
.control_flow_active=true
.functions_active=true
.vm_call_args_local_init=true
.ast_vm_parity_vectors=29
.flat_ast_arena_active=true
.self_hosted_lin_modules_active=10
.provenance_merkle_root="sha256:62b7d202d4f273ab967cc46e705f5b1a035b6540abfa9c97a2ac69480a277482"
```

---

## 5. Documentation

- [AI Safe Prompting Guide & Spec](docs/LIN_PROMPT_GUIDE.md): Syntax rules, recursion contracts, and error taxonomy for AI agents.
