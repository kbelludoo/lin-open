# LIN u512 numeric coprocessor (EXPERIMENTAL)

LIN as a **numeric coprocessor with an auditable receipt**, not as a Uniswap replacement.

`mulDiv(a,b,d) = floor((a*b)/d)` for `a,b,d < 2^256`. The product `a*b` is a 512-bit intermediate. Without that width, a uint256 engine fail-closes (`-2`) or lies. This module proves the intermediate:

| Obligation | What is checked |
|---|---|
| mul 256×256→512 | schoolbook 16-bit limbs, carry out of each limb |
| ge 512 | unsigned compare of 32 limbs (division loop) |
| div 512/256→256 | restoring division; `q*d + r == n` and `r < d` |
| guards | `-1` if `d=0`, `-2` if `q >= 2^256` |
| oracles | Python `int`, C11 16-bit limbs, C11 64-bit `__int128` |
| receipt | LNR1 240-byte records, domains `LIN:U512:LEAF:1` / `LIN:U512:NODE:1` |

Class: **EXPERIMENTAL** — FullMath *width*, not the CRT/`mulmod` assembly in pinned `FullMath.sol`, not a deployed pool.

## Reproduce

```bash
make u512-coprocessor-proof
python3 examples/u512_coprocessor/verify_u512_receipt.py \
  examples/u512_coprocessor/u512_coprocessor_evidence.json --self-test
```

The verifier uses only Python stdlib (`hashlib`, `json`, `struct`). It does not run LIN. Tampering with `q` must be rejected.

## What this does not close

- End-to-end `settle_u256_word` on the full 2000/157 campaign (a 1+1 EXACT/OVERPAID slice with real LCR2 steps is included)
- Replacing the SafeMath-width u256 settler body (phantom `ain=1,rin=1,rout=ceil(2^256/997)` still returns `-2` there; the coprocessor APPROVES)
- Computational soundness / zk — LNR1 is tamper-evidence plus independent identity
