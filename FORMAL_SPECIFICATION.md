# LIN Formal Specification (human-readable extraction)

> Source of truth for executable/formal artifacts in this repository:
> `docs/LINVM_ISA_V1.rulel`, `docs/LINBC1_FORMAT.rulel`,
> `docs/LIN_VERIFIABLE_SPEC_v1.0.rulel`, `docs/HOST_ABI_1.rulel`.
> This file is the cross-reference used by the grant proposal; it does not
> replace the machine-readable `.rulel` artifacts.

Status: **EXPERIMENTAL / not frozen**. The C11 Compiler-0 host
(`transpile/c/bin/lin_c0`) is an audited subset of LINVM-1 that rejects integer
division and shifts with explicit `VM_REJ_*` codes. The repository publishes
this limitation rather than pretending it can execute every LIN module.

---

## 1. Concrete grammar (EBNF sketch)

```
source      = "@LIN:MODULE:2.0.0" annotation* function+ export? ;
annotation  = "@" IDENT "{" (IDENT ("=" (string | int | array)))* "}" ;
function    = "!" IDENT "(" param_list ")" "->" "int" "{" stmt* return_stmt "}" ;
param_list  = (IDENT ":" "int")* ;
stmt        = assignment | conditional | return_stmt ;
assignment  = IDENT "=" expr ";" ;
conditional = "?" "(" expr ")" "{" stmt* "}" (":" "{" stmt* "}")? ;
return_stmt = "^" expr ";" ;
expr        = xor_expr ( "|" xor_expr )* ;
xor_expr    = and_expr ( "^" and_expr )* ;
and_expr    = eq_expr ( "&" eq_expr )* ;
eq_expr     = rel_expr ( ("==" | "!=") rel_expr )* ;
rel_expr    = add_expr ( ("<" | ">" | "<=" | ">=") add_expr )* ;
add_expr    = mul_expr ( ("+" | "-") mul_expr )* ;
mul_expr    = unary_expr ( ("*" | "/" | "%") unary_expr )* ;
unary_expr  = ("-" | "!" | "~")? primary_expr ;
primary_expr= INT | IDENT | "(" expr ")" ;
export      = "=ex{" IDENT ("," IDENT)* "}" ;
```

This sketch matches the parser in the Stage-0 compiler and the C11 front-end.
Operators are scalar `i64`; `* + -` use wrapping arithmetic; `/ %` truncate
toward zero and are fail-closed/undefined in the C0 host today.

## 2. State machine

A LinVM run is a stack machine:

```
state = (pc, stack[256], sp, locals[64], pool[8][256], pool_len[8], steps)
```

- `steps` is a single monotonic counter across the whole call tree.
- every instruction increments `steps` before execution;
- `steps > 200_000_000` → `VmStepLimit`;
- call depth > 192 → `VmDepth`;
- `ret` returns `stack[sp-1]` without popping, so `sp_at_ret` is observable.

## 3. Memory model

- function-visible memory is statically sized;
- no `malloc`, no heap, no pointer indirection beyond fixed array indices;
- array literals use a flat pool of up to `8 x 256` i64 cells in LINVM-1;
- LINBC1 images declare their memory budget in the header and reject an image
  that exceeds the host profile before executing a single instruction.

## 4. Receipt / provenance scheme

Canonical receipt domains (from `docs/LIN_VERIFIABLE_SPEC_v1.0.rulel` and the
N-Version cross-check):

```
leaf_source = SHA256("lin:xver:source:" || source)
leaf_env    = SHA256("lin:xver:env:"    || env_spec)
leaf_code   = SHA256("lin:xver:code:"   || bytecode_image)
leaf_exec   = SHA256("lin:xver:exec:"   || result ":" steps ":" sp_at_ret)
node(a,b)   = SHA256("node:" || a || b)
root        = node(node(leaf_source, leaf_env), node(leaf_code, leaf_exec))
```

The verifier computes the root from public fields with `hashlib` and does not
invoke the producer compiler, so a tampered result is rejected with the same
canonical digest.

## 5. Known non-goals / current limits

- The C0 host does **not** implement `/`, `%`, `<<`, `>>`, `>>>`.
- There is **no** general I/O, OS, database, or blockchain consensus layer.
- The project is a verifiable computation kernel, not a replacement for LLVM,
  Rust, C, or a general-purpose language.
