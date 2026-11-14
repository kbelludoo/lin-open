# Ethena StakedUSDe vest+convert — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Ethena's
StakedUSDe 8-hour linear vest and ERC4626 convert. The LIN copy also lives in
the separate clone-lin repo linked below.

- **Upstream (hash-pinned, GPL-3.0, not vendored):** [ethena-labs/code4arena-contest](https://github.com/ethena-labs/code4arena-contest) `protocols/USDe/contracts/StakedUSDe.sol` commit `7ffedb8873c2286930804e1c4feee0410fd0f033`
- **LIN clone (this tree, for re-runnable proofs):** [`src/lin_ethena_susde.lin`](../../src/lin_ethena_susde.lin)
- **Separate clone-LIN repo:** https://github.com/kbelludoo/clone-lin-ethena-susde
- **C11 oracle:** `test/oracles/ethena_susde_c11.c`
- **Harness:** `python3 test/prove_ethena_susde_external.py` / `make ethena-susde-proof`
- **Event receipt:** `docs/events/EVENT_ETHENA_SUSDE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of StakedUSDe's `getUnvestedAmount` /
`totalAssets` / ERC4626 convert. The real deltas versus the Solidity vault in
this profile are:

1. `block.timestamp`, `lastDistributionTimestamp`, `vestingAmount`,
   `IERC20.balanceOf`, and `totalSupply` are function arguments, not hidden
   contract storage.
2. `VESTING_PERIOD' = 8` (hours) and `MIN_SHARES' = 1000` (Solidity 1 ether).
3. `(a*b)/d` fail-closes if the product does not fit int64 (naive i64 wrap of
   `7e9*3e9` is shown as a negative control). Remainder identity is checked by
   an independent Python bigint oracle.
4. Distinct from Sky sUSDS chi/RAY convert and from OZ ERC-4626 virtual offset.

Named goldens (uint64-scale, vest=800, t=2 of 8 hours, balance=10800, supply=10000):

| id | call | value |
|---|---|---|
| unvested | elapsed=2h | **600** |
| totalAssets | balance-unvested | **10200** |
| convertToShares | assets=1020 | **1000** |
| convertToAssets | shares=1000 | **1020** |
| previewMint | shares=1 | **2** |
| deposit MIN_SHARES | empty vault assets=500 | **ok=0** |
| transferInRewards | still vesting | **ok=0** |

## What is not claimed

- Solidity **uint256** / mainnet **stUSDe** parity
- LIN replacing Ethena, Sky, or the EVM
- OZ virtual-offset (`totalSupply+1`) convert
- TVL, dollar savings, or zk soundness

Machine-written evidence for a given run is in `ethena_susde_evidence.json`
(produced by the harness; do not hand-edit).
