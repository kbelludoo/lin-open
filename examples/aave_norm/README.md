# Aave V3 `getNormalizedIncome` / `getNormalizedDebt` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
ReserveLogic index math. The LIN copy also lives in a separate repo.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `ReserveLogic.sol` + `MathUtils.sol` (MIT after BUSL Change Date 2023-01-27). Hash-pinned, **not vendored**.
- **LIN clone (this tree):** [`src/lin_aave_norm.lin`](../../src/lin_aave_norm.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-norm
- **C11 oracle:** `test/oracles/aave_norm_c11.c`
- **Harness:** `python3 test/prove_aave_norm_external.py` or `make aave-norm-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_NORM_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's aToken / variable-debt
normalized index at **RAY' = 1e9** (mainnet RAY = 1e27 does not fit i64).
Real deltas versus the Solidity:

1. `block.timestamp` and reserve storage become explicit `(rate, index, dt)` arguments.
2. `(a*b + HALF_RAY') / RAY'` and `(rate*dt)/SECONDS_PER_YEAR` use a 128-bit product. If the quotient does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. Solidity `365 days` now expands in `lin_from_solidity.lin` to `31536000`.
4. At RAY' a typical 5% APR makes the binomial x²/x³ terms floor to 0 (compound == linear). An extreme rate keeps a distinct second term. That is a documented scale limit, not mainnet parity.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / aToken parity
- LIN replacing Aave or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `rayMul` / `wadMul` / IRM (see the other Aave clone-lin repos)

Machine-written evidence for a given run is in `aave_norm_evidence.json`
(produced by the harness; do not hand-edit).
