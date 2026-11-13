# Curve tricrypto `newton_D` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
tricrypto `CurveCryptoMathOptimized3.newton_D` (Newton solver for the crypto
invariant `D` given three scaled balances). The LIN kernel is published in a
**separate clone-lin repository**; lin-open keeps the kernel copy needed to
re-run Compiler 0 plus the auditable evidence.

- **Upstream (hash-pinned, not vendored):** [curvefi/tricrypto-ng](https://github.com/curvefi/tricrypto-ng) `contracts/main/CurveCryptoMathOptimized3.vy` commit `ecaa8161c240f21dd7c3712eefc5637e1dac742b`. Curve.Fi publishes that tree as informational-only (no reproduction license). Hashes only: sha256 `d0d48e5c3fa00e36f841250cbce8665292ba3224bb050c948dc3b12a50f01d6c`, git blob `695c794cb8035e4b2848ad0354d0993dcfb9c7cb`.
- **Clone-LIN repo:** [kbelludoo/clone-lin-curve-newton-d](https://github.com/kbelludoo/clone-lin-curve-newton-d) commit [`588c9340ee7dfbe4502f43eafde9ea1196be5e09`](https://github.com/kbelludoo/clone-lin-curve-newton-d/commit/588c9340ee7dfbe4502f43eafde9ea1196be5e09)
- **LIN kernel (this tree, identical bytes):** [`src/lin_curve_newton_d.lin`](../../src/lin_curve_newton_d.lin)
- **C11 oracle:** `test/oracles/curve_newton_d_c11.c`
- **Harness:** `python3 test/prove_curve_newton_d_external.py` or `make curve-newton-d-proof`
- **Event receipt:** `docs/events/EVENT_CURVE_TRICRYPTO_NEWTON_D_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE = 1e9`) reproduction of Curve crypto Newton's
method for invariant `D` given three coin balances. Real deltas versus the
Vyper math contract:

1. Storage / `self` fields (`ANN`, `gamma`, `xp`) are function arguments.
2. `uint256[3]` becomes explicit `x0, x1, x2`.
3. `(a*b)` that does not fit uint64 (notably `S * mul2` and `D * D`) uses a
   128-bit product. Naive i64 wrap of `3e9 * 508044030482641` is
   `6755845818716831232`; the wide path does not use that wrap.
4. `K0_prev != 0` fail-closes (the cubic-root `get_y` apriori is not claimed).
5. Non-convergence fail-closes to `0` instead of `raise`.
6. Quotients that do not fit signed i64 (e.g. `mul1` at `ANN = MIN_A = 2700`) fail-close to `0` instead of wrapping negative.

Named goldens (i64-positive, `ANN=1707629`, `gamma=11809`):

| Case | Value |
|---|---|
| identity `newton_D(1e9,1e9,1e9)` | **3000000000** |
| `x0 += 10%` → `D` | **3096846429** |
| `x0 += 10%` → `D/S` (SCALE) | **998982719** |
| `x0 += 1%` → `D` | **3009971862** |
| imbalanced `(1.2e9, 0.9e9, 1e9)` `D` | **3077962761** |
| small equal `1e8` | **300000000** |
| `K0_prev != 0` | **0** (fail-closed) |
| `ANN=2700` (MIN_A) | **0** (fail-closed: `mul1` exceeds signed i64) |

A 10% extra of one coin raises the naive sum to `3100000000` but `D` only to
`3096846429` (`vp = 0.99898` vs `1.0` balanced). That is a curvature
comparison, not a TVL or gas claim.

## What is not claimed

- Mainnet **uint256** / `ONE=1e18` / price_scale / precision
- The `K0_prev` cubic-root apriori from `get_y`
- LIN replacing Curve pools or the EVM
- Dollar savings, TVL capture, or zk soundness
- Stableswap `get_D` / `_newton_y` (see clone-lin-curve-vp / clone-lin-curve-newton-y)
