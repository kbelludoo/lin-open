# Morpho Blue MathLib — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Morpho Blue's
WAD math and Taylor compound. The standalone LIN copy lives in a separate
repository.

- **Upstream:** [morpho-org/morpho-blue](https://github.com/morpho-org/morpho-blue) `src/libraries/MathLib.sol` (file SPDX MIT; repo LICENSE GPL-2.0) commit `339a885801972740eb27f51da110a4675b839d42`
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-morpho-mathlib
- **LIN kernel (proof copy in this tree):** `src/lin_morpho_mathlib.lin`
- **Pinned fixture:** `test/fixtures/external_proof/MathLib.sol`
- **C11 oracle:** `test/oracles/morpho_mathlib_c11.c`
- **Harness:** `python3 test/prove_morpho_mathlib_external.py` or `make morpho-mathlib-proof`
- **Event receipt:** `docs/events/EVENT_MORPHO_MATHLIB_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive reproduction of Morpho Blue `mulDivDown` / `mulDivUp`
/ `wMulDown` / `wDivDown` / `wDivUp` / `wTaylorCompounded`, plus the
`_accrueInterest` kernel `totalBorrow.wMulDown(rate.wTaylorCompounded(elapsed))`.

Real deltas versus the Solidity library in this profile:

1. `elapsed` is a function argument (Solidity uses `block.timestamp`).
2. `(x*y)/d` uses a 128-bit product. If the quotient does not fit in i64 the
   clone fail-closes to 0 instead of wrapping.
3. `mulDivUp` is remainder-ceil (`floor+1` iff `r!=0`), not `(x*y+(d-1))/d`.

Named goldens (i64-positive, WAD=1e18):

| call | value |
|---|---|
| `mulDivDown(7, 9, 2)` | **31** |
| `mulDivUp(7, 9, 2)` | **32** |
| `wTaylorCompounded(3170979198, 86400)` | **274010136628159** |
| `accrueInterest(1e18, 3170979198, 86400)` | **274010136628159** |

`3170979198` is ~10% APY as a WAD per-second rate (`0.10e18 / 31536000`).

## What is not claimed

- Solidity **uint256** / mainnet Morpho Blue market parity
- LIN replacing Morpho, Uniswap, or the EVM
- TVL or dollar savings
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `morpho_mathlib_evidence.json`
(produced by the harness; do not hand-edit).
