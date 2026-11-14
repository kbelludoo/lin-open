# Maker/Sky DssLitePsm — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Maker/Sky
`DssLitePsm` `_sellGem` / `_buyGem`. The LIN copy itself is published at
https://github.com/kbelludoo/clone-lin-maker-litepsm — lin-open keeps proofs only.

- **Upstream:** [sky-ecosystem/dss-lite-psm](https://github.com/sky-ecosystem/dss-lite-psm) `src/DssLitePsm.sol` (AGPL-3.0-or-later). **Not vendored.**
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-maker-litepsm (HEAD `efcced3f`)
- **LIN kernel (this tree, identical copy):** [`src/lin_maker_litepsm.lin`](../../src/lin_maker_litepsm.lin)
- **C11 oracle:** `test/oracles/maker_litepsm_c11.c`
- **Transpilable kernel:** `test/oracles/maker_litepsm_kernel.c`
- **Harness:** `python3 test/prove_maker_litepsm_external.py` / `make maker-litepsm-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_LITEPSM_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of LitePSM's 1:1 gem↔DAI quote:

`daiWad = gemAmt * to18ConversionFactor` (overflow fail-closes)

- sell (`tin`): `daiOut = daiWad - floor(daiWad * tin / WAD)` unless `tin == HALTED`
- buy (`tout`): `daiIn = daiWad + floor(daiWad * tout / WAD)` unless `tout == HALTED`
- `sellGemNoFee` / `buyGemNoFee` require `kissed == 1`

`HALTED` is sentinel `-1` (not `type(uint256).max`). `WAD' = 1e9`.
Fee uses `(dai/wad)*tin + (dai%wad)*tin/wad`. `(a*b)` wrap-detect XOR `__int128`.

Named goldens (`to18=1000` as 6-dec gem → 9-dec wad, `tin=tout=0.1%`):

| id | call | value |
|---|---|---|
| sell 0 fee | gem=1e6 to18=1e3 tin=0 | **1000000000** |
| sell 0.1% | tin=1e6 | **999000000** |
| buy 0.1% | tout=1e6 | **1001000000** |
| sell halted | tin=-1 | **0** |
| nofee without kiss | kissed=0 | **0** |
| nofee with kiss | kissed=1 | **1000000000** |

## What is not claimed

- Solidity **uint256** / mainnet USDC-6 `* 1e12` wad parity
- `vat.frob` fill/trim/chug, pocket ERC-20, wards/bud
- LIN replacing Maker, Sky, or the EVM
- DaiJoin wad→rad or GemJoin slip
- TVL or dollar savings
- zk / computational soundness of Merkle receipts

Machine-written evidence for a given run is in `maker_litepsm_evidence.json`
(produced by the harness; do not hand-edit).
