# Maker/Sky DssLitePsm fill/trim/chug — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Maker/Sky
`DssLitePsm` `rush` / `gush` / `cut` (the amounts behind `fill` / `trim` /
`chug`). The LIN copy itself is published at
https://github.com/kbelludoo/clone-lin-maker-litepsm-fill — lin-open keeps proofs only.

- **Upstream:** [sky-ecosystem/dss-lite-psm](https://github.com/sky-ecosystem/dss-lite-psm) `src/DssLitePsm.sol` (AGPL-3.0-or-later). **Not vendored.**
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-maker-litepsm-fill (HEAD `c38c621f`)
- **LIN kernel (this tree, identical copy):** [`src/lin_maker_litepsm_fill.lin`](../../src/lin_maker_litepsm_fill.lin)
- **C11 oracle:** `test/oracles/maker_litepsm_fill_c11.c`
- **Transpilable kernel:** `test/oracles/maker_litepsm_fill_kernel.c`
- **Harness:** `python3 test/prove_maker_litepsm_fill_external.py` / `make maker-litepsm-fill-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_LITEPSM_FILL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of LitePSM buffer bookkeeping
(`WAD' = RAY' = 1e9`, `to18=1000` as 6-dec gem → 9-dec wad):

- `tArt = gemAmt * to18 + buf` (overflow fail-closes)
- `rush` (fillable Dai) = `min(subcap(tArt, Art), subcap(line/RAY, Art), subcap(Line, debt)/RAY)`
- `gush` (trimmable Dai) = `min(max(subcap(Art, tArt), subcap(Art, line/RAY)), cash)`
- `cut` (chuggable fees) = `min(cash, cash + gemWad - art)` (underflow fail-closes)
- `fill`/`trim`/`chug` return that wad, or 0 when Solidity would revert (`wad==0`, `rate!=RAY`, missing vow)

Named goldens:

| id | call | value |
|---|---|---|
| rush pocket | gem=1e6 to18=1e3 Art=0 | **1000000000** |
| rush Art cap | Art=6e8 | **400000000** |
| rush ilk line | line/RAY=3e8 | **300000000** |
| rush global | (Line-debt)/RAY=1e8 | **100000000** |
| gush Art>tArt | gem=4e5 Art=1e9 cash=1e9 | **600000000** |
| cut fees | cash=5e8 gemWad=1e9 art=1.2e9 | **300000000** |
| chug no vow | vow=0 | **0** |
| fill nothing | Art already = tArt | **0** |

## What is not claimed

- Solidity **uint256** / mainnet USDC-6 `* 1e12` wad / RAY=1e27 parity
- Actual `vat.frob` / `daiJoin.exit` / pocket ERC-20
- sellGem/buyGem tin/tout (that is the LitePSM quote clone)
- LIN replacing Maker, Sky, or the EVM
- TVL or dollar savings
- zk / computational soundness of Merkle receipts

Machine-written evidence for a given run is in `maker_litepsm_fill_evidence.json`
(produced by the harness; do not hand-edit).
