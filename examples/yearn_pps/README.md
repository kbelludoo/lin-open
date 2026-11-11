# Yearn V2 pricePerShare — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Yearn V2
`pricePerShare` / `_calculateLockedProfit`. The LIN kernel copy lives in a
separate repository; lin-open keeps proofs, hashes, and the in-tree kernel
used by Compiler 0.

- **Upstream:** [yearn/yearn-vaults](https://github.com/yearn/yearn-vaults) `contracts/Vault.vy` v0.4.6 (`97ca1b2e4fcf20f4be0ff456dabd020bfeb6697b`, AGPL-3.0-or-later). Hashes only: sha256 `bc36fcf88e8662a7e1bd5f9c8213645214697dd72afda4e0cd87bfaeb0c4a19b`, git blob `1159912c093b12cf8d758f71d2d568cda69990af`. Vault.vy is **not vendored**.
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-yearn-pps
- **LIN clone (this tree, for proofs):** [`src/lin_yearn_pps.lin`](../../src/lin_yearn_pps.lin)
- **C11 oracle:** `test/oracles/yearn_pps_c11.c`
- **Harness:** `python3 test/prove_yearn_pps_external.py`
- **Event receipt:** `docs/events/EVENT_YEARN_PPS_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Yearn V2's linear harvest-profit
unlock and `pricePerShare = shareValue(10 ** decimals)`. Real deltas versus
the Vyper vault in this profile:

1. Storage (`block.timestamp`, `lastReport`, `lockedProfit`,
   `lockedProfitDegradation`, `totalIdle`, `totalDebt`, `totalSupply`,
   `decimals`) are function arguments.
2. `(a*b)/d` uses a 128-bit product. If the quotient does not fit i64 the
   clone fail-closes to 0 instead of wrapping.
3. `now < lastReport` fail-closes (Vyper uint256 would underflow).

Named goldens (`decimals=18`, idle=1e18, locked=0.1e18, supply=1e18,
default degradation `46e12`): empty PPS **1e18**; t0 harvest **0.9e18** vs
Lido-style ignore-lock **1e18**; 3h linear **0.94968e18** vs step-unlock
**0.9e18**; 6h unlocked **1e18**; empty mint 1:1.

## What is not claimed

- Vyper **uint256** / mainnet **yVault** parity
- LIN replacing Yearn, ERC-4626, Lido, or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `yearn_pps_evidence.json`
(produced by the harness; do not hand-edit).
