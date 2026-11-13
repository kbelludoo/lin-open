# Maker/Sky Clipper.take — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Clipper.take` — the Dutch-auction collateral buy used by liquidations.

**Clone-LIN (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-maker-clipper-take

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `fa4f6630afb0624d04a003e920b0d71a00331d98`
  - `src/clip.sol` sha256 `1ea897fc0e8e0964a2e5098716d86fdcd93d11e0b2e4f65998eb1b7650d167de` blob `c43d8fff46a4ad225d1fa031b4b1de618345cba7`
  - License AGPL-3.0-or-later. lin-open does **not** vendor the Solidity source.
- **LIN kernel (harness copy):** [`src/lin_maker_clipper_take.lin`](../../src/lin_maker_clipper_take.lin)
- **C11 oracle:** `test/oracles/maker_clipper_take_c11.c`
- **Transpilable kernel:** `test/oracles/maker_clipper_take_kernel.c`
- **Harness:** `python3 test/prove_maker_clipper_take_external.py` / `make maker-clipper-take-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_CLIPPER_TAKE_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256 rad/wad/ray. Not a production clipper.

## Named goldens

- FULL `lot=1000 amt=2000 price=100 tab=200000` → slice **1000**, owe **100000**, leftover lot **0**
- TAB_CAP `price=200 tab=100000` → slice **500**, leftover tab **0** (collateral returned to usr)
- CHOST `amt=400 chost=70000` → slice **300**, leftover tab **70000** (dust floor)
- NO_PARTIAL `tab=50000 <= chost` and `slice < lot` → **0**
- TOO_EXPENSIVE `max < price` → **0**; NEEDS_RESET `done=1` → **0**; STOPPED `>=3` → **0**
- STOPPED `=2` still allows take; take is **not** wards-auth; chip/tip are kick/redo not take
- OVERFLOW `7e9*3e9` checked mul **0**; naive i64 wraps to `2553255926290448384`

## What is not claimed

Uint256 rad/wad/ray / mainnet Clipper.take / Dog.bark parity.
LIN replacing Maker, Sky, clipper, or the EVM.
TVL or dollar savings. zk soundness. `vat.slip` / `vat.flux` / `vat.move`.
