# Uniswap V3 getNextSqrtPriceFromInput — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V3's
next-sqrt-price math (`getNextSqrtPriceFromAmount0RoundingUp`,
`getNextSqrtPriceFromAmount1RoundingDown`, `getNextSqrtPriceFromInput`).

- **Upstream:** [Uniswap/v3-core](https://github.com/Uniswap/v3-core) tag `v1.0.0` `contracts/libraries/SqrtPriceMath.sol`
- **LIN clone (this tree):** [`src/lin_uniswap_v3_next_sqrt.lin`](../../src/lin_uniswap_v3_next_sqrt.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v3-next-sqrt
- **Pinned fixture:** `test/fixtures/external_proof/SqrtPriceMath.sol`
- **C11 oracle:** `test/oracles/uniswap_v3_next_sqrt_c11.c`
- **Harness:** `python3 test/prove_uniswap_v3_next_sqrt_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V3_NEXT_SQRT_CLONE_LIN.rulel`

Named contrast (not this kernel): amount-delta `getAmount0Delta` /
`getAmount1Delta` lives in [clone-lin-uniswap-v3-sqrt](https://github.com/kbelludoo/clone-lin-uniswap-v3-sqrt)
and lin-open PR 206. A V3 swap uses **this** kernel to step price, then amount-delta for tokens.

## What is claimed

Experimental, Q32=2^32 uint64-scale reproduction of Uniswap V3 next-sqrt. Real
deltas versus the Solidity library in this profile:

1. `Q96=2^96` exceeds signed i64 and is rejected. The working scale is `Q32=2^32`.
2. Amount0 next-sqrt **rounds up**: L=1e6, price 1, +5e5 token0 → **2863311531**
   not floor **2863311530** (1-unit solvency gap Uniswap documents).
3. Naive wrapping `(L*sqrtP)/(L+amount*sqrtP)` misses the Q-shift and yields **1**
   on that vector.
4. `amount=2^33` × Q32 overflows uint64: naive **leaves the price at Q32** (hides
   the swap); the overflow fallback is **499942**.
5. Adding `amount1=L` at price 1 steps sqrtP to `2*Q32` (price 4). `zeroForOne=1`
   vs `0` are opposite directions.

## What is not claimed

- Solidity **uint160** / **Q64.96** / mainnet **Pool** / SwapRouter / NFT parity
- LIN replacing Uniswap, Compound, or the EVM
- Computational soundness of Merkle / zk
- That this file is the amount-delta kernel

Machine-written evidence: `uniswap_v3_next_sqrt_evidence.json` (do not hand-edit).
