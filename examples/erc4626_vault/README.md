# OpenZeppelin ERC-4626 virtual shares — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OpenZeppelin
v5.0.2 ERC-4626 `_convertToShares` / `_convertToAssets`. The LIN clone itself
is `src/lin_erc4626_vault.lin` in lin-open.

- **Upstream:** [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) `contracts/token/ERC20/extensions/ERC4626.sol` (MIT) tag `v5.0.2`
- **LIN clone (this tree):** [`src/lin_erc4626_vault.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-e4ba/src/lin_erc4626_vault.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-erc4626-vault
- **Pinned fixture:** `test/fixtures/external_proof/ERC4626.sol`
- **C11 oracle:** `test/oracles/erc4626_c11.c`
- **Harness:** `python3 test/prove_erc4626_vault_external.py`
- **Event receipt:** `docs/events/EVENT_ERC4626_VAULT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of OpenZeppelin's virtual-share
convert:

```
shares = floor(assets * (totalSupply + 10**offset) / (totalAssets + 1))
assets = ceil_or_floor(shares * (totalAssets + 1) / (totalSupply + 10**offset))
```

`previewDeposit` uses Floor; `previewMint` uses Ceil (OZ `Rounding` odd = up).

Real deltas versus the Solidity vault in this profile:

1. `totalSupply()`, `totalAssets()`, and `_decimalsOffset()` are function
   arguments, not hidden contract storage.
2. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit in uint64 the clone
   fail-closes to 0 instead of wrapping.
3. `offset > 18` fail-closes (`10**19` does not fit uint64).

## What is not claimed

- Solidity **uint256** / mainnet **ERC-4626 vault** parity
- Transpiling `Math.mulDiv` **assembly** (fail-closed: `REJ_SOLIDITY_INLINE_ASM`
  / `REJ_SOLIDITY_LIBRARY_CALL`)
- LIN replacing OpenZeppelin, Yearn, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Class: **EXPERIMENTAL**. Machine-written evidence for a given run is in
`erc4626_vault_evidence.json` (produced by the harness; do not hand-edit).
