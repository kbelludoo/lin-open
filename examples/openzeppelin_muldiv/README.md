# OpenZeppelin Math.mulDiv — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OpenZeppelin
Contracts v5.0.2 `Math.mulDiv` + `Rounding`. The standalone LIN copy lives in
a separate clone-lin repository.

- **Upstream:** [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) `contracts/utils/math/Math.sol` (MIT) tag `v5.0.2`
- **LIN clone (this tree):** [`src/lin_openzeppelin_muldiv.lin`](../../src/lin_openzeppelin_muldiv.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-oz-muldiv
- **Pinned fixture:** `test/fixtures/external_proof/Math.sol`
- **Pinned excerpt:** `test/fixtures/external_proof/mulDiv.sol`
- **C11 oracle:** `test/oracles/openzeppelin_muldiv_c11.c`
- **Harness:** `python3 test/prove_openzeppelin_muldiv_external.py`
- **Event receipt:** `docs/events/EVENT_OPENZEPPELIN_MULDIV_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of OpenZeppelin's `floor(x*y/d)` /
`ceil(x*y/d)` with explicit rounding. Real deltas versus the Solidity library:

1. `Rounding` is an argument `0/1/2/3` (Floor/Ceil/Trunc/Expand), not an enum
   plus `uint8` cast. `unsignedRoundsUp` is `rounding % 2` after a range check.
2. `(x*y)/d` uses a 128-bit schoolbook product. OpenZeppelin reconstructs a
   512-bit product in Yul via `mulmod` and the Chinese Remainder Theorem.
3. Division by zero and quotient overflow fail-close to 0. Solidity reverts
   (`MathOverflowedMulDiv`). Remainder identity `x*y = q*d + r` is checked by
   an independent Python bigint oracle.

Commercial hook (not a TVL claim): ERC-4626 `convertToShares` is Floor
`mulDiv`; `previewMint` is Ceil `mulDiv`. Distinct from the already-cloned
`ceilDiv(a,b) = (a-1)/b+1`.

## What is not claimed

- Solidity **uint256** / 512-bit CRT parity
- LIN replacing OpenZeppelin or production vaults
- Compiler 0 executing `sol_from_sol` string-literal emit
- Wall-clock superiority vs solc

Machine-written evidence for a given run is in `openzeppelin_muldiv_evidence.json`
(produced by the harness; do not hand-edit).
