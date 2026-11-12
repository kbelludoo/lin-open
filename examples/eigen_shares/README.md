# EigenLayer StrategyBase shares — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of EigenLayer
`StrategyBase.sharesToUnderlyingView` / `underlyingToSharesView` / deposit
`newShares` (virtual SHARES_OFFSET = BALANCE_OFFSET = 1e3). The LIN copy also
lives in a separate repo.

- **Upstream:** [Layr-Labs/eigenlayer-contracts](https://github.com/Layr-Labs/eigenlayer-contracts) `StrategyBase.sol` at tag `v1.13.0`. Hash-pinned, **not vendored**. BUSL-1.1.
- **LIN clone (this tree):** [`src/lin_eigen_shares.lin`](../../src/lin_eigen_shares.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-eigen-shares
- **C11 oracle:** `test/oracles/eigen_shares_c11.c`
- **Harness:** `python3 test/prove_eigen_shares_external.py` or `make eigen-shares-proof`
- **Event receipt:** `docs/events/EVENT_EIGEN_SHARES_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of EigenLayer's virtual-share
conversion at **OFFSET = 1000**. Real deltas versus the Solidity:

1. Storage `totalShares` and `IERC20.balanceOf` (`_tokenBalance`) become
   explicit arguments.
2. The virtual-share haircut is explicit: 10% yield on a 1e9/1e9 book converts
   1e9 shares to **1099999900** underlying, not 1100000000.
3. `deposit` `newShares` uses the pre-transfer virtual prior balance
   (`tokenBalanceAfter + OFFSET - amount`).
4. `address` / `userUnderlying` and `MAX_TOTAL_SHARES=1e38` are fail-closed
   (`REJ_SOLIDITY_ADDRESS` / `REJ_SOLIDITY_WIDE_LIT`) instead of being silently
   dropped. `1e3` expands to `1000`; exponents `> 18` stay unexpanded.
5. `(a*b)/d` uses a 128-bit product. If the quotient does not fit i64 the clone
   fail-closes to 0 instead of wrapping.

Named goldens: empty-book 1000/1000 → **1000**; 1:1 1e9 → **1000000000**;
10% yield haircut → **1099999900**; first deposit 1e9 → **1000000000**;
deposit 1e8 after yield → **90909099**.

## What is not claimed

- Solidity **uint256** / mainnet **MAX_TOTAL_SHARES=1e38** / **IERC20.balanceOf**
- `userUnderlying(address)` / StrategyManager lookups
- LIN replacing EigenLayer or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `eigen_shares_evidence.json`
(produced by the harness; do not hand-edit).
