# Compound JumpRateModel V2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2's
JumpRateModel. The LIN clone itself is `src/lin_compound_jumprate.lin`.

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/BaseJumpRateModelV2.sol` (BSD-3-Clause), pinned commit `a3214f67b73310d547e00fc578e8355911c9d376`
- **LIN clone:** [`src/lin_compound_jumprate.lin`](../../src/lin_compound_jumprate.lin)
- **Pinned fixture:** `test/fixtures/external_proof/BaseJumpRateModelV2.sol`
- **C11 oracle:** `test/oracles/compound_jumprate_c11.c`
- **Harness:** `python3 test/prove_compound_jumprate_external.py`
- **Independent third oracle:** `python3 test/prove_melhorias_independent.py` (Python bigint vs LIN vs C11)
- **Events:** `docs/events/EVENT_COMPOUND_JUMPRATE_CLONE_LIN.rulel`, `docs/events/EVENT_COMPOUND_JUMPRATE_HARDENING_2026_09_15.rulel`

## What is actually improved (experimental i64 profile)

1. **Storage parameters become arguments.** Solidity `getBorrowRateInternal` is `view` on `multiplierPerBlock` / `kink` / owner. LIN takes `base_block, mult_block, jump_block, kink`. Changing `mult_block` changes the rate.
2. **`(a*b)/d` uses a 128-bit product.** Naive signed-i64 `1e18*1e18` wraps. Quotients that do not fit nonnegative i64 **fail-closed to 0**. Remainder identity `q*d+r == a*b` is checked by Python bigint.

This is **not** paridade Solidity uint256 / cToken mainnet.

## What is not claimed

- Solidity uint256 / cToken mainnet parity
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM (a SipHash ~20.8× figure is compile-turnaround on one host)
- Computational soundness of Merkle receipts (C4 is tamper-evidence + re-execution, not zk)

The Solidity emit path still lowers `a * b / c` as wrapping i64. The JumpRate clone is the 128-bit artifact; `sol_jumprate_honesty_gate` records that gap instead of selling emit as IRM parity.

Machine-written evidence for a given run is in `compound_jumprate_evidence.json` and `independent_reproof.json` (produced by the harness; do not hand-edit).
