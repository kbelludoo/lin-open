# Pendle SYUtils — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Pendle V2
`SYUtils` (SY ↔ underlying asset conversion). The LIN copy is published in a
separate clone-lin repository; lin-open keeps proofs, the compact kernel, and
the Compiler 0 harness.

- **Upstream (hash-pinned, not vendored):** [pendle-finance/pendle-core-v2-public](https://github.com/pendle-finance/pendle-core-v2-public) `contracts/core/StandardizedYield/SYUtils.sol` (GPL-3.0-or-later)
  - commit `87685c89d05087535e9b9647eeda0e3d297d1f06`
  - git blob `b6a5ed174c6b93c29654254a5ce10aab28178285`
  - sha256 `25af0a883e174b713a88296b97998bb323ab79356d65cb50f3c7adcef91158c3`
- **Clone-lin (LIN copy):** https://github.com/kbelludoo/clone-lin-pendle-syutils
- **LIN kernel (this tree, for recomputation):** [`src/lin_pendle_syutils.lin`](../../src/lin_pendle_syutils.lin)
- **C11 oracle:** `test/oracles/pendle_syutils_c11.c`
- **Pointer-free C kernel:** `test/oracles/pendle_syutils_kernel.c`
- **Harness:** `python3 test/prove_pendle_syutils_external.py` / `make pendle-syutils-proof`
- **Event receipt:** `docs/events/EVENT_PENDLE_SYUTILS_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Pendle's `syToAsset`, `syToAssetUp`,
`assetToSy`, and `assetToSyUp`. Real deltas versus the Solidity library:

1. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit uint64 the clone fail-closes
   to 0 instead of wrapping.
2. Ceil variants use remainder (`floor+1` iff `r!=0`), not
   `(prod + denom - 1) / denom` which can overflow the add.
3. `exchangeRate == 0` fail-closes to 0 (Solidity 0.8 reverts).
4. The Solidity transpiler now expands `ONE` and `10 ** N` and classifies
   `(a + b - 1) / b` as `CEIL_DIV`.

Named goldens:

| id | call | value |
|---|---|---|
| ID | syToAsset(1e18, 1e18) | 1000000000000000000 |
| FLOOR | assetToSy(3e18, 10) | 3 |
| CEIL | assetToSyUp(3e18, 10) | 4 |
| DUST | syToAsset(3, 10) | 0 |
| DUST_UP | syToAssetUp(3, 10) | 1 |

## What is not claimed

- Solidity **uint256** / mainnet Pendle SY / PT / YT parity
- LIN replacing Pendle, Uniswap, or the EVM
- TVL or dollar savings
- That the pointer-free kernel (`ONE' = 1000`) equals the 1e18 LIN path
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `pendle_syutils_evidence.json`
(produced by the harness; do not hand-edit).
