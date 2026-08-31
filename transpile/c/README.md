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
