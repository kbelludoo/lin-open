# LIN-AGENT-RUNTIME-003: Blind Real Debugging, Root-Cause Localization & Hypothesis Recovery

## 1. Experimental Standard & The Blind Mandate
Unlike previous prescribed benchmarks where the prompt specified the file and line to change:
> **The agent receives strictly the high-level issue description and the failing test assertion trace. No target file, target symbol, line number, or candidate diff is provided. The agent must independently localize the root cause, traverse the call graph, formulate hypotheses, apply multi-file patches, avoid regressions, and recover via the Trauma Ledger upon failure.**

---

## 2. Experimental Arms (Identical Initial Information)

```text
                                 BLIND ISSUE REPORT
                            + FAILING TEST ASSERTION TRACE
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
      Group A: RAW               Group B: CHAT              Group C: LIN
   (Zero-state Guessing)     (Textual Error Buffer)    (Transitive Substrate +
                                                        Trauma Hypothesis Ledger)
             │                          │                          │
             ▼                          ▼                          ▼
     Attempt 1 Fail             Attempt 1 Fail             Attempt 1 Fail
             │                          │                          │
             ▼                          ▼                          ▼
    Repeat Initial State       Append Raw Terminal       Query Refuted Hypotheses
                                    Trace Log             + Prune Dependency DAG
                                                          + Shift Candidate Focus
             │                          │                          │
             ▼                          ▼                          ▼
      Attempt 2 / 3              Attempt 2 / 3              Attempt 2 / 3
```

---

## 3. Evaluated Metrics
1. **Root-Cause Localization Accuracy ($L_{acc}$):** Ratio of patches touching the exact fault-originating module.
2. **Initial Solve Rate ($S_1$):** Blind first-try resolution.
3. **Hypothesis Recovery Rate ($R_{hyp}$):** $\frac{\text{Recovered on Retry}}{\text{Initial Failures}}$.
4. **Wrong-File Edits & Pollution:** Count of edits made to unaffected files.
5. **Transitive Regressions:** Count of passing tests broken by unintended side effects.
6. **Token Growth Rate:** Context tokens on Attempt 1 vs Attempt 2 vs Attempt 3.
