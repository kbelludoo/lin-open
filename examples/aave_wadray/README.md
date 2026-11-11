# Aave V3 WadRayMath — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`WadRayMath` (`wadMul` / `wadDiv`, half-up). The full LIN clone lives in a
separate repository; lin-open keeps the kernel needed to re-run proofs.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `contracts/protocol/libraries/math/WadRayMath.sol` (MIT after BUSL-1.1 Change Date 2023-01-27)
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-wadray
- **LIN kernel (this tree, for proofs):** [`src/lin_aave_wadray.lin`](../../src/lin_aave_wadray.lin)
- **Pinned fixture:** `test/fixtures/external_proof/WadRayMath.sol`
- **C11 oracle:** `test/oracles/aave_wadray_c11.c`
- **Harness:** `python3 test/prove_aave_wadray_external.py`
- **Event receipt:** `docs/events/EVENT_AAVE_WADRAY_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive reproduction of Aave's wad half-up formulas:

1. `wadMul(a,b) = (a*b + HALF_WAD) / WAD` with a 128-bit product (schoolbook
   limbs in LIN, `__int128` in the C11 oracle). Quotients that do not fit
   i64 fail-closed to 0.
2. Distinct from floor `mulWad`: `wadMul(3, 0.5e18) = 2` vs floor `1`.
3. `RAY = 1e27` does not fit uint64 or i64 (`awr_ray_fits = 0`).
   `wadToRay(1 WAD)` fail-closes; a scaled `RAY' = 1e9` is labeled
   experimental and is **not** Aave 1e27.

## What is not claimed

- Solidity **uint256** / mainnet Aave **RAY=1e27** parity
- LIN replacing Aave, Uniswap, or the EVM
- Any TVL or dollar savings figure
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `aave_wadray_evidence.json`
(produced by the harness; do not hand-edit).
