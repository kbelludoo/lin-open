# Compound JumpRateModel V2 — LIN clone (experimental uint64)

Results and proofs for a **uint64-scale** clone of Compound v2 JumpRate.
This is **not** mainnet uint256 / cToken parity.

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/BaseJumpRateModelV2.sol` (BSD-3-Clause), commit `a3214f67b73310d547e00fc578e8355911c9d376`
- **LIN clone (hand-written):** [`src/lin_compound_jumprate.lin`](../../src/lin_compound_jumprate.lin)
- **Pinned fixture:** `test/fixtures/external_proof/BaseJumpRateModelV2.sol`
- **C11 oracle:** `test/oracles/compound_jumprate_c11.c`
- **Python third oracle:** `test/oracles/compound_jumprate_py.py`
- **Harness:** `python3 test/prove_compound_jumprate_external.py`
- **Independent re-proof:** `python3 test/prove_melhorias_independent.py`

`getBorrowRateInternal` is Solidity `internal view` (storage). `sol_from_sol` only emits eligible `pure` functions, so this IRM clone is **not** a transpiler dump.

## What improved (this profile)

1. IRM parameters that Solidity reads from storage are **explicit arguments**.
2. `(a*b)/d` uses a **128-bit product**. Naive signed-i64 `1e18*1e18` wraps; `(1e18*1e18)/2e18 = 5e17` here.
3. A quotient that does not fit uint64 **fail-closes to 0** (no silent low-64 truncation).

## Documented differences vs Solidity 0.8 uint256

- `cash + borrows < reserves`: Solidity reverts; LIN/C11 return `0`.
- `blocksPerYear * kink` overflows uint64; LIN uses the floor-identical reorder `(mult * BASE / kink) / blocks`.
- Operand width is uint64, not uint256.

## What is not claimed

- Mainnet uint256 / cToken parity
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM (a SipHash ~20.8× figure elsewhere is compile-turnaround on one host)
- Merkle computational soundness (C4 is tamper-evidence + SHA-256 reexecution, not zk)
- That a first C4 FAIL meant false math — it was a missing `lin_c_receipt` binary until `make -C transpile/c all`

Machine-written evidence is in `compound_jumprate_evidence.json` and `independent_reproof.json` (harness output; do not hand-edit).
