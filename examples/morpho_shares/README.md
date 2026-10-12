# Morpho Blue SharesMathLib — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Morpho Blue's
virtual-share conversion. The standalone LIN copy lives in the clone-lin repo;
lin-open keeps the kernel, fixtures, C11 oracle, and the recomputable harness.

- **Upstream:** [morpho-org/morpho-blue](https://github.com/morpho-org/morpho-blue) tag `v1.0.0` commit `55d2d99304fb3fb930c688462ae2ccabb1d533ad` (`src/libraries/SharesMathLib.sol` + `MathLib.sol`). File SPDX is GPL-2.0-or-later. The tag LICENSE is BUSL-1.1 with Change Date 2026-01-01 and Change License GPL-2.0-or-later; this run is after that date.
- **LIN clone (this tree):** [`src/lin_morpho_shares.lin`](../../src/lin_morpho_shares.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-morpho-shares
- **Pinned fixtures:** `test/fixtures/external_proof/SharesMathLib.sol`, `test/fixtures/external_proof/MathLib.sol`
- **C11 oracle:** `test/oracles/morpho_shares_c11.c`
- **Harness:** `python3 test/prove_morpho_shares_external.py`
- **Event receipt:** `docs/events/EVENT_MORPHO_SHARES_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Morpho's `toSharesDown` /
`toAssetsDown` / `toSharesUp` / `toAssetsUp` with `VIRTUAL_SHARES = 1e6` and
`VIRTUAL_ASSETS = 1`. Real deltas versus the Solidity library in this profile:

1. Virtual offsets are functions and extra arguments, not hidden `internal constant`s.
2. `(x*y)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in the C11 oracle). If the quotient does not fit uint64 the clone fail-closes to 0.
3. `mulDivUp` is remainder+1, not `x*y+(d-1)` (which wraps on the add).
4. Named contrast vs OpenZeppelin ERC-4626 offset-0 (`virtual shares = 1`):
   - empty market, 1000 assets → **1000000000** Morpho shares vs **1000** OZ shares
   - after a 1e6-asset donation, a 1e6-asset depositor → **1999996** vs **1**

## What is not claimed

- Solidity **uint256** / mainnet Morpho Blue market parity
- LIN replacing Morpho, OpenZeppelin, or the EVM
- TVL, gas savings, or a live inflation-attack profit figure
- Computational soundness of Merkle / zk (receipts here are tamper-evidence plus re-execution)

Machine-written evidence for a given run is in `morpho_shares_evidence.json`
(produced by the harness; do not hand-edit).
