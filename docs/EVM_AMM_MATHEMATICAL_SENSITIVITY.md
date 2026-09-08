# Formal Sensitivity of EVM Floor Division in the Uniswap V2 `getAmountOut` Invariant

**Status:** FROZEN (formal scope note for the Lin-Audit grant, Milestone 1–2)
**Canonical machine:** `u256_settlement_engine.lin` (16 limbs × 16 bits, no hardware division)
**Executable oracle:** `test/pilot_harness/test_honest_parity_and_sensitivity.py` (FASE 2)
**Dataset (unbiased):** `test/pilot_harness/mainnet_unfiltered.json` — 157 contiguous swaps, blocks 25.900.848..25.901.047 (see `docs/DATASETS.md`)

---

## 1. Purpose

This document fixes the **detection bound** of any reconciliation or fraud-detection tool
that recomputes the Uniswap V2 invariant through the canonical EVM arithmetic: integer
(floor) division. It answers the question a grant reviewer or auditor must be able to
ask in closed form:

> *If `reserve_out` is tampered by `δ` wei, when is the tampering **guaranteed** to
> change the recomputed output — and when is it mathematically invisible?*

The bound is a property of the **function**, not of any implementation: no bit-exact
re-implementation of the EVM (Zig, C11, LinVM, Python big-int, or the Solidity oracle)
can detect sub-threshold perturbations that the floor division itself truncates to zero.

## 2. Setup

Uniswap V2 `getAmountOut` (0.3% fee), with EVM floor division:

```text
A     = amount_in                (wei)
R_in  = reserve_in               (wei)
R_out = reserve_out              (wei)

amount_in_with_fee = 997 · A
D   (denominator)  = 1000 · R_in + 997 · A
N   (numerator)    = 997 · A · R_out

Q = amount_out = ⌊ N / D ⌋
```

All quantities are non-negative integers; division is the EVM `DIV` (floor for
non-negatives). The LIN engine and every independent oracle in this repository compute
exactly this function (bit-exact parity is verified on every CI run — see
`make verify-three-repos` and the rationalist proof harness).

## 3. Theorem (detection bound for `reserve_out` tampering)

Let `δ ∈ ℤ` be an integer perturbation of `reserve_out`: `R_out ← R_out + δ`, with
`R_out + δ ≥ 0`. The recomputed output becomes

```text
Q' = ⌊ (N + 997·A·δ) / D ⌋
```

Define the **resolution limit** of the swap:

```text
ΔR_out^min = ⌈ D / (997 · A) ⌉ = ⌈ (1000·R_in + 997·A) / (997·A) ⌉
```

### Claim 1 (guaranteed detection, both directions)

If `|δ| ≥ ΔR_out^min`, then `Q' ≠ Q`. The tampering is **always** detected by an
independent recomputation.

*Proof (δ > 0).* `997·A·δ ≥ D` implies `N'/D = N/D + 997·A·δ/D ≥ N/D + 1`. Since
`Q = ⌊N/D⌋`, we have `N/D ≥ Q`, hence `N'/D ≥ Q + 1` and therefore
`Q' = ⌊N'/D⌋ ≥ Q + 1 > Q`. ∎

*Proof (δ < 0).* Symmetric: `997·A·|δ| ≥ D` implies `N'/D ≤ N/D − 1 + 0`-style bound;
writing `N/D = Q + θ` with `θ ∈ [0,1)`, we get `N'/D ≤ Q + θ < Q + 1` and
`N'/D < Q`, so `Q' ≤ Q − 1 < Q`. ∎

### Claim 2 (tightness: invisibility region)

There exist inputs for which **every** `δ` with `0 < |δ| < ΔR_out^min` is completely
invisible: `Q' = Q`. Concretely, when `N mod D = 0` (i.e. the division is exact,
`θ = 0`), any `|δ|` with `997·A·|δ| < D` leaves the floor unchanged, because

```text
|N'/D − N/D| = 997·A·|δ|/D < 1      and      θ = 0
   ⇒   Q' = Q.
```

Hence `ΔR_out^min` is **tight**: it is simultaneously the smallest universally
guaranteed detection threshold and the largest possible blind spot (plus one).
Detection *below* the threshold happens only when the perturbation crosses the next
integer boundary, i.e. when `δ ≥ (D − (N mod D)) / (997·A)` — which depends on the
remainder and therefore on the specific swap.

### Corollary (per-swap exact bound)

For a *given* swap with remainder `ρ = N mod D`, the exact minimum detectable
perturbation of `reserve_out` is

```text
Δrout^exact = ⌈ (D − ρ) / (997·A) ⌉        (1 ≤ Δrout^exact ≤ ΔR_out^min)
```

which the executable oracle measures independently by binary search per field
(`min_detectable_delta`), and the suite asserts the consistency invariant
`1 ≤ Δrout^exact ≤ ΔR_out^min` on every sampled mainnet swap.

## 4. Empirical calibration (real Mainnet data)

`FASE 2` of `test/pilot_harness/test_honest_parity_and_sensitivity.py` binary-searches
the smallest detectable `δ` per field on real swaps and reports the theoretical limit
side by side. Measured on the unfiltered corpus (157 swaps / 200 contiguous blocks,
**0 `K_VIOLATION`** — consistent with the theorem, since the corpus contains no
perturbation at or above threshold):

* ±1 wei is **invisible** in the large majority of real swaps: `amount_in` 14/25,
  `reserve_in` 15/25, `reserve_out` 23/25 (sample of 25 swaps from the corpus).
* Mainnet-sized reserves put `ΔR_out^min` in the range of 10³–10⁶+ wei, i.e. far above
  wei-scale noise, fee-on-transfer dust, or aggregator slippage rounding.

## 5. Consequences for audit tooling (and for this grant)

1. **No "100% fraud detection" claim is possible or made.** Any tool that recomputes
   `getAmountOut` — including Lin-Audit — has a detection guarantee that is *explicit,
   per-swap, and machine-checkable*: `ΔR_out^min` (upper bound on the blind spot) and
   `Δrout^exact` (the exact per-swap threshold).
2. **Sub-threshold perturbations are out of scope by construction**, not by weakness of
   the implementation: a bit-exact EVM re-implementation computes the same floor and
   cannot see what the canonical arithmetic truncates.
3. **The bound is itself an audit artifact.** Lin-Audit receipts can bind the
   `(A, R_in, R_out, ΔR_out^min)` tuple so that a reviewer knows, for every reconciled
   swap, exactly what deviations would have been guaranteed to trigger a `K_VIOLATION`.

## 6. Reproduce

```bash
# 157-swap unfiltered corpus + FASE 2 sensitivity search (CPU only, no GPU needed)
make -C transpile/c bin/lin_c0 bin/lin_bc1_run
python3 test/pilot_harness/test_honest_parity_and_sensitivity.py \
    --json test/pilot_harness/mainnet_unfiltered.json --sens-sample 40

# regenerate the unfiltered corpus from an accessible Mainnet JSON-RPC
python3 tools/ingest_mainnet_unfiltered.py --blocks 200 \
    --out test/pilot_harness/mainnet_unfiltered.json
```

The suite prints, per sampled swap, the measured `Δain±/Δrin+/Δrout−` next to the
theoretical `den/(997·ain)` limit and a `Consistência com o teorema: OK` line.

## 7. What this document does NOT claim

* Not a proof of equivalence between `u256_settlement_engine.lin` and the deployed
  `UniswapV2Library.sol` (that equivalence is established by bit-exact vector parity
  against the big-int reference on the corpus, not by formal `.sol` equivalence).
* Not a security proof of any protocol, pool, or token (fee-on-transfer and
  re-entrancy behavior are outside the invariant being measured).
* Not a bound on *aggregator* slippage or on *economic* deviation — it bounds what is
  **arithmetically distinguishable** after EVM floor division.
