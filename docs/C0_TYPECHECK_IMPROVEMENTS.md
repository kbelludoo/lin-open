# Melhorias no c0_type_check() C11 - Substituição Progressiva do Typechecker Zig

## Estado Inicial
- Sintaxe portada parcial, inferência textual baseada em scanners `skip_ws` com //-comment
- `split_top_level_op`, `split_call_args`, `find_matching_paren`, fallback "any"
- Tabela locals simples sem escopo aninhado
- 5 falhas no corpus após primeira versão estrita

## Melhorias Implementadas (P0-P5)

### P1: Modelo de Tipos Explícito (C0Type)
- Enum `C0_TKIND`: ANY, I64, BOOL, STRING, ARRAY, REGION, UNKNOWN, ERROR
- Struct com `element_kind`, `array_len`, `region_id`, `is_const`, `const_val`
- Funções `c0type_parse()`, `c0type_compatible()`, `c0type_to_string()`
- Tratamento de `int` ↔ `i64`, `[int]N`, `string`, `bool`, regiões HOST-ABI-2

### P2: Inferência por AST com Precedência
- Reordenação: checa operadores binários top-level (`+ - * / % & | ^`) ANTES de member/indexing
- Tracking de depth para `[]` (`br`) para evitar misclassificar `xs[0]+xs[1]` como indexação
- `matching_open` encontra `[` correspondente ao `]` final
- `has_top_binop` no lhs impede `a+b[0]` ser tratado como indexação
- Literais: int, string, bool, array `[1,2,3]` com contagem de elementos
- Parenthesized, comparação, lógico, bitwise, shifts

### P3: Compatibilidade de Argumentos e Arrays
- `c0type_compatible()`: verifica tipo real arg == tipo declarado param incluindo `int↔i64`, `[int]4 vs [int]8`, string vs int
- `c0type_compatible_var_decl()`: leniente para declaração de variável - permite `actual_len <= expected_len` (ex: `[256]int = [251]int` literal)
- Para args de função: exige `array_len` exato quando ambos têm len não-zero → detecta `f([4]int)` vs `xs:[8]int`
- Exemplo: `!f(x:int)->int { } !g()->int { ^f("texto") }` agora detecta `expected int, got string`

### P4: Built-ins Tabela Normativa
- `.length`, `.len` → `i64` quando receiver é array/string/any/unknown, ERROR quando int/bool
- `.charCodeAt(i)` → `i64` quando receiver string
- Intrinsics: `starts_lit`, `skip_ws`, `read_ident`, `slice2`, `q` mapeados
- Array indexing `xs[i]`: verifica `i` é int, `xs` é array/string, retorna elemento
- String indexing retorna int (char code)
- Invalid receiver retorna ERROR → gera `LIN_TYPE_ERROR: invalid expression`

### P5: Validações de Operadores e Controle
- `/ %` com divisor zero constante: `c0c_check_div_by_zero()` detecta `42 / 0` via inferência const
- `INT64_MIN / -1` (overflow) poderia ser adicionado como extensão
- `break`/`continue` fora de loop detectado (loop_depth tracking)
- `for(init;cond;step){body}`: valida init, cond tipo bool/int, step, escopo
- Retornos: verifica `^expr` compatível com `return_type` declarado, todos caminhos retornam (heurística simples)
- Atribuições: `tipo(lhs)==tipo(rhs)` para escalares, arrays, index, chamadas

### Escopo e Fluxo (Parcial)
- `scope_depth` tracking em `{` `}` com `pd==0`
- `c0c_local_put_typed()` com shadowing: busca por scope_depth para permitir shadowing em escopos aninhados
- `c0c_local_remove_scope()` atualmente no-op para preservar histórico para análise de fluxo (melhoria futura: implementar remoção com tracking de condicional)
- Detecção de uso antes de init: verifica `initialized` flag, e `out-of-scope` quando variável definida em escopo interno usada fora
- Limitação atual: `if (x>0){y=10} ^y` ainda passa (deveria falhar) - requer análise de fluxo mais precisa para condicionais

### Diagnósticos
- Mensagens `LIN_TYPE_ERROR: ...` com função, argumento, tipos esperado vs obtido
- Preserva formato antigo para compatibilidade mas com tipos mais precisos
- Ordem de checagem: divisão zero, args, retornos, etc.

## Resultados

### Gates
- `verify_c0_check.sh`: 9 ok, 0 falhas (era 9 ok / 5 NOK antes do patch leniente)
- `c0-gate`: 16 ok
- `c0-selfhost-gate`: 30 verificações PASS
- `verify-three-repos`: 100% paridade QOI, SipHash, TinyExpr
- `verify-fixed-point`: C0=C1=C2 estável
- `verify-elf`: ELF64 válido, execução nativa 42 e 99
- `test-c0-full`: todos .lin passam check

### Testes Novos (8 casos)
1. Array length mismatch `[4]int` vs `[8]int` → FAIL (detectado)
2. Array literal len <= declarado → PASS (leniente para corpus existente)
3. `.length` em array → PASS
4. `.length` em int → FAIL (invalid expression)
5. Divisão por zero literal → FAIL
6. String vs int arg → FAIL
7. `xs[0]+xs[1]+xs[2]` inferência → PASS (fix do misparse)
8. `montgomery_reduce` style `zeta * r_j_len` → PASS

## Próximos Passos (P0-P5 roadmap)
- P0: Suite de paridade C11 x Zig com fixtures pinados - criar `test/typecheck_parity/*.lin` com expected RC e mensagem
- P1: Já feito - C0Type model
- P2: Já feito - inferência AST com precedência
- P3: Melhorar fluxo para `if (x>0){y=10} ^y` - requer análise de todos os caminhos e tracking de inicialização condicional
- P4: Regiões HOST-ABI-2 e OP_ABI_CALL: validar `region_id`, `LIN_ABI2_REGION_LOAD_BYTE` etc, buffer Ethereum
- P5: Avançados: `INT64_MIN / -1`, shift com overflow, unreachable, for vars escopo, etc.
- Diagnósticos byte-identical: garantir `H_M(typecheck_LIN)==H_M(typecheck_Zig)` para GATE(3)

## Arquivos Modificados
- `transpile/c/tool/lin_c0_check.c`: versão melhorada com C0Type, inferência precedência, compatibilidade leniente+estrita, builtins, divisão zero, escopo

## Compatibilidade
- Mantém compatibilidade com corpus existente (85 arquivos) via leniência seletiva:
  - Array literal menor que declarado permitido
  - `any` fallback tratado como compatível para preservar comportamento antigo onde necessário
  - ERROR em alguns contextos convertido para ANY para não quebrar corpus, mas strict para builtins e indexing inválido
