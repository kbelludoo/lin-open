# Bitcoin Core v27.1 GetFee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Bitcoin Core
`CFeeRate::GetFee`. The LIN kernel lives at
`src/lin_bitcoin_core_getfee.lin`. The clone-lin copy is
**https://github.com/kbelludoo/clone-lin-bitcoin-core-getfee**.

- **Upstream:** [bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) tag `v27.1`
  commit `1088a98f5aad080cc6cca2da174f206509fcda6c` (MIT)
  - `src/policy/feerate.cpp` sha256 `dcee0d3c510936032addb0735dfb1e5389dcd4f8cf31e6867b94e2e14c6cb561`
  - `src/consensus/amount.h` sha256 `cb7bd951877f3fea5a0c280d4bb907a8403437add81e3d5b898879b78fdc877e`
- **C11 oracle:** `test/oracles/bitcoin_core_getfee_c11.c`
- **Harness:** `python3 test/prove_bitcoin_core_getfee_external.py`
- **Event:** `docs/events/EVENT_BITCOIN_CORE_GETFEE_CLONE_LIN.rulel`

## What is claimed (EXPERIMENTAL)

Integer ceil of `sat/kvB * vbytes / 1000` with i64 overflow fail-closed, plus
Core's 1-sat minimum. `GetVirtualTransactionSize(weight) = (wu+3)/4` is explicit.
A second function fees by weight (`ceil(sat/kwu * wu / 1000)`). On 381 wu they
disagree: **332 vs 330 sat** at 864 sat/kwu, **9600 vs 9525 sat** at 100 sat/vB.

On a wallet-scale grid (0..4000 sat/kvB × 0..400 vB) gcc `std::ceil(double)`
**matches** integer ceil. The published gap is vsize rounding vs weight-native
rounding, not an IEEE disagreement at those sizes.

`lin_from_c` v2 now rejects Core's GetFee after comment-strip (`std::ceil`,
`1000.0`, `::`) — v1 would have returned OK because the word `double` lives only
in a comment.

## What is not claimed

- LIN replacing Bitcoin Core / bitcoind / any wallet
- A consensus bug (GetFee is policy)
- Dollar or TVL savings
- Negative fee-rate Core behaviour (LIN returns -1)
