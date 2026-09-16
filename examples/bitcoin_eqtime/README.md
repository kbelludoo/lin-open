# Bitcoin Core GetBlockProofEquivalentTime — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Bitcoin Core
`GetBlockProofEquivalentTime`. The LIN copy lives in a separate repository.

- **Upstream:** [bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) `v27.1` `src/chain.cpp` (MIT)
- **Clone-lin (LIN copy):** https://github.com/kbelludoo/clone-lin-bitcoin-core-eqtime
- **LIN clone in this tree (for the proof harness):** [`src/lin_bitcoin_eqtime.lin`](../../src/lin_bitcoin_eqtime.lin)
- **Pinned fixtures:** `test/fixtures/external_proof/bitcoin_v27_1_chain.cpp`, `bitcoin_v27_1_pow_tests.cpp`
- **C11 oracle:** `test/oracles/bitcoin_eqtime_c11.c`
- **Harness:** `python3 test/prove_bitcoin_eqtime_external.py` or `make bitcoin-eqtime-proof`
- **Event receipt:** `docs/events/EVENT_BITCOIN_EQTIME_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Core's formula

`sign(to.nChainWork - from.nChainWork) * min(int64_max, |Δwork| * nPowTargetSpacing / GetBlockProof(tip))`

against the published `GetBlockProofEquivalentTime_test` identity: with constant
`nBits = 0x207fffff` (GetBlockProof = 2) and `nPowTargetSpacing = 600`,

`eqtime(h1, h2) == (h1 - h2) * 600`.

This run: **19 PASS / 0 FAIL / 2 SKIP** (SKIP = `lin_c0` string-literal VM reject on the
C++ fail-closed numeric gate; libtcc JIT absent). Python bigint, C11 `__int128`,
portable limbs, and Compiler 0 `vm` agree on 11 vectors plus 84 Core-test identities.

Real deltas versus the C++ original:

1. `CBlockIndex&` / `Consensus::Params&` become explicit `to_work`, `from_work`,
   `tip_proof`, `spacing` arguments (no hidden header fields).
2. `tip_proof == 0` fail-closes to 0 (Core would divide `arith_uint256` by
   `GetBlockProof == 0`).
3. `(Δwork * spacing) / proof` uses a 128-bit product. Naive signed i64
   `(1e18 * 10) / 100` wraps; the clone matches Python bigint.

## What is not claimed

- **uint256** `nChainWork` / a Bitcoin node / `CheckProofOfWork` / SHA256d
- LIN replacing Bitcoin Core
- General superiority vs GCC/LLVM
- Computational soundness of Merkle / zk
- That `cfs_from_c` string-emit or `cfs_rej_eqtime` executes on `lin_c0 vm`
  (`VM_REJ_STRING_LITERAL`; the module typechecks)

Machine-written evidence: `bitcoin_eqtime_evidence.json` (produced by the harness).
