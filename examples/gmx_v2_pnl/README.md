# GMX V2 getPositionPnlUsd — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2
uncapped trader PnL. The LIN clone itself is `src/lin_gmx_v2_pnl.lin` in
lin-open. The copy of the clone lives in a separate repository.

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/position/PositionUtils.sol` + `Price.sol` + `Calc.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **Pinned commit:** `a85ea3491c19c93bb4b5a002d9b358fb769b7849`
- **LIN clone (this tree):** [`src/lin_gmx_v2_pnl.lin`](https://github.com/kbelludoo/lin-open/blob/HEAD/src/lin_gmx_v2_pnl.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-v2-pnl
- **Pinned fixtures:** `test/fixtures/external_proof/PositionPnlUsd.excerpt.sol`, `Price.sol`, `CalcRoundUp.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_pnl_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_pnl_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_PNL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2

`executionPrice = pickPriceForPnl(isLong, false)`

then

`pnl = isLong ? tokens*price - sizeUsd : sizeUsd - tokens*price`

and

`sizeDeltaInTokens = full close ? tokens : isLong ? ceil(tokens*sizeDelta/sizeUsd) : floor(...)`.

Class: **EXPERIMENTAL** (real published algorithm, reduced operand width).
Not mainnet uint256. Not pool-capped PnL.

Named contrasts (all recomputed this run):

| Path | Result |
|---|---|
| long full, price 2100 vs entry 2000 | `+1e14` |
| long full, price 1900 | `-1e14` |
| short minimize uses pmax=1950 not 1900 | `+5e13` (not `+1e14`) |
| long min oracle 2000/2100 | `0` (breakeven at min) |
| long wrong max oracle | fakes `+1e14` |
| V2 dust `tokens=3 sizeUsd=3001 p=1100` | `299` vs V1-style `300` |
| long half-close 3/3000/1500 | ceil dt=`2` PnL=`200` vs floor dt=`1` |
| naive i64 `7e9*2e9/1e6` | wraps `-4446744073709`; 128-bit `14000000000000` |

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 / `MAX_PNL_FACTOR_FOR_TRADERS` pool cap
- GMX V1 funding, fee, liquidation, or `adjustForDecimals` (other clones)
- LIN replacing GMX, Uniswap, or the EVM
- TVL or live trader-PnL profit
- General superiority vs solc/LLVM

Machine-written evidence for a given run is in `gmx_v2_pnl_evidence.json`
(produced by the harness; do not hand-edit).
