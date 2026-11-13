# Velodrome `getAmountIn` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of the
exact-output inverse of Velodrome Finance V2 (Solidly-style)
`Pool.getAmountOut`. The published Pool has no `getAmountIn`; LIN publishes
the inverse (volatile closed-form +1 ceiling, stable Newton then fee
gross-up +1). Same kernel applies to Aerodrome on Base.

The LIN kernel is published in a **separate clone-lin repository**; lin-open
keeps the kernel copy needed to re-run Compiler 0 plus the auditable evidence.

- **Upstream (hash-pinned, not vendored):** [velodrome-finance/contracts](https://github.com/velodrome-finance/contracts) `contracts/Pool.sol` commit `b3065d8b6702b14b094f9f6046b752cc9f78c43b`. License GPL-3.0-or-later. Hashes only: sha256 `32d040ff419fa9b1f9113f7e10d587b332a2ab9c6b6099851025cc16a4e986bb`, git blob `91412c378bba4d8076271cee52e1397b1520b709`.
- **Clone-LIN repo:** [kbelludoo/clone-lin-velo-getin](https://github.com/kbelludoo/clone-lin-velo-getin) commit [`5a1e842e6971f3094184e0b7e0706cded612ba7f`](https://github.com/kbelludoo/clone-lin-velo-getin/commit/5a1e842e6971f3094184e0b7e0706cded612ba7f)
- **LIN kernel (this tree, identical bytes):** [`src/lin_velo_getin.lin`](../../src/lin_velo_getin.lin)
- **C11 oracle:** `test/oracles/velo_getin_c11.c`
- **Harness:** `python3 test/prove_velo_getin_external.py` or `make velo-getin-proof`
- **Event receipt:** `docs/events/EVENT_VELO_GETIN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE = 1e9`) inverse of the published quote:

- **Volatile:** `(reserveA * amountOut * 10000) / ((reserveB - amountOut) * (10000 - fee)) + 1`
- **Stable:** Newton `_get_y` on `y_new = reserveB - amountOut`, then gross-up `net * 10000 / (10000 - fee) + 1`

Real deltas versus a mechanical Solidity emit:

1. `reserveA/B`, `stable`, and `fee` are function arguments (Pool reads factory/token storage).
2. Wrapping i64 multiply becomes 128-bit muldiv. Naive i64 wrap of `4e9 * 4e9` is `-2446744073709551616`; the wide path fail-closes to `0`.
3. `amountOut >= reserveB`, `fee >= 10000`, and Newton non-convergence fail-close to `0`.
4. `vgi_ceil_gap` names the Uniswap-style +1 K-guard versus naive floor.

Named goldens (i64-positive, equal `1e9` reserves, `amountOut = 1e8`):

| Case | Value |
|---|---|
| volatile, fee 0 | **111111112** |
| volatile, fee 5 | **111166695** |
| volatile, fee 30 (Uniswap V2 0.3% match) | **111445448** |
| same, naive floor (no +1) | **111445447** (gap **1**) |
| same, `getAmountOut(getAmountIn)` | **100000000** (round-trip gap 0) |
| stable, fee 0 | **100050050** |
| stable, fee 1 | **100060056** |
| `amountOut=0` / `amountOut>=reserveB` / `fee=10000` | **0** |

A 10% exact-output on equal reserves costs **11.1445448%** in on the volatile 0.3% pool versus **10.0060056%** on the stable 0.01% pool. That is a curve/fee comparison, not a TVL or gas claim.

## What is not claimed

- Mainnet **uint256** / `1e18` / token-decimals parity
- Pool `getAmountOut` itself (see clone-lin-velo-getout)
- Solidly cubic `k` alone (see clone-lin-solidly-k)
- LIN replacing Velodrome, Aerodrome, Uniswap, or the EVM
- Dollar savings, TVL capture, or zk soundness
