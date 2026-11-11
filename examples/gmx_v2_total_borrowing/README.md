# GMX V2 getNextTotalBorrowing — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`getNextTotalBorrowing`. The LIN clone itself is `src/lin_gmx_v2_total_borrowing.lin` in
lin-open. A copy of the clone lives in a separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-total-borrowing](https://github.com/kbelludoo/clone-lin-gmx-v2-total-borrowing)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_total_borrowing.lin`](../../src/lin_gmx_v2_total_borrowing.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/GetNextTotalBorrowing.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_total_borrowing_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_total_borrowing_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_TOTAL_BORROWING_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **next total borrowing**:
`total -= applyFactor(prevSize, prevFactor); total += applyFactor(nextSize, nextFactor)`.
`isLong` selects the `totalBorrowing` storage key; it does not flip the math.
The real deltas versus the Solidity market in this profile are:

1. `total`, `prevSize`, `prevFactor`, `nextSize`, and `nextFactor` are
   function arguments, not hidden DataStore / market storage.
2. FLOAT is **1e6**, not GMX `FLOAT_PRECISION` 1e30.
3. Previous contribution larger than `total`, `size * factor` overflow, and
   `mid + next` overflow fail-close instead of wrapping or reverting with a
   host exception.

Named goldens (uint64-scale, FLOAT'=1e6): total 1e8 size 5e7 factor 4e5→5e5
next **105000000** vs signed fused when prev contrib > total **15000000**
(ok=0) vs getBorrowingFees **5000000** vs pending OI fees **20000000**; size
5e7→8e7 and factor 4e5→5e5 **120000000** vs applyFactor(size-delta) **115000000**;
remainder 3/4e5→3/7e5 nested **11** vs fused mulDiv **10**; open **125000000**;
close **80000000**; prev==total **25000000**; first position **25000000**;
7e9*2e9 **ok=0** vs naive i64 wrap **-4446744073709551616**; near-i64-max add
**ok=0** vs wrap **-9223372036854551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity / FLOAT **1e30**
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is `getBorrowingFees`, `getTotalPendingBorrowingFees`, signed
  fused next-prev, or `applyFactor` of the size delta
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_total_borrowing_evidence.json` (produced by the harness; do not
hand-edit).
