# Maker/Sky GemJoin.join/exit — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`GemJoin.join` / `GemJoin.exit` (ERC20 collateral adapter: `vat.slip` ±wad).

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/join.sol` `GemJoin` (AGPL-3.0-or-later, hash-pinned, **not vendored**)
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-maker-gemjoin
- **LIN clone (this tree):** [`src/lin_maker_gemjoin.lin`](../../src/lin_maker_gemjoin.lin)
- **C11 oracle:** `test/oracles/maker_gemjoin_c11.c`
- **Transpilable kernel:** `test/oracles/maker_gemjoin_kernel.c`
- **Harness:** `python3 test/prove_maker_gemjoin_external.py` / `make maker-gemjoin-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_GEMJOIN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GemJoin's collateral adapter:

- join: requires `live==1`; usr vat gem += wad, adapter ERC20 += wad, sender ERC20 -= wad
- exit: **does not require live** (Maker cage still lets users withdraw); sender vat gem -= wad, adapter ERC20 -= wad, usr ERC20 += wad
- overflow of `usr_gem+wad` fail-closes instead of wrapping

Named goldens: JOIN `wad=1000` **usr_gem'=5000001000** **adapter'=1000**; EXIT **usr_tok'=1007**; cage join fail-closes.

## What is not claimed

- Solidity **uint256** / mainnet wad / ERC20 host / `vat.slip` host / `bytes32` ilk parity
- LIN replacing Maker, Sky, GemJoin, or the EVM
- TVL or dollar savings; zk soundness
- `DaiJoin` wad→rad (different adapter, inverse cage rules) or `wad = 2**255` exit overflow
