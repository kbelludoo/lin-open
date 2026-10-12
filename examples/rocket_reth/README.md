# Rocket Pool rETH exchange — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Rocket Pool
v1.4 `getRethValue` / `getEthValue` / `getExchangeRate`. The LIN clone itself
is `src/lin_rocket_reth.lin` in lin-open. The standalone LIN copy is
[clone-lin-rocket-reth](https://github.com/kbelludoo/clone-lin-rocket-reth).

- **Upstream:** [rocket-pool/rocketpool](https://github.com/rocket-pool/rocketpool) tag `v1.4` `contracts/contract/token/RocketTokenRETH.sol` (GPL-3.0-only)
- **LIN clone (this tree):** [`src/lin_rocket_reth.lin`](../../src/lin_rocket_reth.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-rocket-reth
- **Pinned fixture:** `test/fixtures/external_proof/RocketTokenRETH.sol`
- **C11 oracle:** `test/oracles/rocket_reth_c11.c`
- **Harness:** `python3 test/prove_rocket_reth_external.py`
- **Event receipt:** `docs/events/EVENT_ROCKET_RETH_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Rocket Pool's rETH exchange.

1. Hidden `getTotalETHBalance` / `getTotalRETHSupply` / `getContractAddress`
   become function arguments.
2. Empty `rethSupply` is **1:1** (the published special case). A wallet that
   prices empty LST deposits with Lido empty-div0 (`0`) or Morpho
   `VIRTUAL_SHARES=1e6` mis-counts the first Rocket mint.
3. After a 1-wei bootstrap + 1e6-ETH donation, Rocket and Lido both give the
   victim of 1e6 ETH **0** tokens (named contrast only; not a TVL claim).
4. `(a*b)/d` uses a 128-bit product. Quotient overflow fail-closes to 0.
   `totalEth==0` with supply>0: Solidity `getRethValue` reverts; LIN returns 0.

## What is not claimed

- Solidity **uint256** / mainnet **rETH** / deposit-pool / minipool parity
- LIN replacing Rocket Pool, Lido, Morpho, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `rocket_reth_evidence.json`
(produced by the harness; do not hand-edit).
