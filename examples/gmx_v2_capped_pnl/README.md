# GMX V2 getCappedPnl — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2
pool-capped PnL (`getCappedPnl` + trader pro-rata after
`MAX_PNL_FACTOR_FOR_TRADERS`). The LIN clone itself is
`src/lin_gmx_v2_capped_pnl.lin` in lin-open. The copy of the clone lives in
a separate repository.

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` + `Precision.sol` + `Keys.sol` + `PositionUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **Pinned commit:** `a85ea3491c19c93bb4b5a002d9b358fb769b7849`
- **LIN clone (this tree):** [`src/lin_gmx_v2_capped_pnl.lin`](https://github.com/kbelludoo/lin-open/blob/HEAD/src/lin_gmx_v2_capped_pnl.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-v2-capped-pnl
- **Pinned fixtures:** `test/fixtures/external_proof/GetCappedPnl.excerpt.sol`, `PrecisionApply.excerpt.sol`, `KeysMaxPnl.excerpt.sol`, `PositionCappedScale.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_capped_pnl_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_capped_pnl_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_CAPPED_PNL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2

`maxPnl = applyFactor(poolUsd, maxPnlFactor)` with `FLOAT' = 1e6`
(not `FLOAT_PRECISION = 1e30`)

then

`getCappedPnl = pnl < 0 ? pnl : min(pnl, maxPnl)`

and trader settlement

`if capped != pool && capped > 0 && pool > 0: trader * capped / pool else trader`.

Class: **EXPERIMENTAL** (real published algorithm, reduced operand width).
Not mainnet uint256. Not the uncapped `getPositionPnlUsd` kernel.

Named contrasts (all recomputed this run):

| Path | Result |
|---|---|
| pool 2e8, factor 50% (`5e5/1e6`) | `maxPnl = 1e8` |
| pool profit `1.5e8` | capped `1e8` |
| pool profit `5e7` (below cap) | stays `5e7` |
| pool loss `-2e8` | stays `-2e8` (never capped) |
| wrong symmetric cap of that loss | `-1e8` |
| trader `1.5e8` of pool `3e8` | pro-rata `5e7` |
| wrong `min(trader, maxPnl)` | `1e8` (overpays vs pool split) |
| factor `0` pool cap | `0`; trader stays `1.5e8` (`capped>0` guard) |
| naive i64 `7e9*2e9/1e6` | wraps `-4446744073709`; 128-bit `14000000000000` |

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 / `FLOAT_PRECISION=1e30`
- Uncapped `getPositionPnlUsd` / `pickPriceForPnl` (other clone)
- LIN replacing GMX, Uniswap, or the EVM
- TVL or live trader-PnL profit
- General superiority vs solc/LLVM

Machine-written evidence for a given run is in `gmx_v2_capped_pnl_evidence.json`
(produced by the harness; do not hand-edit).
