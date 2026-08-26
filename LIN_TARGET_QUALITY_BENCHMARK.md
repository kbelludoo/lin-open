# LIN Target Quality Benchmark

**Host:** win32 **Date:** 2026-08-15 **Suite:** `tests/target_quality.lin`
**Rule:** all 7 real nucleus langs must FULL (compile AND run) before rank. Stubs excluded.
**Host policy:** C is `memory=unsafe` (compile+run gate / portability only). Rust is `in_memory_host` / `systems_pick`. CLI default stays `ts`.

Warmup=2, repeats=9, metric=median wall ms of running the already-compiled artifact.

| lang | compile | run | ms | bytes | rank | memory |
|------|---------|-----|----|-------|------|--------|
| c | PASS | PASS | 32.46 | 1798 | 1 | unsafe |
| rust | PASS | PASS | 35.20 | 2270 | 2 | ownership |
| go | PASS | PASS | 35.46 | 3267 | 3 | gc |
| py | PASS | PASS | 105.27 | 1736 | 4 | agent |
| ts | PASS | PASS | 113.98 | 487 | 5 | agent |
| js | PASS | PASS | 115.27 | 447 | 6 | agent |
| java | PASS | PASS | 197.86 | 2579 | 7 | gc |

**FASTEST (wall-clock):** `c` — 32.46ms, 1798 emitted bytes. Honest process-startup timing; not an in-process memory-safe host.
**BEST_IN_MEMORY / SYSTEMS_PICK / runtime_winner:** `rust` — ownership; C cannot win this rank.
CLI default stays `ts` (clone / behavior_eq). `futurePickBestLang` is MEASURED only when given FULL rows; without a bench it stays NOT_RUN.

**LIN→Rust (emit existing .lin, not a hand-written rust compiler):**
- `tests/target_quality.lin`: rustc+run OK. Same results as TS (`3628800`, `false`, `5050`, `64`, `10`). Emitted bytes rust 2270 vs ts 487. Wall ms rust 35.20 vs ts 113.98.
- `src/emit_host_pick.lin`: rustc+run OK. Prints `in_memory_host=rust`, CLI default `ts`, `c_memory=unsafe`, kinds `unsafe`/`ownership`.
- Not rustc-valid yet (rust emitter MVP): `src/clone_lin_full_repo_gate.lin`, `src/emit_entry_main.lin`, and other `src/*.lin` that use arrays/objects/regex/index-assign/JS closures/`node:crypto`. Future = write more LIN, then emit rust — never a parallel hand-written rust compiler.

