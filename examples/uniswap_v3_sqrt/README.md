# Uniswap V3 SqrtPriceMath amount deltas — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V3
`SqrtPriceMath.getAmount0Delta` / `getAmount1Delta`.
The LIN clone lives in lin-open as `src/lin_uniswap_v3_sqrt.lin`. A standalone
copy is published at **https://github.com/kbelludoo/clone-lin-uniswap-v3-sqrt**.

- **Upstream:** [Uniswap/v3-core](https://github.com/Uniswap/v3-core) tag `v1.0.0` commit `e3589b192d0be27e100cd0daaf6c97204fdb1899` `contracts/libraries/SqrtPriceMath.sol`
- **License:** GPL-2.0-or-later (BUSL-1.1 Change Date 2023-04-01 elapsed)
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v3-sqrt
- **LIN clone (this tree):** [`src/lin_uniswap_v3_sqrt.lin`](../../src/lin_uniswap_v3_sqrt.lin)
- **Pinned fixture:** `test/fixtures/external_proof/SqrtPriceMath.sol` sha256 `ddd62e3a94346248677f30f1ab009ef015e71e4b8696dcca890eeabc9dc6c149` blob `685f485da43402235c3a9ce7fd85a49597b6373a`
- **C11 oracle:** `test/oracles/uniswap_v3_sqrt_c11.c`
- **Harness:** `python3 test/prove_uniswap_v3_sqrt_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V3_SQRT_CLONE_LIN.rulel`

## Formula (class: EXPERIMENTAL Q32-scale)

Uniswap V3 (Q64.96, not claimed here):

`amount0 = L * (sqrtB - sqrtA) / (sqrtA * sqrtB)` implemented as
`(L << 96) * (sqrtB - sqrtA) / sqrtB / sqrtA`

`amount1 = L * (sqrtB - sqrtA) / Q96`

LIN clone uses **Q32 = 2^32** (Q96 = 2^96 exceeds signed i64) and 128-bit floor/ceil muldiv.
Tuple swap of unordered prices is `v3s_sort2`. `roundUp` is an int argument.

## Named commercial contrasts (not a TVL claim)

At reduced Q32, liquidity `L=1000000`, sqrt-price from `Q` (price=1) to `2Q` (price=4):

| path | token amount |
| --- | ---: |
| sequential amount0 `(L*Q*(sb-sa)/sb)/sa` | **500000** |
| amount1 `L*(sb-sa)/Q` | **1000000** |
| naive `(L*(sb-sa))/(sa*sb)` | **0** |

Naive hides the entire **500000** of token0 because `sa*sb` overflows uint64 (wraps to 0).

At `L=1`, `sb=sa+1`: floor amount0 = **0**, ceil = **1** (1-unit protocol-solvency gap).
At price 1→2.25 (`sb=1.5 Q`): amount0 floor = **333333**, ceil = **333334**.

This is **not** a retread of OpenZeppelin `Math.mulDiv`: amount0 is two sequential
divisions plus a CLMM identity, not one generic `(a*b)/d` with a Rounding enum.

## What is not claimed

- Solidity **uint256** / **Q64.96** / mainnet **Pool** / **SwapRouter** / NFT position parity
- LIN replacing Uniswap, Compound, or the EVM
- General superiority vs solc/LLVM
- `getNextSqrtPriceFromInput` / `getNextSqrtPriceFromAmount0RoundingUp` (later kernel)

Machine-written evidence for a given run is in `uniswap_v3_sqrt_evidence.json`
(produced by the harness; do not hand-edit).
