# Maker/Sky Vat.slip — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.slip` — the wards-authenticated signed gem credit used by GemJoin adapters.

**Clone-LIN (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-maker-vat-slip

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `fa4f6630afb0624d04a003e920b0d71a00331d98`
  - `src/vat.sol` sha256 `9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f` blob `ff90bbed5b36e54318bd5461cbf32e4167df2b28`
  - License AGPL-3.0-or-later. lin-open does **not** vendor the Solidity source.
- **LIN kernel (harness copy):** [`src/lin_maker_vat_slip.lin`](../../src/lin_maker_vat_slip.lin)
- **C11 oracle:** `test/oracles/maker_vat_slip_c11.c`
- **Transpilable kernel:** `test/oracles/maker_vat_slip_kernel.c`
- **Harness:** `python3 test/prove_maker_vat_slip_external.py` / `make maker-vat-slip-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_SLIP_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not a production vat.

## Named goldens

- JOIN `gem=5e9 wad=+1e9 wards=1` → leftover **6e9**, `join_amt=1e9`
- EXIT `gem=5e9 wad=-1e9 wards=1` → leftover **4e9**, `exit_amt=1e9`
- NO_AUTH `wards=0` → **0**
- UNDERFLOW `gem=1e9 wad=-2e9` → **0**
- OVERFLOW `7e18+3e18` → checked add **0**; naive i64 wraps to `-8446744073709551616`
- zero wad is a no-op **ok=1**; full exit leftover 0; join from 0 → 1e9
- `live_required=0`, `wish_required=0`, `auth_required=1`, unit is wad (not rad)

## What is not claimed

Uint256 / mainnet GemJoin parity. LIN replacing Maker, Sky, vat, or the EVM.
TVL or dollar savings. zk soundness. `vat.flux` (unsigned src-dst + wish).
