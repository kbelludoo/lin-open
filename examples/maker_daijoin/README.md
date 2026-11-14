# Maker/Sky DaiJoin.join/exit — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`DaiJoin.join` / `DaiJoin.exit` (ERC20 DAI adapter: `rad = mul(ONE, wad)`).

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/join.sol` `DaiJoin` (AGPL-3.0-or-later, hash-pinned, **not vendored**)
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-maker-daijoin
- **LIN clone (this tree):** [`src/lin_maker_daijoin.lin`](../../src/lin_maker_daijoin.lin)
- **C11 oracle:** `test/oracles/maker_daijoin_c11.c`
- **Transpilable kernel:** `test/oracles/maker_daijoin_kernel.c`
- **Harness:** `python3 test/prove_maker_daijoin_external.py` / `make maker-daijoin-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_DAIJOIN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of DaiJoin's wad→rad adapter:

- `rad = mul(RAY, wad)` with scaled `RAY'=1e9` (Solidity `ONE = 10**27`)
- join: adapter vat DAI decreases by rad, usr vat DAI increases, ERC20 token burns wad; **does not require live**
- exit: requires `live==1`; sender vat DAI decreases by rad, adapter increases, ERC20 token mints wad
- overflow of `RAY*wad` / `to+rad` fail-closes instead of wrapping

Named goldens: JOIN `wad=1000` **rad=1e12** **token'=0**; EXIT **token'=1007**; cage join still ok.

## What is not claimed

- Solidity **uint256** / mainnet rad/wad/ray / ERC20 host / `vat.move` host parity
- LIN replacing Maker, Sky, DaiJoin, or the EVM
- TVL or dollar savings; zk soundness
- `GemJoin` ilk slip (different adapter) or `vat.move` alone (separate clone)
