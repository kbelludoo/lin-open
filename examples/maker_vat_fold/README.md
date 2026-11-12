# Maker/Sky `vat.fold` (signed ilk.rate / dai / debt) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO /
Sky Protocol `Vat.fold`. The LIN copy also lives in a separate repo.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later). Hash-pinned, **not vendored**.
- **LIN clone (this tree):** [`src/lin_maker_vat_fold.lin`](../../src/lin_maker_vat_fold.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-maker-vat-fold
- **C11 oracle:** `test/oracles/maker_vat_fold_c11.c`
- **Harness:** `python3 test/prove_maker_vat_fold_external.py` or `make maker-vat-fold-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_FOLD_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Maker's stability-fee fold at
**RAY' = 1e9** (mainnet RAY = 1e27 and `rad = wad * ray` do not fit i64).
Real deltas versus the Solidity:

1. Storage `ilk.Art` / `ilk.rate` / `dai[u]` / `debt` / `live` and the
   signed `rate` delta become explicit arguments.
2. `|Art| * |rate_delta|` uses a 128-bit product. If the magnitude does not
   fit i64 the clone fail-closes to 0 instead of wrapping.
3. `require(live == 1)` and `auth` / `dai[u]` are fail-closed by the
   Solidity/C/Rust transpilers (`REJ_SOLIDITY_VAT_FOLD` / `LIVE` / `AUTH` /
   `DAI_SLOT`).
4. Negative `rate_delta` (rate deflation) underflows `dai`/`rate` fail-close
   to 0, matching Maker's wrapped `uint + int` requires.

Named goldens (`Art = RAY' = 1e9`): delta=+1e6 → rate **1001000000**, rad
**1e15**; delta=-1e6 → rate **999000000**, rad **-1e15**; live=0 → **0**.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray rad / `vat.ilks` parity
- LIN replacing Maker, Sky, or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `jug.drip` / `pot.drip` (see clone-lin-maker-jug-drip / clone-lin-maker-pot-drip)

Machine-written evidence for a given run is in `maker_vat_fold_evidence.json`
(produced by the harness; do not hand-edit).
