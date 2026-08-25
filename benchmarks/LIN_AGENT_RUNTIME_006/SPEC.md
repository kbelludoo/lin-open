# LIN-AGENT-RUNTIME-006: Adversarial Blind Debugging & Dynamic Re-Ranking

## 1. Object & Scientific Mandate
Following `LIN-AGENT-RUNTIME-005` (which identified static scoring constants and upfront single-pass beam generation):
> **Can True Dynamic Re-Ranking (where each failure refutes the candidate, updates live invariant weights, and propagates a DAG neighbor boost $Score_{t+1}(C) = Score_t(C) + \Delta$) successfully isolate and resolve deep adversarial bugs ($A \rightarrow B \rightarrow C \rightarrow D$) where shallow decoy candidates cause Greedy and Static Beam agents to fail?**

---

## 2. Dynamic Score Propagation Mechanics

When candidate $N_t$ is refuted at attempt $t$:

1. **Pruning:**
   $$\text{Score}_{t+1}(N_t) = 0.0$$

2. **Topological Gradient Boost to Unrefuted Neighbours:**
   $$\text{Score}_{t+1}(C) = \text{Score}_t(C) + \frac{0.35}{1 + \text{DAG\_Dist}(N_t, C)}$$

3. **Active Invariant Density Ingestion:**
   $$S_{\text{inv}}(C) = \frac{\#(\text{Active } \% \text{ invariants involving } C)}{\text{Total Invariants}}$$

4. **Live Session Memory Update:**
   $$S_{\text{hist}}(C) = \text{SuccessRatio}(C)$$

---

## 3. Evaluated Arms
- **Arm A (RAW):** Zero-state baseline.
- **Arm B (CHAT):** Textual error history buffer.
- **Arm C1 (LIN Greedy):** Static single-node greedy.
- **Arm C2 (LIN Fixed Beam-3):** Static 3-candidate beam.
- **Arm C3 (LIN Dynamic Re-Ranker):** Live score propagation & adaptive search.
