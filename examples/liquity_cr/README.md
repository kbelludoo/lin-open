# Liquity ICR / decMul / decPow — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Liquity V1
`LiquityMath._computeCR` / `decMul` / `_decPow`. The LIN clone itself is
`src/lin_liquity_cr.lin` in lin-open. The standalone LIN copy is
[clone-lin-liquity-cr](https://github.com/kbelludoo/clone-lin-liquity-cr).

- **Upstream:** [liquity/dev](https://github.com/liquity/dev) `packages/contracts/contracts/Dependencies/LiquityMath.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_liquity_cr.lin`](../../src/lin_liquity_cr.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-liquity-cr
- **Pinned fixture:** `test/fixtures/external_proof/LiquityMath.sol`
- **C11 oracle:** `test/oracles/liquity_cr_c11.c`
- **Harness:** `python3 test/prove_liquity_cr_external.py`
- **Event receipt:** `docs/events/EVENT_LIQUITY_CR_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Liquity's collateral-ratio and
decimal exponentiation.

1. Hidden `PriceFeed` becomes a `price` argument. SafeMath `.mul` / `.add` /
   `.div` is 128-bit fail-closed muldiv, not wrapping i64.
2. `decMul` is **half-up** wad multiply. Floor wad-mul of `3 * 5e17 / 1e18` is
   **1**; Liquity `decMul` is **2**. A redemption-fee path that uses floor
   instead of half-up drifts `_decPow(MINUTE_DECAY_FACTOR, minutes)`.
3. `_computeCR` does **not** bake a liquidation threshold (named contrast vs
   Aave-style HF = `percentMul(lt) * 1e18 / debt`). Same 10000/10000
   coll/debt: Liquity CR **1e18** at price 1e18 vs Aave-style HF **0.85e18**
   at lt=85%.
4. `debt==0`: Solidity returns `2**256-1` (infinite CR). LIN fail-closes to
   **0** and `lq_cr_ok=0`. `NICR_PRECISION=1e20` exceeds signed i64 and is
   rejected, not wrapped.

## What is not claimed

- Solidity **uint256** / mainnet **Trove** / **LUSD** / **PriceFeed** parity
- LIN replacing Liquity, Aave, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk
- TVL or live liquidation profit

Machine-written evidence for a given run is in `liquity_cr_evidence.json`
(produced by the harness; do not hand-edit).
