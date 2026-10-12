# Aave V3 compounded interest — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`MathUtils.calculateCompoundedInterest` / `calculateLinearInterest`.
The LIN clone lives in lin-open as `src/lin_aave_compound.lin`. A standalone
copy is published at **https://github.com/kbelludoo/clone-lin-aave-compound**.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) tag `v1.19.4` commit `b74526a7bc67a3a117a1963fc871b3eb8cea8435` `contracts/protocol/libraries/math/MathUtils.sol`
- **License:** MIT (BUSL-1.1 Change Date 2023-01-27 elapsed). Did **not** pin `aave-dao/aave-v3-origin` (Change Date 2027-03-06 still future).
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-compound
- **LIN clone (this tree):** [`src/lin_aave_compound.lin`](../../src/lin_aave_compound.lin)
- **Pinned fixture:** `test/fixtures/external_proof/MathUtils.sol` sha256 `7f73c927e9801debfe0666e2a6364b92f62fd2d58d0c4b485ff04765fd4dc58d` blob `9adca939db36cbe1009d0a00600def9314fc7332`
- **C11 oracle:** `test/oracles/aave_compound_c11.c`
- **Harness:** `python3 test/prove_aave_compound_external.py`
- **Event receipt:** `docs/events/EVENT_AAVE_COMPOUND_CLONE_LIN.rulel`

## Formula (class: EXPERIMENTAL wad-scale)

Aave (ray, not claimed here):

`(1+x)^n ≈ 1 + n x + n(n-1)/2 x^2 + n(n-1)(n-2)/6 x^3` with `x = rate / SECONDS_PER_YEAR`, `n = dt`.

LIN clone uses **WAD=1e18** (RAY=1e27 exceeds signed i64) and 128-bit floor muldiv.
`SECONDS_PER_YEAR = 365 days = 31536000`. `block.timestamp` is an argument `dt`.

## Named commercial contrasts (not a TVL claim)

At 5% APY (`rate=5e16` wad) for 1 year (`dt=31536000`):

| path | interest index |
| --- | ---: |
| linear (`1 + n x`) | **1050000000000000000** |
| Aave binomial, 128-bit wad | **1051270833291714231** |
| naive wad `rate*rate/WAD/(YEAR^2)` floor | **1050994519264464000** |

Binomial minus linear = **1270833291714231** (~12.7 bps of principal / year at 5%).
YEAR^2-floor vs wide = **276314027250231** of hidden second-term.

At 100% APY and `dt=2` seconds, e^x Horner (`n^2/2`) = **1000000063419585978** vs Aave binomial (`n(n-1)/2`) = **1000000063419584972**.

Naive uint64 `(rate * YEAR) / YEAR` wraps to **292049323152** instead of **50000000000000000**.

## What is not claimed

- Solidity **uint256** / **ray** / mainnet **Pool** / **aToken** parity
- LIN replacing Aave, Compound, or the EVM
- General superiority vs solc/LLVM
- A port of `aave-dao/aave-v3-origin` (still BUSL)

Machine-written evidence for a given run is in `aave_compound_evidence.json`
(produced by the harness; do not hand-edit).
