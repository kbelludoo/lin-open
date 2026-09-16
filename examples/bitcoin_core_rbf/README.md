# Bitcoin Core PaysForRBF — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Bitcoin Core
v27.1 BIP-125 incremental-relay / replace-by-fee bandwidth payment.

- **Upstream:** [bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) tag `v27.1` `PaysForRBF` (MIT)
- **Cross-oracle:** [btcsuite/btcd](https://github.com/btcsuite/btcd) tag `v0.24.2` `calcMinRequiredTxRelayFee` (ISC)
- **LIN clone (this tree):** [`src/lin_bitcoin_core_rbf.lin`](../../src/lin_bitcoin_core_rbf.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-bitcoin-core-rbf
- **Pinned fixtures:** `test/fixtures/external_proof/bitcoin_v27_1_rbf.cpp` (+ rbf.h, policy.h, feerate.cpp, amount.h, btcd policy.go)
- **C11 oracle:** `test/oracles/bitcoin_core_rbf_c11.c`
- **Harness:** `python3 test/prove_bitcoin_core_rbf_external.py`
- **Event receipt:** `docs/events/EVENT_BITCOIN_CORE_RBF_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of BIP-125 rules 3 and 4:

1. Replacement total fees must be at least original total fees (rule 3).
2. Additional fees must pay for replacement vsize at the incremental relay
   feerate (rule 4). Default: `DEFAULT_INCREMENTAL_RELAY_FEE = 1000` sat/kvB.

Canonical wallet-scale vector (P2WPKH-class 141 vB, 1 sat/vB incremental):

| original | replacement | extra | result |
|---|---|---|---|
| 2000 sat | 2140 sat | 140 | **REJECT** |
| 2000 sat | 2141 sat | 141 | **ACCEPT** |

btcd's `calcMinRequiredTxRelayFee` truncates then, on a zero quotient,
substitutes the **full rate**. At 3 sat/kvB × 2 bytes: Core/LIN integer-ceil
needs 1 sat; btcd needs 3 sat. That is a policy difference, not a consensus
fork.

## What is not claimed

- LIN replacing Bitcoin Core, btcd, or any wallet
- A consensus bug (this is mempool policy)
- IEEE `std::ceil` vs integer-ceil disagreement on wallet-scale rates
  (the C11 selftest requires they **agree** on 0..4000 sat/kvB × 0..400 vB)
- Dollar/TVL savings, or superiority vs gcc/LLVM

Machine-written evidence for a given run is in `bitcoin_core_rbf_evidence.json`
(produced by the harness; do not hand-edit).
