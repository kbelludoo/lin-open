# Solady FixedPointMathLib mulWad — LIN results (not the clone)

This directory holds **results and proofs** for the LIN clone of Solady's
`mulWad` / `mulWadUp` / `divWad` / `divWadUp`. The LIN copy of the kernel lives
in a separate repository:

- **Clone-lin:** https://github.com/kbelludoo/clone-lin-solady-mulwad
- **Upstream:** [Vectorized/solady](https://github.com/Vectorized/solady) `src/utils/FixedPointMathLib.sol` (MIT)
- **Pinned commit:** `2afba69bf67b78dd4abeadcc696052b3a6f71499`
- **Full-file sha256:** `d322e2a0b1f43dbd80a3cf26a40d1ca1cc19cf03737f1e8513485e266b47e9c3`
- **Git blob:** `12a83024751cd5fb7a12a7c22cc0bd5badd1846d`
- **Pinned excerpt:** `test/fixtures/external_proof/FixedPointMathLib_wad.sol`
- **C11 oracle:** `test/oracles/solady_mulwad_c11.c`
- **Harness:** `python3 test/prove_solady_mulwad_external.py`
- **Event receipt:** `docs/events/EVENT_SOLADY_MULWAD_CLONE_LIN.rulel`
- **In-tree kernel (for lin-open CI replay):** [`src/lin_solady_mulwad.lin`](../../src/lin_solady_mulwad.lin)

## What is claimed

Experimental, uint64-scale reproduction of Solady wad mul/div:

`(x * y) / WAD` and `(x * WAD) / y`, floor and ceil, with a 128-bit product.
Upstream bodies are Yul `assembly`; the Solidity transpiler **rejects** them
(`REJ_SOLIDITY_INLINE_ASM`). The LIN kernel is a hand-lowered integer clone,
not a claimed automatic Yul lowering.

Canonical vector: `mulWad(2e18, 3e18) = 6e18`.

## What is not claimed

- Solidity **uint256** / on-chain Solady parity
- LIN replacing Solady, Morpho, ERC-4626 vaults, or the EVM
- Automatic transpile of inline assembly
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Class: **EXPERIMENTAL**. Machine-written evidence is in
`solady_mulwad_evidence.json` (do not hand-edit).
