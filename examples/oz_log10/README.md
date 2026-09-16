# OpenZeppelin Math.log10 / log256 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OpenZeppelin
Contracts v5.0.2 `Math.log10` / `Math.log256`. The LIN copy also lives in a
separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-oz-log10
- **LIN clone (this tree):** [`src/lin_oz_log10.lin`](../../src/lin_oz_log10.lin)
- **Upstream:** [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) tag `v5.0.2` `contracts/utils/math/Math.sol` (MIT)
- **Pinned fixture:** `test/fixtures/external_proof/openzeppelin_math_v5_0_2.sol`
- **Excerpt:** `test/fixtures/external_proof/oz_log10_log256_excerpt.sol`
- **C11 oracle:** `test/oracles/oz_log10_c11.c`
- **Harness:** `python3 test/prove_oz_log10_external.py` or `make oz-log10-proof`
- **Event receipt:** `docs/events/EVENT_OZ_LOG10_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of OpenZeppelin's floor `log10` / `log256`
and the unsigned "round up" overloads (as an explicit `round_up: int`).

Real deltas versus the Solidity library in this profile:

1. `10 ** 64` and `10 ** 32` are skipped — they do not fit in i64. The Solidity
   transpiler now fail-closes `**` as `REJ_SOLIDITY_POW`.
2. `Rounding` enum overloads are `REJ_SOLIDITY_ENUM`; LIN takes `round_up` as
   an argument (0 = floor, 1 = expand).
3. Negatives fail-closed (`ozl_ok=0`). OpenZeppelin's `uint256` cannot be negative.
4. `ozl_dec_digits` / `ozl_hex_nbytes` expose the commercial use: buffer size
   for decimal / hex amount strings (1 ETH = 19 digits, 1 BTC = 9, 1 USDC = 7).

## What is not claimed

- Solidity **uint256** / mainnet OpenZeppelin parity
- LIN replacing OpenZeppelin, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk receipts
- That Compiler 0 executes `sol_from_sol` / `cfs_from_c` (string-literal modules
  still hit `VM_REJ_STRING_LITERAL`)

Machine-written evidence for a given run is in `oz_log10_evidence.json`
(produced by the harness; do not hand-edit).
