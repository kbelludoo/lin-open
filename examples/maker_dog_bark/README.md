# Maker/Sky Dog.bark — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Dog.bark` — the liquidation kick that seizes an unsafe vault and starts a
Dutch auction (`tab = due * chop / WAD`, `lot = dink`).

**Clone-LIN (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-maker-dog-bark

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `fa4f6630afb0624d04a003e920b0d71a00331d98`
  - `src/dog.sol` sha256 `274f7c5df8a13e535b496236436ebf726228fbe9285d94c542e2c9d2a78671de` blob `d941d80fbf89fe7b3d334cf4931c779e1ac7c0ce`
  - License AGPL-3.0-or-later. lin-open does **not** vendor the Solidity source.
- **LIN kernel (harness copy):** [`src/lin_maker_dog_bark.lin`](../../src/lin_maker_dog_bark.lin)
- **C11 oracle:** `test/oracles/maker_dog_bark_c11.c`
- **Transpilable kernel:** `test/oracles/maker_dog_bark_kernel.c`
- **Harness:** `python3 test/prove_maker_dog_bark_external.py` / `make maker-dog-bark-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_DOG_BARK_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256 rad/wad/ray. Not a production dog.

## Named goldens

- FULL `ink=1000 art=800 rate=1500 spot=1000 chop=1130` → dart **800**, dink **1000**, due **1200000**, tab **1356000**, leftover 0, id **7**
- PARTIAL `i_hole=2e6` → dart **1474**, dink **1842**, tab **1998744** (ilk Hole/Dirt room)
- DUSTY leftover (`i_hole=791000 dust=200000`) → dart **800** (full liquidation)
- DUSTY auction from partial (`i_hole=113000 dust=500000`) → **0**
- SAFE / NOT LIVE / LIMIT HIT / NULL AUCTION / spot=0 → **0**
- bark is **not** wards-auth; chip/tip are clipper.kick/redo not bark
- OVERFLOW `7e9*3e9` checked mul **0**; naive i64 wraps to `2553255926290448384`

## What is not claimed

Uint256 rad/wad/ray / mainnet Dog.bark / Clipper.take parity.
LIN replacing Maker, Sky, dog, clipper, or the EVM.
TVL or dollar savings. zk soundness. `clipper.take` / `vat.slip` / `vat.flux` / `vat.move`.
