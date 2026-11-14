# Maker End cage(ilk)/skim/flow — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO
`End` global-settlement math. The published LIN copy lives in a separate repository.

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/end.sol` AGPL-3.0-or-later
  commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
  sha256 `40eca7c82e6794a4dabfa9b6ae41f177dd3c0bafacefc14f060b88f52667adef`
  blob `14e17b195c82bf0266db7bb78252b7b689f8b42f`
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-maker-end
- **LIN kernel (lin-open, for recomputing proofs):** `src/lin_maker_end.lin`
- **C11 oracle:** `test/oracles/maker_end_c11.c`
- **Pointer-free kernel:** `test/oracles/maker_end_kernel.c`
- **Harness:** `python3 test/prove_maker_end_external.py` / `make maker-end-proof`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not a production End replacement.

## What is claimed

Experimental, uint64-scale reproduction of

- `cage(ilk)` tag = wdiv(par, pip) = mul(par, WAD') / pip  (requires live==0 and tag unset)
- skim owe = rmul(rmul(art, rate), tag)
- skim wad = min(ink, owe); gap' = add(gap, sub(owe, wad))
- flow fix = mul(sub(owe_ilk, gap), RAY') / (debt / RAY')
- cash out = rmul(wad, fix)

with `WAD'=1e6`, `RAY'=1e9`. `live` / `tag` / `par` / `pip` / `art` / `rate` / `ink` / `gap` / `debt` are arguments.
Wrapping add/mul fail-close to 0. `pip.read` and `vat.grab` are not executed.

Named goldens (uint64-scale):

| id | inputs | result |
|---|---|---|
| cage tag | par=1e9 pip=2e9 | **500000** |
| cage while live | live=1 | **0** |
| skim full | ink=100000 owe=50000 | gap' **0** |
| skim under | ink=30000 owe=50000 | gap' **20000** |
| flow after under | Art=100e6 gap=20000 debt=1e17 | fix **300000** |
| cash 100 DAI | wad=100e6 fix=300000 | **30000** |
| flow no gap | gap=0 | fix **500000** |

Distinct from `Vow` settle (clone-lin-maker-vow) and `Spotter.poke` (clone-lin-maker-spot).

## What is not claimed

- Solidity **uint256** / mainnet WAD=1e18 / RAY=1e27 parity
- LIN replacing Maker, Sky, or the EVM
- TVL or dollar savings
- zk soundness
- Hidden `pip.read` / `vat.ilks` / `vat.urns` / `vat.grab` side effects

Machine-written evidence for a given run is in `maker_end_evidence.json`
(produced by the harness; do not hand-edit).
