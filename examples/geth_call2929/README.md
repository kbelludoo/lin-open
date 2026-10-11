# Geth CALL / EIP-2929 — LIN clone (results)

Experimental i64-scale LIN clone of [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` `gasCallEIP2929` (`core/vm/operations_acl.go` + `gasCall` + EIP-150 `callGas`, LGPL-3.0).

- **Clone-lin (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-geth-call2929
- **LIN kernel in lin-open:** [`src/lin_geth_call2929.lin`](../../src/lin_geth_call2929.lin)
- **Event receipt:** [`docs/events/EVENT_GETH_CALL2929_CLONE_LIN.rulel`](../../docs/events/EVENT_GETH_CALL2929_CLONE_LIN.rulel)
- **Re-run proofs:** `make geth-call2929-proof` / `python3 test/prove_geth_call2929_external.py`

This is **not** a Geth node and does **not** claim Ethereum consensus, quadratic `memoryGasCost` (Cmem), `CallStipend` 2300, DELEGATECALL/STATICCALL, or EIP-7702 delegation.

Canonical goldens (dynamic = extras + EIP-150 forwarded + 2500 if cold was charged first; jump-table `constantGas` is 100 extra):

- avail=64000 req=1e6 warm = **63000** dynamic / **63100** opcode total (63/64 binds)
- avail=64000 req=1e6 cold = **63040** / **63140** — Berlin delta **40**, not 2500
- child forwarded warm **63000** vs cold **60540** (cold child gets 2460 less)
- avail=64000 req=1000 warm = **1000** / **1100** (requested binds)
- avail=64000 req=1000 cold = **3500** / **3600** — Berlin delta **2500**
- value transfer req=0 warm = **9000** / **9100**; cold = **11500** / **11600**
- value+new-account 63/64: warm **98969** / cold **99008** (delta **39**)
- new_acct without value adds **0**; available=2499 cold fail-closes to **0**
