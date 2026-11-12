# Balancer V2 `_calcOutGivenIn` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Balancer V2
`WeightedMath._calcOutGivenIn` (weighted-pool swap amount-out). The LIN copy
also lives in a separate repo.

- **Upstream:** [balancer/balancer-v2-monorepo](https://github.com/balancer/balancer-v2-monorepo) `WeightedMath.sol` + `FixedPoint.sol` + `LogExpMath.sol`. Hash-pinned, **not vendored**. GPL-3.0-or-later.
- **LIN clone (this tree):** [`src/lin_balancer_weighted.lin`](../../src/lin_balancer_weighted.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-balancer-weighted
- **C11 oracle:** `test/oracles/balancer_weighted_c11.c`
- **Harness:** `python3 test/prove_balancer_weighted_external.py` or `make balancer-weighted-proof`
- **Event receipt:** `docs/events/EVENT_BALANCER_WEIGHTED_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Balancer's weighted `outGivenIn`
kernel at **ONE = 1e9**. Real deltas versus the Solidity:

1. Normalized storage weights become explicit `weightIn` / `weightOut` arguments.
2. Integer `powUp` for exponents 1/2/4 (Balancer's own FixedPoint fast path)
   plus bounded Newton for small rationals (60/40, 70/30). `LogExpMath.ln/exp`
   is fail-closed in the transpilers.
3. `amountIn > 30%` of `balanceIn` fail-closes to 0 (Solidity reverts).
4. `mulDown` / `divUp` use a 128-bit product. If the quotient does not fit
   i64 the clone fail-closes to 0 instead of wrapping.

Named goldens: 50/50 on `1e9` balances with `1e8` in → **90909090** (constant
product); 80/20 → **316986541**; 60/40 Newton → **133215825**; over-max-in
`300000001` → **0**.

## What is not claimed

- Solidity **uint256** / mainnet **ONE=1e18** / **LogExpMath** parity
- LIN replacing Balancer or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- Standalone FixedPoint clone (see clone-lin-balancer-fixedpoint)
- `_calcInGivenOut`, invariant, or BPT join/exit arrays

Machine-written evidence for a given run is in `balancer_weighted_evidence.json`
(produced by the harness; do not hand-edit).
