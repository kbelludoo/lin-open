# Euler EVK IRMLinearKink — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Euler Vault Kit
`IRMLinearKink`. The LIN copy itself is published at
https://github.com/kbelludoo/clone-lin-euler-irm — lin-open keeps proofs only.

- **Upstream:** [euler-xyz/euler-vault-kit](https://github.com/euler-xyz/euler-vault-kit) `src/InterestRateModels/IRMLinearKink.sol` (file SPDX GPL-2.0-or-later; repo LICENSE BUSL-1.1 until 2029-04-24). **Not vendored.**
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-euler-irm (HEAD `0a94fe10`)
- **LIN kernel (this tree, identical copy):** [`src/lin_euler_irm.lin`](../../src/lin_euler_irm.lin)
- **C11 oracle:** `test/oracles/euler_irm_c11.c`
- **Transpilable kernel:** `test/oracles/euler_irm_kernel.c`
- **Harness:** `python3 test/prove_euler_irm_external.py` / `make euler-irm-proof`
- **Event receipt:** `docs/events/EVENT_EULER_IRM_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Euler's linear-kink IRM:

`utilization = borrows * type(uint32).max / (cash + borrows)` (empty pool → 0)

- if `util <= kink`: `ir = baseRate + util * slope1`
- else: `ir = baseRate + kink * slope1 + slope2 * (util - kink)`

`computeInterestRate` fail-closes unless `caller == vault`. View skips auth.
`(a*b)` uses wrap-detect XOR `__int128`; overflow fail-closes to 0.

Named goldens (slope1=2, slope2=3, kink=2^31, uint32.max scale):

| id | call | value |
|---|---|---|
| util 50/50 | cash=50 borrows=50 | **2147483647** |
| rate at ~50% | | **4294967294** |
| rate at 100% | cash=0 borrows=100 | **10737418237** |
| rate at 75% | cash=25 borrows=75 | **7516192765** |
| unauthorized compute | caller≠vault | **0** |
| empty pool | cash=0 borrows=0 base=10 | **10** |

## What is not claimed

- Solidity **uint256** / mainnet Euler vault parity
- APY ↔ SPY (`ln`, 365.2425 days)
- LIN replacing Euler, Compound, or the EVM
- Compound JumpRate (1e18 utilization, reserves, jump / BASE)
- TVL or dollar savings
- zk / computational soundness of Merkle receipts

Machine-written evidence for a given run is in `euler_irm_evidence.json`
(produced by the harness; do not hand-edit).
