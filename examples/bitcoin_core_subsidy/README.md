# Bitcoin Core GetBlockSubsidy — LIN clone (results + proofs)

Monetary kernel: Bitcoin's issuance schedule (`GetBlockSubsidy`) from
[bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) **v27.1** (MIT),
cloned to deterministic LIN and checked with Compiler 0 (`lin_c0`, C11).

- **Clone-lin copy (full LIN kernel + oracle):** https://github.com/kbelludoo/clone-lin-bitcoin-core-subsidy
- **LIN kernel in lin-open (needed to re-run proofs):** [`src/lin_bitcoin_core_subsidy.lin`](../../src/lin_bitcoin_core_subsidy.lin)
- **Upstream:** `src/validation.cpp` `GetBlockSubsidy` + `src/consensus/amount.h` @ commit `1088a98f5aad080cc6cca2da174f206509fcda6c`
- **Cross-oracle:** [btcsuite/btcd](https://github.com/btcsuite/btcd) `CalcBlockSubsidy` @ v0.24.2 (ISC)
- **Pinned fixtures:** `test/fixtures/external_proof/bitcoin_core_v27_1_amount.h`, `bitcoin_core_v27_1_getblocksubsidy.cpp`
- **C11 oracle:** `test/oracles/bitcoin_core_subsidy_c11.c`
- **Harness:** `python3 test/prove_bitcoin_core_subsidy_external.py`
- **Event receipt:** `docs/events/EVENT_BITCOIN_CORE_SUBSIDY_CLONE_LIN.rulel`

## What is claimed (EXPERIMENTAL)

Bit-exact mainnet subsidy for `height >= 0` against Bitcoin Core's formula
(`50 * COIN >> (height / 210000)`, zero after 64 halvings) plus the 64-era
sum **2099999997690000** sats, which is **strictly below** `MAX_MONEY`
(21000000 * COIN). That gap is documented in Core `amount.h`; LIN checks it.

Real deltas versus Core/btcd:

1. `Consensus::Params&` becomes explicit `interval` and `genesis` arguments
   (the C transpiler fail-closes the original C++ signature as `REJ_C_CXX` /
   `REJ_C_POINTER`).
2. `height < 0` fail-closes to 0. Core and btcd: `(-1)/210000 == 0` so they
   still return 50 BTC.
3. `interval <= 0` fail-closes to 0. Core: division by zero is UB. btcd:
   `SubsidyReductionInterval == 0` returns 50 BTC.

## What is not claimed

- LIN is a Bitcoin node, wallet, or consensus replacement
- Price, TVL, or "LIN saves Bitcoin" figures
- General speed versus `bitcoind` / gcc
- Computational soundness of Merkle receipts (tamper-evidence only)
- That `lin_c0 vm` executes the string-literal C transpiler module

Machine-written evidence: `bitcoin_core_subsidy_evidence.json` (do not hand-edit).
