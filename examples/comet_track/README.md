# Compound III tracking-index / divBaseWei — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III
`accrueInternal` tracking-index wrap (`divBaseWei(speed * timeElapsed, totalSupplyBase)`).
The LIN clone itself is `src/lin_comet_track.lin` in lin-open.
A full copy lives in a separate clone-lin repository.

- **Upstream:** [compound-finance/comet](https://github.com/compound-finance/comet) `contracts/CometWithExtendedAssetList.sol` (GPL-2.0-or-later after BUSL-1.1 Change Date 2025-12-31)
- **LIN clone (this tree):** [`src/lin_comet_track.lin`](../../src/lin_comet_track.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-comet-track
- **Pinned excerpt:** `test/fixtures/external_proof/CometTrackingIndex.excerpt.sol`
- **C11 oracle:** `test/oracles/comet_track_c11.c`
- **Harness:** `python3 test/prove_comet_track_external.py`
- **Event receipt:** `docs/events/EVENT_COMET_TRACK_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound III's rewards tracking wrap:

`delta = divBaseWei(speed * dt, total) = (speed * dt) * baseScale / total`

with `baseScale = 10 ** decimals` (1e6 on USDC, 1e18 on WETH). This is **not**
`mulFactor` (`n * factor / FACTOR_SCALE`, `FACTOR_SCALE=1e18`) and **not**
present-value (`BASE_INDEX_SCALE=1e15`).

The real deltas versus the Solidity view in this profile are:

1. Hidden immutables (`baseScale`, `baseTrackingSupplySpeed`, `baseMinForRewards`)
   and storage (`totalSupplyBase`) are not read. They are function arguments.
2. `(speed * dt) * baseScale / total` uses a 128-bit product. If a quotient
   does not fit in uint64 the clone fail-closes to 0 instead of wrapping.
3. Empty supply or `total < baseMinForRewards` fail-closes to 0.
4. Reorder `(speed * baseScale / total) * dt` is a named rejected path: on
   USDC-scale `(2, 5, 1e6, 4e6)` it yields **0**, while Comet wrap yields **2**.
5. Named scale contrast on USDC 6-dec `(speed,dt,total)=(1,1,1e6)`:
   comet **1**, FACTOR confusion **1e12**, INDEX confusion **1e9**,
   `mulFactor(speed*dt, baseScale)` **0**. WETH 18-dec `(1,1,1e18)` hides
   the FACTOR bug (both **1**).

## What is not claimed

- Solidity **uint256** / mainnet **Comet USDC market** parity
- `getUtilization` / `presentValue` / `accruedInterestIndices` (other kernels)
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM
- A TVL or production-rewards claim

Machine-written evidence for a given run is in `comet_track_evidence.json`
(produced by the harness; do not hand-edit).
