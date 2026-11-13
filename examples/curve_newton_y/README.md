# Curve tricrypto `_newton_y` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
tricrypto `CurveCryptoMathOptimized3._newton_y` (Newton fallback used when the
closed-form `get_y` cubic is unsafe). The LIN kernel is published in a
**separate clone-lin repository**; lin-open keeps the kernel copy needed to
re-run Compiler 0 plus the auditable evidence.

- **Upstream (hash-pinned, not vendored):** [curvefi/tricrypto-ng](https://github.com/curvefi/tricrypto-ng) `contracts/main/CurveCryptoMathOptimized3.vy` commit `ecaa8161c240f21dd7c3712eefc5637e1dac742b`. Curve.Fi publishes that tree as informational-only (no reproduction license). Hashes only: sha256 `d0d48e5c3fa00e36f841250cbce8665292ba3224bb050c948dc3b12a50f01d6c`, git blob `695c794cb8035e4b2848ad0354d0993dcfb9c7cb`.
- **Clone-LIN repo:** [kbelludoo/clone-lin-curve-newton-y](https://github.com/kbelludoo/clone-lin-curve-newton-y)
- **LIN kernel (this tree, identical bytes):** [`src/lin_curve_newton_y.lin`](../../src/lin_curve_newton_y.lin)
- **C11 oracle:** `test/oracles/curve_newton_y_c11.c`
- **Harness:** `python3 test/prove_curve_newton_y_external.py` or `make curve-newton-y-proof`
- **Event receipt:** `docs/events/EVENT_CURVE_TRICRYPTO_NEWTON_Y_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE = 1e9`) reproduction of Curve crypto Newton's
method for `y` given the other two coins and invariant `D`. Real deltas versus
the Vyper math contract:

1. Storage / `self` fields (`ANN`, `gamma`, `D`, `xp`) are function arguments.
2. `uint256[3]` becomes explicit `x0, x1, x2`.
3. `(a*b)` that does not fit uint64 (notably `S * mul2` inside `yfprime`) uses
   a 128-bit product. Naive i64 wrap of `3e9 * 169349010160880` is
   `5251948605238943744`; the wide path does not use that wrap.
4. `dx = 0` fail-closes to `0` instead of uint256 wrap of `xp[j] - y - 1 = -1`.
5. Non-convergence fail-closes to `0` instead of `raise`.
6. Quotients that do not fit signed i64 (e.g. `mul1` at `ANN = MIN_A = 2700`) fail-close to `0` instead of wrapping negative.

Named goldens (i64-positive, equal `1e9` balances, `ANN=1707629`, `gamma=11809`):

| Case | Value |
|---|---|
| identity `newton_y(..., i=1)` | **1000000000** |
| `x0 += 10%` → `y1` | **909085543** |
| `get_dy` +10% no fee | **90914456** |
| `get_dy` +10% fee `3e6/1e10` | **90887181** |
| `get_dy` +1% no fee | **9906505** |
| `get_dy` `dx=0` | **0** (fail-closed) |
| `get_dy` `ANN=2700` (MIN_A) +10% | **0** (fail-closed: `mul1` exceeds signed i64) |
| imbalanced `(1.2e9, 0.9e9, 1e9)` `y1` | **833328413** |

Two-coin `x*y=k` out on the same 10% in is **90909090**; the tricrypto quote is
**90914456** (slightly more out because of the third coin). That is a curvature
comparison, not a TVL or gas claim.

## What is not claimed

- Mainnet **uint256** / `ONE=1e18` / price_scale / precision / `newton_D`
- The analytic `get_y` cubic / `cbrt` path
- LIN replacing Curve pools or the EVM
- Dollar savings, TVL capture, or zk soundness
- Stableswap `get_y` / `get_dy` (see clone-lin-curve-gety / getdy)
