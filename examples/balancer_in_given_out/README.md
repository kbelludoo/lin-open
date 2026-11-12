# Balancer V2 `_calcInGivenOut` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Balancer V2
`WeightedMath._calcInGivenOut` (weighted-pool exact-output amount-in). The LIN
copy also lives in a separate repo.

- **Upstream:** [balancer/balancer-v2-monorepo](https://github.com/balancer/balancer-v2-monorepo) `WeightedMath.sol` + `FixedPoint.sol` + `LogExpMath.sol`. Hash-pinned, **not vendored**. GPL-3.0-or-later.
- **LIN clone (this tree):** [`src/lin_balancer_in_given_out.lin`](../../src/lin_balancer_in_given_out.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-balancer-in
- **C11 oracle:** `test/oracles/balancer_in_given_out_c11.c`
- **Harness:** `python3 test/prove_balancer_in_given_out_external.py` or `make balancer-ingivenout-proof`
- **Event receipt:** `docs/events/EVENT_BALANCER_IN_GIVEN_OUT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Balancer's weighted `inGivenOut`
kernel at **ONE = 1e9**. Real deltas versus the Solidity:

1. Normalized storage weights become explicit `weightIn` / `weightOut` arguments.
2. Integer `powUp` for exponents 1/2/4 (Balancer's own FixedPoint fast path)
   plus bounded Newton for small rationals (60/40, 40/60, 70/30). `LogExpMath.ln/exp`
   is fail-closed in the transpilers.
3. `amountOut > 30%` of `balanceOut` fail-closes to 0 (Solidity reverts).
4. `power - ONE` then `mulUp`, **not** `complement`. The Solidity comment says
   the base is larger than one, so complement would yield 0. The clone's
   `bigo_wrong_complement` vector proves that misuse.
5. `mulUp` / `divUp` use a 128-bit product. If the quotient does not fit
   i64 the clone fail-closes to 0 instead of wrapping.

Named goldens: 50/50 on `1e9` balances with `1e8` out → **111111112** (constant
product, rounded up); 20/80 FOUR-path → **524157910**; 80/20 1/4-Newton →
**26690096**; over-max-out `300000001` → **0**; complement-misuse → **0**.

## What is not claimed

- Solidity **uint256** / mainnet **ONE=1e18** / **LogExpMath** parity
- LIN replacing Balancer or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `_calcOutGivenIn` (see clone-lin-balancer-weighted)
- Invariant or BPT join/exit arrays

Machine-written evidence for a given run is in `balancer_in_given_out_evidence.json`
(produced by the harness; do not hand-edit).
