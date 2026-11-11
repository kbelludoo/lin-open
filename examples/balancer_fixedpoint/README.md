# Balancer V2 FixedPoint — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Balancer V2
`FixedPoint` (`mulDown` / `mulUp` / `divDown` / `divUp` / `complement`). The
full LIN clone lives in a separate repository; lin-open keeps the kernel needed
to re-run proofs.

- **Upstream:** [balancer/balancer-v2-monorepo](https://github.com/balancer/balancer-v2-monorepo) `pkg/solidity-utils/contracts/math/FixedPoint.sol` (GPL-3.0-or-later)
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-balancer-fixedpoint
- **LIN kernel (this tree, for proofs):** [`src/lin_balancer_fixedpoint.lin`](../../src/lin_balancer_fixedpoint.lin)
- **Pinned fixture:** `test/fixtures/external_proof/FixedPoint.sol`
- **C11 oracle:** `test/oracles/balancer_fixedpoint_c11.c`
- **Harness:** `python3 test/prove_balancer_fixedpoint_external.py`
- **Event receipt:** `docs/events/EVENT_BALANCER_FIXEDPOINT_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive reproduction of Balancer's 1e18 floor/ceil formulas:

1. `mulDown(a,b) = (a*b) / ONE` and `mulUp(a,b) = 0 if product==0 else ((product-1)/ONE)+1`
   with a 128-bit product (schoolbook limbs in LIN, `__int128` in the C11 oracle).
   Quotients that do not fit i64 fail-closed to 0.
2. Distinct from Aave half-up wadMul: `divUp(1,3) = 333...334` (ceil) vs Aave
   `wadDiv(1,3) = 333...333` (half-up) vs `divDown(1,3) = 333...333` (floor).
3. Naive signed i64 `3e18 * 3e18` wraps; 128-bit mulDown yields `9e18`.

`powDown` / `powUp` / `LogExpMath` are **out of scope**.

## What is not claimed

- Solidity **uint256** / mainnet Vault or WeightedPool parity
- LIN replacing Balancer, Uniswap, or the EVM
- Any TVL or dollar savings figure
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `balancer_fixedpoint_evidence.json`
(produced by the harness; do not hand-edit).
