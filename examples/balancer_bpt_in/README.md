# Balancer V2 `_calcTokenInGivenExactBptOut` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Balancer V2
`WeightedMath._calcTokenInGivenExactBptOut` (tokens in for an exact BPT mint).
The LIN kernel lives in a separate clone-lin repository; lin-open keeps proofs,
the C11 oracle, and the Compiler 0 harness.

- **Upstream:** [balancer/balancer-v2-monorepo](https://github.com/balancer/balancer-v2-monorepo) `pkg/pool-weighted/contracts/WeightedMath.sol` (GPL-3.0-or-later; **not vendored**)
- **Separate clone-lin repo:** [kbelludoo/clone-lin-balancer-bpt-in](https://github.com/kbelludoo/clone-lin-balancer-bpt-in)
- **LIN clone (this tree, results copy):** [`src/lin_balancer_bpt_in.lin`](../../src/lin_balancer_bpt_in.lin)
- **Pinned hashes:** `test/fixtures/external_proof/balancer_bpt_in.pin.rulel`
- **C11 oracle:** `test/oracles/balancer_bpt_in_c11.c`
- **Harness:** `python3 test/prove_balancer_bpt_in_external.py` or `make balancer-bpt-in-proof`
- **Event receipt:** `docs/events/EVENT_BALANCER_BPT_IN_CLONE_LIN.rulel`

Distinct from [clone-lin-balancer-bpt-join](https://github.com/kbelludoo/clone-lin-balancer-bpt-join) (`_calcBptOutGivenExactTokenIn`), [clone-lin-balancer-weighted](https://github.com/kbelludoo/clone-lin-balancer-weighted) (`_calcOutGivenIn`), and [clone-lin-balancer-in](https://github.com/kbelludoo/clone-lin-balancer-in) (`_calcInGivenOut`).

## What is claimed

Experimental, uint64-scale reproduction of the exact-BPT-out join with
`ONE=1e9`. Real deltas versus the Solidity WeightedMath in this profile:

1. Hidden storage (balance, normalized weight, BPT supply, swap fee) is lifted
   to function arguments.
2. `powUp` / `mulUp` / `divUp` overflow i64 at 1e9-scale. LIN uses a 128-bit
   product (schoolbook limbs in LIN, `__int128` in the C11 oracle) and
   fail-closes if the quotient does not fit i64.
3. `MAX_INVARIANT_RATIO=3e9` fail-closes (Solidity reverts). Naive linear
   `balance * bptOut / supply` and a full-fee-on-`amountInWithoutFee` misuse
   are explicit second oracles (named goldens: 50/50 `1e8` BPT costs
   **210000000** vs linear **100000000**; 0.3% fee **210315948** vs full-fee
   **210631896**).

## What is not claimed

- Solidity **uint256** / mainnet **ONE=1e18** / LogExpMath / `uint256[]` joins
- LIN replacing Balancer or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `balancer_bpt_in_evidence.json`
(produced by the harness; do not hand-edit).
