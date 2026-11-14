# Morpho AdaptiveCurveIRM — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Morpho Blue's
AdaptiveCurve interest-rate model. The LIN copy also lives in a separate
repository: **[kbelludoo/clone-lin-morpho-adaptive](https://github.com/kbelludoo/clone-lin-morpho-adaptive)**.

- **Upstream:** [morpho-org/morpho-blue-irm](https://github.com/morpho-org/morpho-blue-irm) `src/adaptive-curve-irm/AdaptiveCurveIrm.sol` (MIT)
- **Pinned commit:** `58ce91fd04840372443a7080a5b32067b17b3d60`
- **LIN clone (this tree):** [`src/lin_morpho_adaptive_curve.lin`](../../src/lin_morpho_adaptive_curve.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-morpho-adaptive
- **C11 oracle:** `test/oracles/morpho_adaptive_curve_c11.c`
- **C kernel (lin_from_c):** `test/oracles/morpho_adaptive_curve_kernel.c`
- **Harness:** `python3 test/prove_morpho_adaptive_curve_external.py` or `make morpho-adaptive-curve-proof`
- **Event receipt:** `docs/events/EVENT_MORPHO_ADAPTIVE_CURVE_CLONE_LIN.rulel`
- **Transpiler delta:** `src/lin_from_solidity.lin` v3 (`require` fail-closed, `if/else` emit)

## What is claimed

Experimental, int64-scale reproduction of Morpho AdaptiveCurve `_curve`,
utilization error, `wExp` (2nd-order Taylor + `2^q`), and the trapezoidal
average rate over `elapsed`. Solidity `int256` is not claimed. The real
deltas versus the Solidity IRM in this profile are:

1. `rateAtTarget[id]` and `block.timestamp - lastUpdate` are function
   arguments, not hidden storage / env.
2. `(a*b)/d` uses a signed 128-bit product. If the quotient does not fit
   in int64 the clone fail-closes to 0 instead of wrapping.
3. `wExp` fail-closes when `2^q` would overflow int64 instead of clipping
   to Solidity's 256-bit `WEXP_UPPER_VALUE`.
4. `bound` is explicit min/max, not `slt`/`sgt` assembly.

Named goldens (`WAD=1e18`, `INITIAL_RATE_AT_TARGET=1268391679`):

| id | call | value |
|---|---|---|
| TARGET | `_curve(init, 0)` | **1268391679** (1×) |
| HIGH | `_curve(init, WAD)` | **5073566716** (4×) |
| LOW | `_curve(init, -WAD)` | **317097919** (¼×) |
| END-1D | `endRateAtTarget` at 100% util / 86400s | **1454044805** |
| AVG-1D | trapezoid avg rate, same inputs | **5438922544** |

## What is not claimed

- Solidity **int256** / mainnet Morpho Blue **market** parity
- LIN replacing Morpho, Uniswap, or the EVM
- TVL or dollar savings
- Computational soundness of Merkle / zk
- Year-scale adaptation (`speed * elapsed` that does not fit int64 fail-closes)

Machine-written evidence for a given run is in
`morpho_adaptive_curve_evidence.json` (produced by the harness; do not hand-edit).
