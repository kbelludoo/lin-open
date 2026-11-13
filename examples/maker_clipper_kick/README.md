# Maker/Sky Clipper.kick — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Clipper.kick` (Dutch-auction start: OSM `top` and chip/tip keeper `coin`).

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/clip.sol` `kick` (AGPL-3.0-or-later, hash-pinned, **not vendored**)
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-maker-clipper-kick
- **LIN clone (this tree):** [`src/lin_maker_clipper_kick.lin`](../../src/lin_maker_clipper_kick.lin)
- **C11 oracle:** `test/oracles/maker_clipper_kick_c11.c`
- **Transpilable kernel:** `test/oracles/maker_clipper_kick_kernel.c`
- **Harness:** `python3 test/prove_maker_clipper_kick_external.py` / `make maker-clipper-kick-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_CLIPPER_KICK_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Clipper.kick's start price and
keeper incentive:

- `top = rmul(rdiv(mul(val, BLN), par), buf)` with scaled `WAD=1000`, `RAY=1e6`, `BLN=1000`
- `coin = add(tip, wmul(tab, chip))` and `sucks=1` iff tip or chip is nonzero
- wards-auth and circuit breaker level 1 (`stopped < 1`)
- overflow of `tab*chip` / `kicks+1` fail-closes instead of wrapping

Named goldens: FULL `val=2000 buf=1.1e6` **top=2200000** **coin=600** **id=8**.

## What is not claimed

- Solidity **uint256** / mainnet rad/wad/ray / OSM / `vat.suck` host parity
- LIN replacing Maker, Sky, Clipper, or the EVM
- TVL or dollar savings; zk soundness
- `clipper.take` buy math (separate clone) or `dog.bark` lot sizing
