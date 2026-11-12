# Balancer V2 `_calcBptOutGivenExactTokenIn` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Balancer V2
`WeightedMath._calcBptOutGivenExactTokenIn` (single-token join: BPT minted for
an exact token in). The LIN copy also lives in a separate repo.

- **Upstream:** [balancer/balancer-v2-monorepo](https://github.com/balancer/balancer-v2-monorepo) `WeightedMath.sol` + `FixedPoint.sol` + `LogExpMath.sol`. Hash-pinned, **not vendored**. GPL-3.0-or-later.
- **LIN clone (this tree):** [`src/lin_balancer_bpt_join.lin`](../../src/lin_balancer_bpt_join.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-balancer-bpt-join
- **C11 oracle:** `test/oracles/balancer_bpt_join_c11.c`
- **Harness:** `python3 test/prove_balancer_bpt_join_external.py` or `make balancer-bpt-join-proof`
- **Event receipt:** `docs/events/EVENT_BALANCER_BPT_JOIN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Balancer's weighted single-token
BPT-join kernel at **ONE = 1e9**. Real deltas versus the Solidity:

1. Normalized storage weight, BPT supply and swap fee become explicit arguments.
2. Integer `powDown` for exponents 1/2/4 plus bounded Newton for 4/5, 1/5, 3/5.
   `LogExpMath.ln/exp` is fail-closed in the transpilers.
3. The taxable-excess fee split is explicit (`mulUp` on the portion of
   `amountIn` above `invariantRatioWithFees`).
4. `uint256[]` multi-token `_calcBptOutGivenExactTokensIn` is fail-closed
   (`REJ_SOLIDITY_ARRAY` / `REJ_SOLIDITY_BPT_JOIN`) instead of being silently
   dropped.
5. `mulDown` / `mulUp` use a 128-bit product. If the quotient does not fit
   i64 the clone fail-closes to 0 instead of wrapping.

Named goldens: 50/50 fee-0 on `1e9` balance/supply with `1e8` in → **48808848**
(`sqrt(1.1)-1`); 0.3% fee → **48737336**; 80/20 → **79230342**.

## What is not claimed

- Solidity **uint256** / mainnet **ONE=1e18** / **LogExpMath** parity
- Multi-token array joins
- LIN replacing Balancer or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `_calcOutGivenIn` / `_calcInGivenOut` (see the weighted swap clone-lins)

Machine-written evidence for a given run is in `balancer_bpt_join_evidence.json`
(produced by the harness; do not hand-edit).
