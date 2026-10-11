# Saddle getD / getY — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Saddle
Finance `SwapUtils.getD` / `getY` (Newton stableswap invariant, N=2). The
standalone LIN copy lives in a separate clone-lin repository.

- **Upstream:** [saddle-finance/saddle-contract](https://github.com/saddle-finance/saddle-contract) `contracts/SwapUtils.sol` (MIT) commit `2cfdd05580efb626d79d597034b2cf5ae89b5626`
- **LIN clone (this tree):** [`src/lin_saddle_getd.lin`](../../src/lin_saddle_getd.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-saddle-getd
- **Pinned fixture:** `test/fixtures/external_proof/SwapUtils.sol`
- **Pinned excerpt:** `test/fixtures/external_proof/getD.sol`
- **C11 oracle:** `test/oracles/saddle_getd_c11.c`
- **Harness:** `python3 test/prove_saddle_getd_external.py`
- **Event receipt:** `docs/events/EVENT_SADDLE_GETD_CLONE_LIN.rulel`

Curve.Fi `curve-contract` / `stableswap-ng` were **not** copied. Their LICENSE
grants no reproduction right. Saddle is the MIT Solidity Newton D that settled
historical stableswap TVL (sUSD, alETH, FRAX).

## What is claimed

Experimental, uint64-scale, two-coin reproduction of Saddle's Newton `getD`
and `getY`. Real deltas versus the Solidity library:

1. `xp` is two arguments `x0,x1`, not `uint256[] memory` plus SafeMath chains.
2. Precise A is an argument (`display A * 100`). Hidden storage / ramp-A time
   is not claimed.
3. `(a*b)/d` uses a 128-bit schoolbook product. Overflow and non-convergence
   fail-close to 0. Saddle reverts (`D does not converge`).
4. `dy` is the fee-less Saddle quote `x1 - y - 1`. Swap fee stays storage.

Commercial hook (not a TVL claim): a 1% swap of a balanced `1e6/1e6` pool
quotes **9999** on this invariant versus **9871** on Uniswap-style `x*y` with
the 997/1000 fee already cloned in-tree.

## What is not claimed

- Solidity **uint256** / **N>2** / mainnet Saddle pool parity
- LIN replacing Saddle, Curve, or a production AMM
- Compiler 0 executing `sol_from_sol` string-literal emit
- Wall-clock superiority vs solc
- A license to reproduce Curve.vy

Machine-written evidence for a given run is in `saddle_getd_evidence.json`
(produced by the harness; do not hand-edit).
