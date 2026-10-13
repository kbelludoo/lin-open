# GMX V2 getNextFundingFactorPerSecond — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2 adaptive
funding factor per second. The LIN copy also lives in the separate repository
[clone-lin-gmx-v2-funding-fps](https://github.com/kbelludoo/clone-lin-gmx-v2-funding-fps).

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** `src/lin_gmx_v2_funding_fps.lin`
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-v2-funding-fps
- **Pinned excerpts:** `test/fixtures/external_proof/GetNextFundingFactorPerSecond.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_funding_fps_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_funding_fps_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_FUNDING_FPS_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's *rate* (not the already
cloned paying-side `getNextFundingAmountPerSize`):

1. Storage / DataStore parameters are function arguments.
2. `(a*b)/d` uses a 128-bit product. Quotient that does not fit uint64 fail-closes to 0.
3. Named audit contrasts versus the published formula:
   - charged fps is bound by `minFundingFactorPerSecond`; saved fps is not
   - decrease is `decFps * duration`, not `applyFactor(imbalance, decFps)`
   - decrease past magnitude becomes `+/-1`, not `0`
   - skew flip keeps the old sign until saved crosses zero

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 / `FLOAT_PRECISION=1e30` / PRBMath pow
- LIN replacing GMX, Uniswap, or the EVM
- TVL or live funding paid
- Identity with V1 `getNextFundingRate` or with `getNextFundingAmountPerSize`

Machine-written evidence for a given run is in `gmx_v2_funding_fps_evidence.json`
(produced by the harness; do not hand-edit).
