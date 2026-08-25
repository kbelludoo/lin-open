# LIN-SIGIL-002: Real Compiler Parser Evolution Benchmark

## 1. Object & Research Goal
Following `LIN-SIGIL-001`, this benchmark replaces the simulated lexer with the **Real LIN Compiler Parser Pipeline** (`src/semantic_parser.lin` & `src/lin_core_compiler.lin`), testing the real parser against the Candidate V2 Extension with `%` (Contracts) and `*` (Effects) across the entire corpus of 375 `.lin` files.

---

## 2. Validation Gates
- **Gate 1 (Zero-Regression AST Equivalence):** $AST_{V1} \equiv AST_{V2}$ for 100% of all existing 375 `.lin` files (headers, functions, signatures, bodies).
- **Gate 2 (Zero-Regex Semantic Extraction):** Extraction of contracts (`%`) and effects (`*`) directly into typed IR properties without running multi-line RegExp scans.
- **Gate 3 (Compilation & Parse Throughput):** Parse and canonicalize time ($\mu$s/file).
