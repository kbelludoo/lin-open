# Aave V3 `rayMul` / `rayDiv` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
WadRayMath `rayMul` / `rayDiv`. The LIN copy also lives in a separate repo.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `contracts/protocol/libraries/math/WadRayMath.sol` (MIT after BUSL Change Date 2023-01-27). Hash-pinned, **not vendored**.
- **LIN clone (this tree):** [`src/lin_aave_raymul.lin`](../../src/lin_aave_raymul.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-raymul
- **C11 oracle:** `test/oracles/aave_raymul_c11.c`
- **Harness:** `python3 test/prove_aave_raymul_external.py` or `make aave-raymul-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_RAYMUL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's half-up ray multiply/divide
at **RAY' = 1e9** (mainnet RAY = 1e27 does not fit i64). Real deltas versus the
Solidity Yul:

1. Operands are function arguments; there is no `assembly` / `HALF_RAY` Yul.
2. `(a*b + HALF_RAY') / RAY'` uses a 128-bit product. If the quotient does not
   fit uint64/i64 the clone fail-closes to 0 instead of wrapping.
3. Half-up is distinguished from floor: `rayMul(1, 5e8) = 1` vs floor `0`;
   `rayDiv(2, 3) = 666666667` vs floor `666666666`.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / aToken parity
- LIN replacing Aave or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `wadMul` / `wadDiv` (see [clone-lin-aave-wadray](https://github.com/kbelludoo/clone-lin-aave-wadray))
- `rayToWad` / `wadToRay` (see [clone-lin-aave-raytowad](https://github.com/kbelludoo/clone-lin-aave-raytowad))

Machine-written evidence for a given run is in `aave_raymul_evidence.json`
(produced by the harness; do not hand-edit).
