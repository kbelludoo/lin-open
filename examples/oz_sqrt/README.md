# OpenZeppelin Math.sqrt / log2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OpenZeppelin
Contracts v5.0.2 `Math.sqrt` / `Math.log2`. The LIN copy also lives in a
separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-oz-sqrt
- **LIN clone in this tree:** [`src/lin_oz_sqrt.lin`](../../src/lin_oz_sqrt.lin)
- **Upstream:** [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) `contracts/utils/math/Math.sol` (MIT) tag `v5.0.2` commit `dbb6104ce834628e473d2173bbc9d47f81a9eec3`
- **Pinned excerpt:** `test/fixtures/external_proof/Math_sqrt_log2.sol`
- **C11 oracle:** `test/oracles/oz_sqrt_c11.c` (integer Newton; not libc `sqrt`)
- **Harness:** `python3 test/prove_oz_sqrt_external.py` or `make oz-sqrt-proof`
- **Event receipt:** `docs/events/EVENT_OZ_SQRT_CLONE_LIN.rulel`

Machine-written evidence for a given run is `oz_sqrt_evidence.json`
(produced by the harness; do not hand-edit).

## What is claimed

Experimental, non-negative **i64** reproduction of OpenZeppelin's log2 initial
guess plus seven Newton iterations and `min(result, a/result)`. Real deltas
versus the Solidity library in this profile:

1. `Rounding` enum overloads are fail-closed (`REJ_SOLIDITY_ENUM`); LIN takes
   rounding as an explicit integer (odd modes round up, matching
   `unsignedRoundsUp`).
2. `value >> 128` / `value >> 64` are skipped: they are well-defined on
   Solidity `uint256` and **undefined** as C `uint64_t` shifts of the width.
3. Ceil uses remainder-safe `ozs_sq_lt` instead of wrapping `result * result`.
4. Negative inputs and a zero Newton denominator fail-closed to 0.

## What is not claimed

- Solidity **uint256** / mainnet OpenZeppelin parity
- LIN replacing OpenZeppelin, Uniswap, or the EVM
- IEEE-754 / libc `sqrt` (C `sqrt(` is `REJ_C_FLOAT`)
- `Math.mulDiv` (inline assembly, out of scope)
- Compiler 0 executing `sol_from_sol` (string-literal modules stay
  `VM_REJ_STRING_LITERAL`)
