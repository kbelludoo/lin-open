# Transpilação LIN (Zig) → C — Slice 1: Parser Pratt + Arena + LinVM

> **O que é isto:** um port *educacional e verificável* da pipeline de
> expressões C do compiler do LIN — tokenizer → parser Pratt → arena flat de
> AST → avaliação → lowerer de bytecode → interprete LinVM — do Zig
> (`compiler/lin.zig`) para C11.
>
> **O oráculo:** os 29 vetores de teste da suite original
> (`REAL STAGE-0 C EXPRESSION PARSER & FLAT AST ARENA TEST SUITE`,
> `lin.zig:14646`), copiados **verbatim**, com o mesmo ambiente
> `{x=10, y=20, z=5, x1=15}` e o mesmo formato de saída — o stdout do port é
> diretamente *diff-ável* contra o bloco correspondente de `lin test`.
>
> **Resultado:** `29/29 PASSED` (byte-exact, incluindo `Insts` por vetor) +
> `17/17` vetores de borda (semântica de wrapping do Zig em limites de INT64).

```
$ make test        # suite verbatim: 29/29
$ make test-edges  # sondas de overflow: 17/17
```

## Por que este slice é um bom alvo de transpilação

1. **É autossuficiente**: a pipeline expression tem fronteiras limpas
   (string in → número out) e não depende do restante dos 16.894 linhas.
2. **É verificável de verdade**: 29 vetores com valores esperados, três estágios
   de rejeição (parse / eval / VM) e contagem de instruções — um oráculo rico.
3. **Força decisões semânticas reais**: é um compilador numérico, então
   *overflow, divisão truncada e remainder* são parte do contrato, não detalhe.

## Mapa de conceitos Zig → C

| Zig | C | Decisão |
|---|---|---|
| `[]const u8` (slice) | `LinStr { p, len }` | mantém aliasing com o buffer de entrada (o `name` dos nós aponta para a fonte, igual ao Zig) |
| `error.Set` / `ParseError!u16` | `enum LinErr` + out-param | `fn f() E!T` → `LinErr f(..., T *out)`; `try x` → `LinErr e = x(); if (e) return e;` |
| `?i64` (opcional) | `int flag + valor` | `tc.expected` vira `expected + has_expected` |
| `[%d]AstTag` (array fixo) | `AstTag tags[256]` | idêntico — a arena já é zerada de heap, o port permanece **zero-alloc** |
| `ArrayList(VmIns)` (heap) | `VmIns code[512]` | limite documentado: ≤1 instrução por nó (256) + 1 `ret` |
| `std.mem.eql(u8, a, b)` | `lin_str_eq_cstr` | comparação byte a byte com length |
| `@intCast(i)` | cast C | os valores neste slice sempre estão em range (índices, operandos não-negativos) |
| `{d: >2}`, `{s: <24}` (printf Zig) | `%2d`, `%-24s` | formato reproduzido byte a byte para o diff |

## As decisões semânticas (o coração do exercício)

### 1. Aritmética com wrapping — o caso central

Zig tem **aritmética de inteiro definida com wrapping** (`+%`, `-%`, `*%`).
C tem *undefined behavior* em overflow de inteiro signed. O truque:

```c
/* C garante aritmética modular em uint64_t; bitcast de volta = idêntico ao Zig */
static inline int64_t lin_wadd(int64_t a, int64_t b) { return (int64_t)((uint64_t)a + (uint64_t)b); }
```

### 2. Divisão e remainder: iguais por sorte da C99, exceto em 2 casos

`@divTrunc` e `@rem` do Zig têm a mesma semântica da `/` e `%` da C99
(truncam para zero). **Mas**:

| Expressão | Zig | C (naive) |
|---|---|---|
| `INT64_MIN / -1` | `INT64_MIN` (wrapping) | **UB** |
| `INT64_MIN % -1` | `0` | **UB** |
| `0 - INT64_MIN` | `INT64_MIN` (wrapping) | **UB** |

O port resolve com special cases explícitos (`lin_wdiv`, `lin_wrem`, `lin_wsub(0,x)`).

**Nuance descoberta durante o teste:** no gcc x86-64, o código *naive*
acidentalmente produz os mesmos bits (a divisão do hardware faz wrap).
Ou seja: um port bobo *passaria* os testes nesta plataforma — e quebraria em
outras, ou seria flagado pelo sanitizador. Confirmação:

```
$ gcc -O2 -fsanitize=undefined naive.c && ./a.out
runtime error: division of -9223372036854775808 by -1 cannot be represented in type 'long long int'
runtime error: negation of -9223372036854775808 cannot be represented in type 'long long int'
```

Lição: **"passa no gcc x86-64" ≠ "portável"**. Os 17 vetores de borda
(`test_overflow_edges.c`) existem para que o contrato seja *definido*, não
acidental.

### 3. Literais inteiros que estouram o range

`9223372036854775808` (1 além do `INT64_MAX`) é lido como `INT64_MIN` no Zig
(o acumulador `num*10+d` faz wrap em i64). Em C, acumular em `int64_t` seria
UB já no parse; o port acumula em `uint64_t` e bitcasteia — mesmo bit pattern.

### 4. O que ficou *idêntico* (o presente da flat arena)

- Precedência do Pratt (3: `* / %`, 2: `+ -`, 1: comparações) e
  associatividade à esquerda (`prec <= min_prec` quebra o loop).
- `1 < 2 < 3` agrupa como `(1<2) < 3` → `1` (comparações não são
  transitivas no LIN — vetorial, como C).
- `unary_pos` **não emite nada** no bytecode (`+x` compila igual a `x`).
- `call`/`call_arg` são rejeitados em eval e no lower com `UndefinedVariable`
  (parece estranho; é o que o original faz — fidelidade > elegância).
- O erro é reportado no *primeiro* estágio que o rejeita: parse → AST eval →
  lower → VM (a ordem do if/else do harness original).

### 5. `a >> b` em signed

C deixa `>>` em signed *implementation-defined*; gcc/clang x86-64 fazem shift
aritmético, que é o que o `>>` do Zig faz em i64. Aceito e documentado —
sairia do escopo exigir portabilidade exotica. (Nenhum vetor deste slice
exerce shift; relevante a partir do slice 2.)

## Como verificar (e a limitação honesta desta sandbox)

- **Aqui**: `make test` (29/29) + `make test-edges` (17/17). Os valores
  esperados foram copiados do fonte Zig; a semântica de borda foi derivada da
  referência de linguagem do Zig (aritmética wrapping, `@divTrunc`, `@rem`).
- **Limitação**: esta sandbox não tem Zig (ziglang.org bloqueado; o GitHub só
  distribui o source bootstrap para versões ≥ 0.8 — compilar o próprio Zig é
  inviável aqui). Logo, o diff byte a byte contra `lin test` *ao vivo* fica
  para a sua máquina:
  ```bash
  ./baseline_diff.sh   # builda o binário Zig, extrai o bloco da suite, roda o port e faz diff
  ```

## O que o exercício ensinou (nota de aprendizado)

1. **O bug do `<` solto**: minha primeira leitura do tokenizer só traduziu
   `<=`/`>=` (o caminho de dois caracteres) e esqueceu que no Zig o `<`
   cai num *fall-through* para o caminho de um caractere. Os vetores 13 e 14
   falharam no primeiro build — exatamente como o método prevê: *o oráculo
   encontra o que a tradução cega perde*.
2. **Fidelidade > elegância**: rejeitar `call` com `UndefinedVariable` é
   "errado" por gosto pessoal, mas é o contrato do original. Em transpilação
   educacional, desviar do contrato sem registrar é o que transforma aprendizado
   em reescrita.
3. **UB é invisível até que alguém prove**: o gcc x86-64 escondeu os três
   casos de overflow por hardware. UBSan + vetores de borda explicitaram.
   Transpilar numérico SEM sondas de limite é transpilar às cegas.
4. **A flat arena é didática**: porque o original já evita heap, o port C
   herda a mesma disciplina (arrays fixos, zero `malloc`). A escolha de
   arquitetura do autor virou lição de C grátis.

## Estrutura

```
transpile/c/
├── Makefile                  # make test / make test-edges / make clean
├── README.md                 # este arquivo
├── baseline_diff.sh          # diff byte-exact vs. `lin test` (requer zig)
├── lin_c/
│   ├── lin_common.h/.c       # LinStr, LinErr (nomes exatos p/ diff), aritmética wrapping
│   ├── lin_token.h/.c        # nextToken/peekToken (lin.zig:14309)
│   ├── lin_ast.h/.c          # arena [256] + eval (lin.zig:14204-14300)
│   ├── lin_parse.h/.c        # parser Pratt (lin.zig:14346-14522)
│   └── lin_vm.h/.c           # lowerer (lin.zig:14525) + vmExecWithSp (lin.zig:6420)
└── test/
    ├── test_c_expr.c         # 29 vetores verbatim, formato de saída idêntico
    └── test_overflow_edges.c # 17 sondas de borda INT64 (não existem no original)
```

## Próximos slices (caminho natural, em ordem de dependência)

1. **Slice 2 — Statements**: o `StmtParser` (lin.zig:14790+) com `x = 10;`,
   blocos, `if/else`, `while`, `for` desugar + os 13 vetores C1/C2. Exercita
   `store_local`, `jump*` e `pop` — os opcodes que o slice 1 não emite.
2. **Slice 3 — Funções & frames**: `call`/`ret`, recursão (`fact(6)==720`),
   os 4 vetores de frame unwinding e a disciplina `sp_at_ret == 1`.
3. **Slice 4 — Diferencial com fuzzing**: gerador de expressões aleatórias
   rodando binário Zig e port C em paralelo (differential testing), com
   `diff` dos resultados — o oráculo deixa de ser finito.
4. **Slice 5 (opcional)**: `--ai-feedback` JSON — comparar a taxonomia de
   erros (`E_SYNTAX_*`, `E_EXEC_*`) como saída estruturada, não só valor.

---

## N-Version cross-check (adicionado em 2026-08-31)

O port deixou de ser apenas um exercício de transpilação: ele é agora a **segunda
implementação independente** usada pelo verificador N-Version do LIN.

```bash
make -C transpile/c xver          # compila bin/lin_c_receipt
./zig-out/bin/lin_native crosscheck-c
# ou, da raiz:  make xver
```

`tool/lin_c_receipt.c` empurra uma expressão pela pipeline C (tokenizer → parser
Pratt → arena plana → lowerer → LinVM C) e emite um **commitment Merkle SHA-256**
do que computou. O lado Zig (`crosscheck-c` em `compiler/lin.zig`) faz o mesmo com
a sua própria implementação e compara as raízes.

### Canonicalização (idêntica nos dois lados)

```
bytecode_image = por instrução: 1 byte (ordinal do opcode) + operando i64 little-endian

leaf_source = SHA256("lin:xver:source:" || expr)
leaf_env    = SHA256("lin:xver:env:"    || env_spec)          # "x=10,y=20,z=5,x1=15"
leaf_code   = SHA256("lin:xver:code:"   || bytecode_image)
leaf_exec   = SHA256("lin:xver:exec:"   || result ":" steps ":" sp_at_ret)

root = node(node(leaf_source, leaf_env), node(leaf_code, leaf_exec))
node(l, r) = SHA256("node:" || l || r)
```

Raízes iguais significam que as duas implementações concordam sobre: a fonte, o
ambiente, **cada instrução emitida**, o resultado, a contagem de passos e a
profundidade final da pilha. Qualquer diferença é divergência e o comando falha
(`error.NVersionDivergence`, exit não-zero, sem recibo).

### Arquivos novos

| Arquivo | Papel |
|---|---|
| `lin_c/lin_sha256.{h,c}` | SHA-256 (FIPS 180-4) próprio, sem OpenSSL — a "implementação independente" não pode depender de uma terceira base de código |
| `test/test_sha256.c` | vetores **publicados** (FIPS + NIST CAVP de 1 MiB); nenhum valor esperado foi gerado pela implementação testada |
| `tool/lin_c_receipt.c` | emissor do recibo de execução do lado C |

### Resultado verificado

```
$ make xver
N-VERSION CONSENSUS: 34 vectors | agreements 34 | divergences 0
Independent implementations compared: 2 (Zig, C11)
```

Os 34 vetores são os 29 do oráculo compartilhado (23 avaliados + 6 que ambos os
lados devem rejeitar) mais 5 vetores de fronteira INT64 (`9223372036854775807+1`,
`-9223372036854775807-2`, `9223372036854775807*2`, `(0-9223372036854775807)-1`,
`x*x*x*x`) — exatamente os casos em que um port de aritmética com wrapping diverge.

O recibo (`xver_receipt.rulel`) fixa o binário C por SHA-256
(`engine_b_sha256`), para que "concordaram" seja auditável: sabe-se *qual* segunda
implementação concordou.

### Teste de injeção de falha

`test/attestation_honesty.sh` substitui a segunda implementação por um script que
mente (`result=999`, raiz falsa). O `crosscheck-c` reporta `DIVERGENCE DETECTED`,
não escreve recibo e sai não-zero — ou seja, a comparação é real, não decorativa.

---

## Compiler 0 host (`lin_c0`) — compilar e executar `.lin` sem Zig (2026-09-02)

Até esta data `transpile/c` cobria **duas** rotas: o oráculo de expressões C
(slice 1) e o loader LINBC1 (V1). Faltava a terceira — compilar fonte `.lin`.
Os gates `test/verify_c0.sh` e `test/verify_c0_selfhost.sh` já a exigiam
(`transpile/c/bin/lin_c0`, alvo `c0`), mas nem o binário nem o alvo existiam:
as duas portas saíam com `exit 2`.

```bash
make -C transpile/c c0        # ou, da raiz: make c0        (só `cc`)
make c0-gate                  # test/verify_c0.sh          → 16 ok, 0 falhas
make c0-selfhost-gate         # test/verify_c0_selfhost.sh → 30 verificações
```

| Arquivo | Papel |
|---|---|
| `lin_c0_front.h` | contrato do front-end |
| `tool/lin_c0_front.c` | **port** de `parse_fn_type_infos` (`lin.zig:5287`), `vmTokenize` (`:5678`), `VmComp` (`:5733`) e `vmBuild` (`:6296`) + emissor LINBC1 |
| `tool/lin_c0.c` | CLI `--version` / `info` / `vm` / `image` / `run` / `roundtrip` |

O interpretador **não é novo**: é o `vm_exec` deste diretório (`lin_c/lin_vm.c`),
o mesmo dos 29/29. O que é novo é o front-end — e ele é um *port*, não uma
reimplementação: mesma ordem de emissão, mesmos códigos `VM_REJ_*` e a mesma
ordem de escolha entre eles.

**Oráculo:** os goldens publicados pelo Stage0 Zig, com `value` **e** `steps`
(`vms_gate` = `1 / 8511500`; `lex_gate` = `1 / 10097`; `xver_gate` = `1 / 12445`;
`low_gate` = `1 / 4386`; `lb_selfhash_fold` = `-178321285347216732`). Todos
reproduzidos aqui sem Zig — evidência completa e limitações declaradas em
`docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel`.

Duas lições que ficaram do desenvolvimento, no espírito da seção anterior:

1. **O ASan encontrou o que os goldens não encontrariam.** A primeira arena usava
   um bloco único com `realloc`; ao crescer, ele **movia** os `VmFn*` que
   `c0_build` ainda estava preenchendo → use-after-free, visível só em módulos
   grandes (`linvm_selfhost.lin`), invisível nos módulos do front-end que
   passavam em todos os goldens. Arena de blocos encadeados resolve.
2. **Formato de registro é contrato.** O `run` imprimia `.result{ … steps=N sp=1 }`;
   o consumidor (`verify_c0_selfhost.sh`) faz `sed` esperando `steps=N }`, e o
   campo extra transformava um PASS em string vazia. `sp_at_ret` pertence ao
   registro do `roundtrip`, que é o dono daquele campo.

**Escopo honesto (R5):** subconjunto `vmBuild`; `check`/`lint` e o ponto fixo
C0=C1=C2 continuam no Stage0 Zig. TCB C11 total medido: 4103 linhas (a meta
`≤ 2500` da regra R6 era do loader V1 e precisa ser re-orçada).
