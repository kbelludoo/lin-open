# LIA — AI-Native compact code language

Língua densa para código e agentes. **Único caminho ativo de compile**: LIA → JS / TS / Python / Go / Rust.

Dicel L0 = legado/arquivo apenas; novos trabalhos **não** dependem de Dicel para emitir.

## Sigilos

| Símbolo | Significado |
|---------|-------------|
| `!f(a){…}` | function |
| `?(c){t}` | if |
| `:{e}` / `:(c){t}` | else / else if |
| `#(i;c;s){b}` | for |
| `^e` | return |
| `$K{k=v}` | const table |
| `=ex{a,b}` | exports |

## CLI

```bash
npm test
npm run test:multi
node bin/lia.mjs compile examples/safe-compare.lia --target js
node bin/lia.mjs compile examples/safe-compare.lia --target ts -o out.ts
node bin/lia.mjs compile examples/safe-compare.lia --target py
node bin/lia.mjs compile examples/safe-compare.lia --target go
node bin/lia.mjs compile examples/safe-compare.lia --target rust
```

Alias legado: `bin/ail.mjs` → mesmo CLI.

## Layout

```
spec/          # LIA_MULTI_EMIT + semantics/compiler
src/           # emitter, compiler, emit_{js,ts,py,go,rust}, multi_emit
bin/lia.mjs    # CLI canônico
examples/      # safe-compare.lia
scripts/       # golden_multi_emit.mjs
```

Repo: `C:/Users/k/Documents/lia` (ex-`ail`).

## Licença

MIT
