# Aave V3 PercentageMath — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`PercentageMath` (`percentMul` / `percentDiv`, half-up bps). The full LIN clone
lives in a separate repository; lin-open keeps the kernel needed to re-run proofs.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `contracts/protocol/libraries/math/PercentageMath.sol` (MIT after BUSL-1.1 Change Date 2023-01-27)
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-percent
- **LIN kernel (this tree, for proofs):** [`src/lin_aave_percent.lin`](../../src/lin_aave_percent.lin)
- **Pinned fixture:** `test/fixtures/external_proof/PercentageMath.sol`
- **C11 oracle:** `test/oracles/aave_percent_c11.c`
- **Harness:** `python3 test/prove_aave_percent_external.py`
- **Event receipt:** `docs/events/EVENT_AAVE_PERCENT_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive reproduction of Aave's percentage half-up formulas:

1. `percentMul(a,b) = (a*b + HALF_PERCENTAGE_FACTOR) / PERCENTAGE_FACTOR` with a
   128-bit product (schoolbook limbs in LIN, `__int128` in the C11 oracle).
   Quotients that do not fit i64 fail-closed to 0.
2. Distinct from floor `(a*b)/1e4`: `percentMul(3, 0.5e4) = 2` vs floor `1`.
3. Naive signed i64 `3e18 * 5000` wraps; 128-bit percentMul yields `1.5e18`.

## What is not claimed

- Solidity **uint256** / mainnet Aave pool parity
- LIN replacing Aave, Uniswap, or the EVM
- Any TVL or dollar savings figure
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `aave_percent_evidence.json`
(produced by the harness; do not hand-edit).
