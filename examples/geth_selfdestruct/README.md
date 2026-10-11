# Geth SELFDESTRUCT / EIP-3529 — LIN clone (results)

Experimental i64-scale LIN clone of [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` `makeSelfdestructGasFn` (`core/vm/operations_acl.go`, LGPL-3.0).

- **Clone-lin (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-geth-selfdestruct
- **LIN kernel in lin-open:** [`src/lin_geth_selfdestruct.lin`](../../src/lin_geth_selfdestruct.lin)
- **Event receipt:** [`docs/events/EVENT_GETH_SELFDESTRUCT_CLONE_LIN.rulel`](../../docs/events/EVENT_GETH_SELFDESTRUCT_CLONE_LIN.rulel)
- **Re-run proofs:** `make geth-selfdestruct-proof` / `python3 test/prove_geth_selfdestruct_external.py`

This is **not** a Geth node and does **not** claim Ethereum consensus, EIP-6780, or the EIP-3529 1/5 refund cap.

Canonical goldens (dynamic gas only; jump-table `constantGas` is 5000 extra):

- warm existing, EIP-3529 = **0** gas + **0** refund
- warm existing, EIP-2929 first destruct = **0** gas + **24000** refund
- cold existing, EIP-3529 = **2600**
- warm empty + value = **25000** (`CreateBySelfdestructGas`)
- cold empty + value = **27600** (2600+25000)
- `gasEip2929AccountCheck` cold = **2500** (2600-100)
- flags outside `{0,1}` fail-close to **0**
