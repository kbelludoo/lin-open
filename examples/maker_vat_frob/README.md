# Maker/Sky vat.frob — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO
`Vat.frob` (the Dai/USDS CDP lock/draw/wipe/free kernel). The LIN copy lives in
a separate clone-lin repository; lin-open keeps proofs only.

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later)
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-maker-vat-frob commit [`7e219fd7`](https://github.com/kbelludoo/clone-lin-maker-vat-frob/commit/7e219fd71412a851c6f6706b45cf12faf7a89f9c)
  - LIN kernel blob `99419e74b6e6be102b99b7daf90ebd82ffb147b5` (commit `562f9e34`)
  - C11 oracle blob `aa9750e46c4797d0e90baa2a3d909b2f5694fc7b` (commit `7e219fd7`)
- **LIN kernel (this tree, identical bytes):** [`src/lin_maker_vat_frob.lin`](../../src/lin_maker_vat_frob.lin)
- **C11 oracle:** `test/oracles/maker_vat_frob_c11.c`
- **Harness:** `python3 test/prove_maker_vat_frob_external.py` / `make maker-vat-frob-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_FROB_CLONE_LIN.rulel`

Pinned commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
sha256 `9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f`
git blob `ff90bbed5b36e54318bd5461cbf32e4167df2b28`.

## What is claimed

Experimental uint64-scale (`RAY'=1e9`) CDP safety: signed `ink`/`art` updates,
`tab = art * rate`, `tab <= ink * spot` unless the urn became less risky,
debt-ceiling and dust checks. Storage and `wish` consent are function arguments
or rejected. `(a*b)` uses a 128-bit product and fail-closes if the result does
not fit i64.

Named goldens this run (`make maker-vat-frob-proof`):

| Case | Value |
|---|---|
| OPEN lock `1e9` + draw `5e8` at 200% spot | `frob_ok=1`, `tab=5e17` |
| UNSAFE draw `3e9` on the same collateral | `frob_ok=0` (`tab=3e18 > cov=2e18`) |
| LESS-RISKY wipe while underwater | `frob_ok=1` |
| 150% spot `max_art` vs naive 1:1 | `1500000000` vs `1000000000` (buffer `5e8`) |
| naive i64 `7e18*3e18` | wraps `-5389669316318724096`; 128-bit → `0` |

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray **rad** parity
- LIN replacing Maker, Sky, vat, or the EVM
- `wish` / `wards` / `gem` / `dai[u]` mapping consent
- TVL or dollar savings; zk soundness
- `vat.fold` (see clone-lin-maker-vat-fold)

Class: **EXPERIMENTAL**. Evidence JSON is machine-written; do not hand-edit.
