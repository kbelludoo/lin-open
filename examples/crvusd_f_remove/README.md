# crvUSD `_get_f_remove` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
crvUSD `Controller._get_f_remove` (liquidation collateral-withdraw fraction).
The LIN kernel is published in a **separate clone-lin repository**; lin-open
keeps the kernel copy needed to re-run Compiler 0 plus the auditable evidence.

- **Upstream (hash-pinned, not vendored):** [curvefi/curve-stablecoin](https://github.com/curvefi/curve-stablecoin) `curve_stablecoin/controller.vy` commit `81b3bea490e9b45221c82e78387920ccfeb05b33`. Curve.Fi publishes that tree as informational-only (no reproduction license). Hashes only: sha256 `42d82a3c36712cc1397f170d8e6924f7985035be2e54cfcfee1ce3d303a47c6b`, git blob `ac5e86ccaefffde86ced8ee4fa4b61cc5242206f`.
- **Clone-LIN repo:** [kbelludoo/clone-lin-crvusd-f-remove](https://github.com/kbelludoo/clone-lin-crvusd-f-remove) commit [`5bebba0726bd3716c4b33775fb40275485b2700d`](https://github.com/kbelludoo/clone-lin-crvusd-f-remove/commit/5bebba0726bd3716c4b33775fb40275485b2700d)
- **LIN kernel (this tree, identical bytes):** [`src/lin_crvusd_f_remove.lin`](../../src/lin_crvusd_f_remove.lin)
- **C11 oracle:** `test/oracles/crvusd_f_remove_c11.c`
- **Harness:** `python3 test/prove_crvusd_f_remove_external.py` or `make crvusd-f-remove-proof`
- **Event receipt:** `docs/events/EVENT_CRVUSD_F_REMOVE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE = 1e9`) reproduction of the published
formula

`f_remove = ((1 + h/2) / (1 + h) * (1 - frac) + frac) * frac`

Real deltas versus the Vyper controller:

1. `frac` and `health_limit` are function arguments (Vyper reads
   `liquidation_discounts` / `self`).
2. `unsafe_mul` / `unsafe_div` become 128-bit muldiv. Naive i64 wrap of
   `7e18 * 3e18` is `-5389669316318724096`; the wide path fail-closes to `0`.
3. `frac > SCALE` fail-closes to `0` instead of wrapping.
4. `cfr_collateral_out` vs `cfr_naive_frac_out` names the interpolation gap.

Named goldens (i64-positive, `SCALE=1e9`):

| Case | Value |
|---|---|
| `h=0`, `frac=0.5` | **500000000** (identity: no interpolation) |
| `frac=1` any `h` | **1000000000** |
| `frac=0.5`, `h=0.1` | **488636363** |
| same, collateral `y=1e9` vs naive frac | gap **11363637** |
| `frac=0.1`, `h=0.05` | **97857142** |
| `frac=0.9`, `h=0.04` | **898269230** |
| `frac=0.01`, `h=0.01` | **9950990** |
| `frac=0` | **0** |

A 50% debt liquidation with a 10% health-limit withdraws **48.8636363%** of
AMM collateral, not 50%. That is a curvature/discount comparison, not a TVL
or gas claim.

## What is not claimed

- Mainnet **uint256** / `WAD=1e18` / token precision
- Controller `_health` (see clone-lin-crvusd-health)
- LLAMMA `get_x_down` / `get_y_up` (see clone-lin-llamma-xy)
- LIN replacing crvUSD, Curve, or the EVM
- Dollar savings, TVL capture, or zk soundness
