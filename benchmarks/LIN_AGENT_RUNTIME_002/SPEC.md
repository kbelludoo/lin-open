# LIN-AGENT-RUNTIME-002: Real Hard-Task Maintenance & Failure Recovery Benchmark

## 1. Object & Scientific Mandate
Following `LIN-AGENT-RUNTIME-001` (which proved architectural integration with 100% initial solve rate), `LIN-AGENT-RUNTIME-002` focuses on:
> **Does the LIN Semantic Agent Runtime (Transitive Substrate + Pure Invariants `%` + Static Effects `*` + Trauma Ledger) improve Recovery Rate ($\frac{\text{recovered}}{\text{initial\_fails}}$) and reduce Context Token Overhead compared to Raw Inference and Textual Chat Buffers on 50 difficult multi-module software maintenance tasks?**

---

## 2. Experimental Arms
- **Group A (RAW Baseline):** Zero-state retry on failure.
- **Group B (Chat History Buffer):** Retries appending raw test runner failure outputs.
- **Group C (LIN Semantic Runtime):** Retries with Structured Trauma Ledger (Refuted Hypothesis, Broken Invariant, Transitive Impact Graph).

---

## 3. Evaluated Metrics
1. **Initial Success Rate ($S_1$):** Tasks solved on Attempt 1.
2. **Recovery Rate ($R$):** Tasks recovered on Attempt 2 or 3 given Attempt 1 failure.
3. **Overall Success Rate ($S_{total}$):** $\frac{\text{Initial} + \text{Recovered}}{N}$.
4. **Token Telemetry:** Prompt tokens, eval tokens, and context growth rate per retry.
5. **Latency Telemetry:** Dedicated breakdown of LLM inference duration vs disk/test cycle duration.
