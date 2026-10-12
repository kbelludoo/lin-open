# GMX V1 getFeeBasisPoints — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`VaultUtils.getFeeBasisPoints`. The standalone LIN copy lives in a
separate clone-lin repository; lin-open keeps proofs, the kernel, and the
transpiler delta.

- **Upstream:** [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts) `contracts/core/VaultUtils.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_gmx_fee.lin`](../../src/lin_gmx_fee.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-fee
- **Pinned fixture:** `test/fixtures/external_proof/VaultUtils.sol`
- **C11 oracle:** `test/oracles/gmx_fee_c11.c`
- **Harness:** `python3 test/prove_gmx_fee_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_FEE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V1 **dynamic USDG fees**:
rebate when a mint/swap improves a token's USDG weight versus its target,
tax when it worsens it. Class: EXPERIMENTAL (real published algorithm,
deliberately reduced operand width).

Real deltas versus the Solidity Vault in this profile:

1. `initial` / `delta` / `target` / `fee_bps` / `tax_bps` / `increment` / `has_dynamic` are explicit LIN arguments (no `vault.usdgAmounts`, no `hasDynamicFees()`, no token address).
2. `(tax * diff) / target` uses a 128-bit product. Naive i64 wrap is named and rejected.
3. Rebate is fail-closed at 0 when `rebateBps > feeBps` (same as Solidity).

Named commercial contrast on a 10k target: overweight increment **dynamic 130** vs **flat 100** (30 bps extra tax). Underweight increment **75** vs flat **100**. Using a Uniswap-style constant fee on GMX undercharges the overweight side.

Published GMX tests reproduced at uint64 scale: at-target 1000-delta **100**, 5000-delta **104**.

This is **not** a retread of Uniswap V2 `xy`, Solidly `x³y+y³x`, Saddle/Curve
`getD`/`getY`, or Maker `rpow`.

## What is not claimed

- Solidity **uint256** / mainnet GMX Vault or GLP parity
- LIN replacing GMX, GLP, or the EVM
- Wall-clock superiority vs solc
- That this clone is a production perps DEX

Machine-written evidence for a given run is in `gmx_fee_evidence.json`
(produced by the harness; do not hand-edit).
