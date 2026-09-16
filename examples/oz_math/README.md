# OpenZeppelin Math v5.0.2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OpenZeppelin
`Math.ceilDiv` / `average` / `try*` / `max` / `min`. The LIN copy of the kernel
also lives in a separate clone-lin repository.

- **Upstream:** [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) tag `v5.0.2` `contracts/utils/math/Math.sol` (MIT)
- **LIN clone (this tree, for the harness):** [`src/lin_oz_math.lin`](../../src/lin_oz_math.lin)
- **Clone-lin (separate repo):** https://github.com/kbelludoo/clone-lin-oz-math
- **Pinned fixture:** `test/fixtures/external_proof/Math.sol` (verbatim `tryAdd`..`ceilDiv` substring of the live file)
- **C11 oracle:** `test/oracles/oz_math_c11.c`
- **Harness:** `python3 test/prove_oz_math_external.py`
- **Event receipt:** `docs/events/EVENT_OZ_MATH_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of the published overflow-safe forms:

1. `ceilDiv` as `a==0 ? 0 : (a-1)/b+1`, with `b==0` fail-closed (Solidity panics).
2. `average` as `(a & b) + ((a ^ b) / 2)` instead of overflowing `(a+b)/2`.
3. `tryAdd`/`trySub`/`tryDiv` as explicit `ok` + `value` arguments, not a tuple.
4. `Math.mulDiv` assembly is **rejected** by the Solidity transpiler.

Canonical vectors: `ceilDiv(10,3)=4`, `average(3,5)=4`, `ceilDiv(INT64_MAX,2)=2^62`.

## What is not claimed

- Solidity **uint256** / mainnet OpenZeppelin library parity
- CRT / `mulmod` assembly of `Math.mulDiv`
- LIN replacing OpenZeppelin, ERC-4626 vaults, or the EVM
- Wall-clock superiority vs solc

Machine-written evidence for a given run is in `oz_math_evidence.json`
(produced by the harness; do not hand-edit).
