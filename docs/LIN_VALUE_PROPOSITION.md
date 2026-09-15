# LIN value proposition — auditable scalar coprocessor + receipts

> **LIN não executa seu sistema. Prova um kernel numérico pequeno com receipt stdlib + disputa otimista.**
>
> LIN does not run your system. It proves a small numeric kernel with a stdlib receipt and an optimistic dispute.

This is the one-page grant positioning document. Pinned numbers below are copied from measured artifacts (`docs/GRANT_EVIDENCE_2026_09.rulel`, `docs/GRANT_ADDENDUM_ERRATA_2026_09.md`). They are not estimates.

## What LIN is

An **auditable scalar coprocessor**: a heap-free numeric kernel (`LinVM`) that binds a small function — typically Uniswap V2 `getAmountOut` on emulated `uint256` limbs — to a 208-byte LCR2 SHA-256 Merkle receipt. Anyone with Python 3 or a browser (WebCrypto) recomputes the root. On-chain settlement is an **optimistic dispute** window (`contracts/LinReceiptVerifier.sol`), not a zk validity proof.

## What LIN is not

LIN does not execute your application, replace C/Rust/Python, transpile general Solidity, run OpenSSL, or provide computational soundness. The canonical denial table lives in `README.md` §2 and is a CI gate (`test/gate_forbidden_overclaims.py`).

`src/lin_from_solidity.lin` (`sol_from_sol`) is a **pure-math subset**: eligible `pure`/`view` scalar functions, fail-closed with explicit `REJ_*` codes. It is not a Solidity compiler.

## Right rivals (never vs Rust/C)

| Auditor job today | LIN coprocessor |
|---|---|
| Ad-hoc **Python/JS + RPC** script | **LCR2 receipt** + independent `hashlib` / WebCrypto verify |
| **zkVM** (RISC Zero, SP1) expensive prover | **Optimistic** and cheap: near-native/GPU execute, SHA-256 anchor |
| **L1 EVM re-execution** of every swap | **Batch Merkle root** anchored once, spot-check dispute |

## Pinned measured numbers

| Metric | Pinned value | Reproduce | Honesty note |
|---|---|---|---|
| LCR2 record | **208 B** | `tools/emit_batch_receipt.py` | Canonical leaf |
| Batch verify | **2000/2000 + 157/157**, ~0.1 s | `make audit` / `make verify-batch-receipt` | Python stdlib; **`steps_bound=false`** (steps field is 0) |
| Receipt verify (block B=4) | **5.29 µs** vs re-exec **26.372 ms** (~4986×) | `python3 benchmarks/audit_cost_benchmark.py` | Audit cost, not compiler speed |
| Anvil anchor | **70,133 gas** `settleBatch` (fresh root) | `make verify-forge-gas` | Foundry/Anvil, **not Mainnet** |
| Anvil + inclusion | **87,831 gas** | same | Foundry/Anvil |
| Cost / swap | **$0.00210** @ 20 gwei, $3k ETH, ÷2000 | `docs/GRANT_ADDENDUM_ERRATA_2026_09.md` | Amortized batch |
| vs Groth16 | ~**3.56×** cheaper gas/swap (~35.1 vs ~125) | README §2 | Optimistic soundness, **not zk** |
| vs L1 re-exec | 13,258×–16,604× | same | **CONDITIONAL BASELINE**, not a general proof |
| TCB (execution runtime) | **809 LOC** C11 | `transpile/c/lin_c/{lin_vm,lin_linbc1,lin_sha256,lin_common}.c` | Host compiler/OS/GPU driver sit outside |
| i64 toy `get_amount_out(10000,50000,100000)` | value **16624**, **36 steps** | `src/lin_uniswap_v2_library.lin` | **TOY** — overflows Mainnet 18-decimal reserves |
| u256 limb engine | canonical engine | `examples/defi_settlement_proof/u256_settlement_engine.lin` | Emulated 16×16-bit limbs; see `make swap-steps` |

Independent verify without trusting the author: `python3 lin_verify.py receipt benchmarks/fixtures/receipt_sqr9.json` and `benchmarks/verify_receipt.html`.

## One auditor command (no Zig)

```bash
make -C transpile/c all          # cc only
make audit                       # dataset.json -> root + manifest + verify
# or:
python3 tools/lin_auditor.py \
  --dataset test/pilot_harness/mainnet_real_swaps_2000.json \
  --out-dir /tmp/lin-audit
```

Requires `cc` + Python 3. Zig is not used.
