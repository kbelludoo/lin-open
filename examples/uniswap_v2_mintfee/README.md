# Uniswap V2 `_mintFee` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V2
`UniswapV2Pair._mintFee` / `Math.sqrt`. The LIN clone itself is
`src/lin_uniswap_v2_mintfee.lin` in lin-open. A separate clone-lin GitHub
repository publishes the same `.lin` source:
**https://github.com/kbelludoo/clone-lin-uniswap-v2-mintfee**

- **Upstream:** [Uniswap/v2-core](https://github.com/Uniswap/v2-core) `contracts/UniswapV2Pair.sol` (GPL-3.0-or-later), tag `v1.0.1` commit `4dd59067c76dea4a0e8e4bfdda41877a6b16dedc`
- **Helpers:** `Math.sqrt` (Babylonian) and `SafeMath.mul/add/sub`
- **LIN clone (this tree):** `src/lin_uniswap_v2_mintfee.lin`
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v2-mintfee
- **C11 oracle:** `test/oracles/uniswap_v2_mintfee_c11.c`
- **Harness:** `python3 test/prove_uniswap_v2_mintfee_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V2_MINTFEE_CLONE_LIN.rulel`

GPL Uniswap source is **not vendored**. Pins are sha256 + git blob only.

## What is claimed

Experimental, uint64-scale reproduction of Uniswap V2's protocol-fee mint
(`liquidity = totalSupply * (rootK - rootKLast) / (5 * rootK + rootKLast)`).
The real deltas versus the Solidity pair in this profile are:

1. `IUniswapV2Factory(factory).feeTo()`, `kLast`, `totalSupply`, and `_mint`
   are function arguments / a returned liquidity amount, not hidden storage.
2. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit in uint64 the clone
   fail-closes to 0 instead of wrapping.
3. Babylonian `sqrt` is bounded at 80 steps (Solidity `while (x < z)` is
   unbounded) and uses unsigned `udiv` so high-bit uint64 operands do not
   take the signed-i64 path.

## What is not claimed

- Solidity **uint256** / **uint112** / mainnet **pair** parity
- LIN replacing Uniswap, Compound, or the EVM
- TVL, dollar savings, or wall-clock superiority vs solc/LLVM
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `uniswap_v2_mintfee_evidence.json`
(produced by the harness; do not hand-edit).
