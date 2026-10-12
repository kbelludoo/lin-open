# Compound III Comet present/principal — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III
`CometCore.presentValueSupply` / `presentValueBorrow` / `principalValueSupply`
/ `principalValueBorrow`. The LIN clone itself is `src/lin_comet_pv.lin` in
lin-open. The standalone LIN copy is
[clone-lin-comet-pv](https://github.com/kbelludoo/clone-lin-comet-pv).

- **Upstream:** [compound-finance/comet](https://github.com/compound-finance/comet) `contracts/CometCore.sol` (GPL-2.0-or-later after BUSL Change Date 2025-12-31)
- **LIN clone (this tree):** [`src/lin_comet_pv.lin`](../../src/lin_comet_pv.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-comet-pv
- **Pinned fixture:** `test/fixtures/external_proof/CometCore.sol`
- **C11 oracle:** `test/oracles/comet_pv_c11.c`
- **Harness:** `python3 test/prove_comet_pv_external.py`
- **Event receipt:** `docs/events/EVENT_COMET_PV_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound III's present-value and
principal-value conversion.

1. Hidden `baseSupplyIndex` / `baseBorrowIndex` become arguments. `uint256(` /
   `uint104(` casts are rejected. `(a*b)/d` is 128-bit fail-closed muldiv.
2. `BASE_INDEX_SCALE` is **1e15**, not wad 1e18. A wallet that prices Comet
   balances with Compound V2 `exchangeRate` scale understates genesis present
   by **1000x** (principal 1000 → Comet **1000** vs naive wad **1**).
3. Supply principal **floors**; borrow principal **ceils** via remainder+1,
   not `(present * scale + index - 1) / index` which wraps in i64. Same
   present=1 index=3: floor **333333333333333** vs ceil **333333333333334**.
4. `index==0`: Solidity reverts. LIN fail-closes to **0** and `cm_index_ok=0`.

## What is not claimed

- Solidity **uint256** / mainnet **Comet** / **USDC** / **PriceFeed** parity
- LIN replacing Compound III, Aave, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk
- TVL or live liquidation profit

Machine-written evidence for a given run is in `comet_pv_evidence.json`
(produced by the harness; do not hand-edit).
