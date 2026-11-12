# Aave V3 rayToWad / wadToRay — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`WadRayMath.rayToWad` / `WadRayMath.wadToRay`. The LIN kernel is
`src/lin_aave_raytowad.lin` in lin-open. The full clone-lin copy lives in a
separate repository:

- **clone-lin:** https://github.com/kbelludoo/clone-lin-aave-raytowad
- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core)
  `contracts/protocol/libraries/math/WadRayMath.sol` commit
  `782f51917056a53a2c228701058a6c3fb233684a` (MIT after BUSL Change Date
  2023-01-27). Solidity is **not vendored** (hash-only pin).
- **C11 oracle:** `test/oracles/aave_raytowad_c11.c`
- **Harness:** `python3 test/prove_aave_raytowad_external.py`
- **Event receipt:** `docs/events/EVENT_AAVE_RAYTOWAD_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive reproduction of Aave's RAY↔WAD conversion:

1. `rayToWad`: `q = a / 1e9`, round **half up** when remainder `>= 5e8`.
2. `wadToRay`: `a * 1e9`, fail-closed to 0 if the product does not fit in i64.

Real deltas versus the Solidity library in this profile:

- Yul `assembly` is not executed. `lin_from_solidity.lin` lowers `rayToWad` /
  `wadToRay` to scalar integer math, and leftover `WAD_RAY_RATIO` Yul is
  `REJ_SOLIDITY_AAVE_RAYTOWAD`.
- Overflow of `wadToRay` fail-closes to 0 instead of a Yul `revert`.
- `WAD_RAY_RATIO = 1e9` is the **real** Aave constant (it fits in i64).
  `RAY = 1e27` does not; `wadToRay(1 WAD)` is therefore 0 in this profile.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** parity
- LIN replacing Aave, the EVM, or liquidity-index accounting
- TVL or dollar savings
- Computational soundness of Merkle / zk
- `wadMul` / `wadDiv` (see `clone-lin-aave-wadray`)

Named goldens: half-up `5e8` → **1** (floor would be 0); `1.5e9` → **2**
(floor 1); `wadToRay(1)` → **1e9**; `wadToRay(1e9)` → **1e18**;
`wadToRay(1e18)` → **0**.

Machine-written evidence for a given run is in `aave_raytowad_evidence.json`
(produced by the harness; do not hand-edit).
