# Bitcoin Core PermittedDifficultyTransition — LIN results (proofs only)

This directory holds **results and proofs** for the LIN clone of Bitcoin Core
v27.1 `PermittedDifficultyTransition` / timespan clamp. The LIN copy of the
kernel is published separately:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-bitcoin-core-permdiff
- **In-tree kernel (for Compiler 0 in this repo):** [`src/lin_bitcoin_perm_diff.lin`](../../src/lin_bitcoin_perm_diff.lin)

## Upstream (MIT, pinned)

- Repo: [bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) tag `v27.1`
- Commit: `1088a98f5aad080cc6cca2da174f206509fcda6c`
- File: `src/pow.cpp`
- git blob: `1e8d53de8bb87b0b9a30ff6439881cc2c40e38a4`
- sha256: `a997ebc9e89ec0ed0f98fe56e7ece7c0a799746d36be5c0951ca6fd264280a33`
- Fixture: `test/fixtures/external_proof/bitcoin_core_v27_1_pow.cpp`
- Lifted scalar C (no `::`, no `&`): `test/fixtures/external_proof/bitcoin_perm_diff_scalar.c`

## How to re-run (C11 Compiler 0, no Zig)

```bash
./test/verify_bitcoin_perm_diff.sh
# or:
python3 test/prove_bitcoin_perm_diff_external.py
```

Evidence for a given run is written to `bitcoin_perm_diff_evidence.json`
(machine output; do not hand-edit).

## What is claimed

**EXPERIMENTAL.** Real Bitcoin Core algorithm for:

1. Timespan clamp `[T/4, 4T]` with **published** `pow_tests.cpp` block-time
   vectors (1022578 unclamped, 289434 → 302400, 6048000 → 4838400).
2. Retarget window `height % 2016` (next height 32256 on, 32255 off).
3. Off-window `old_nbits == new_nbits` (the 2015/2016-block header-sync case)
   and `fPowAllowMinDifficultyBlocks ⇒ true`.
4. Compact 4× bound only for `nSize <= 8` (i64). Mainnet `0x1d00ffff`
   (`nSize=29`) returns `WIDTH=2` — fail-closed, not a uint256 pretend.

Consensus parameters are function arguments, not `const Consensus::Params&`.

The C transpiler (`src/lin_from_c.lin` v2) now fail-closes C++ `::` as
`REJ_C_CXX_SCOPE` and lone `&` in signatures as `REJ_C_REFERENCE`. That is the
defect this kernel found: `PermittedDifficultyTransition(const Consensus::Params& …)`
has no `*`, so v1 would have labelled it `OK`.

## What is not claimed

- Solidity/Bitcoin **uint256** compact target compare on mainnet nBits
- LIN replacing bitcoind, header sync, or consensus
- Wall-clock superiority vs Core
- Dollar / TVL / hashrate savings
- Merkle receipts as zk / computational soundness
