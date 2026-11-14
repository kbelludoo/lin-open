# Maker/Sky Spotter.poke — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO
`Spotter.poke`. The published LIN copy lives in a separate repository.

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/spot.sol` AGPL-3.0-or-later
  commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
  sha256 `f772861927801ca1e32ba818ffc55df6ceffcc530ac3d8b6b223e7411bed118f`
  blob `2f5b98d9160e6f4f5c7943a964dcc47bb2c2c862`
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-maker-spot
- **LIN kernel (lin-open, for recomputing proofs):** `src/lin_maker_spot.lin`
- **C11 oracle:** `test/oracles/maker_spot_c11.c`
- **Pointer-free kernel:** `test/oracles/maker_spot_kernel.c`
- **Harness:** `python3 test/prove_maker_spot_external.py` / `make maker-spot-proof`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not a production OSM/vat replacement.

## What is claimed

Experimental, uint64-scale reproduction of

`spot = has ? rdiv(rdiv(mul(val, wad_ray), par), mat) : 0`

with `ONE=RAY'=1e9` and `wad_ray` as an argument (Solidity uses `10 ** 9` to
lift WAD→RAY). `pip.peek` `val`/`has`, `par`, and `mat` are arguments.
Wrapping `val*wad_ray` and `x*ONE` fail-close to 0. `vat.file` is not executed.

Named goldens (uint64-scale, `RAY'=1e9`):

| id | inputs | spot |
|---|---|---|
| 150% of val=3e9 | has=1 par=1e9 mat=1.5e9 | **2000000000** |
| stale OSM | has=0 | **0** |
| 200% of val=4e9 | mat=2e9 | **2000000000** |
| par=$2 of val=4e9 | par=2e9 mat=1e9 | **2000000000** |
| wad_ray=1000 | val=3e6 | **2000000000** |

Distinct from Clipper.kick OSM `top` and Vat.frob (which *consumes* `spot`).

## What is not claimed

- Solidity **uint256** / mainnet OSM / RAY=1e27 parity
- LIN replacing Maker, Sky, or the EVM
- TVL or dollar savings
- zk soundness
- Hidden `pip.peek` / `vat.ilks[].mat` SLOADs / `vat.file` side effects

Machine-written evidence for a given run is in `maker_spot_evidence.json`
(produced by the harness; do not hand-edit).
