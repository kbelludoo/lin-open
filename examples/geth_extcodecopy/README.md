# Geth EXTCODECOPY / EIP-2929 — LIN clone (results)

Experimental i64-scale LIN clone of [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` `gasExtCodeCopyEIP2929` (`core/vm/operations_acl.go`, LGPL-3.0).

- **Clone-lin (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-geth-extcodecopy
- **LIN kernel in lin-open:** [`src/lin_geth_extcodecopy.lin`](../../src/lin_geth_extcodecopy.lin)
- **Event receipt:** [`docs/events/EVENT_GETH_EXTCODECOPY_CLONE_LIN.rulel`](../../docs/events/EVENT_GETH_EXTCODECOPY_CLONE_LIN.rulel)
- **Re-run proofs:** `make geth-extcodecopy-proof` / `python3 test/prove_geth_extcodecopy_external.py`

This is **not** a Geth node and does **not** claim Ethereum consensus, quadratic `memoryGasCost` (Cmem), or EIP-4762 Verkle pricing.

Canonical goldens (dynamic gas = `CopyGas * ceil32(size)` + 2500 if cold; jump-table `constantGas` is 100 extra):

- size=0 warm = **0** dynamic / **100** opcode total
- size=0 cold = **2500** dynamic / **2600** opcode total
- size=1 warm = **3** / **103**
- size=1 cold = **2503** / **2603**
- size=33 warm = **6** / **106**
- size=33 cold = **2506** / **2606**
- size=1024 warm = **96** / **196**
- size=1024 cold = **2596** / **2696**
- Berlin delta (cold-warm) is **2500** at every in-range size
- negative size or `is_cold` outside `{0,1}` fail-close to **0**
