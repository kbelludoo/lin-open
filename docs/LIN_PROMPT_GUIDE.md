# LIN AI Prompting & AI-Safe Specification Guide

@RULEL:LIN_AI_GUIDE:1.4.0
~R{.p=prompt .s=syntax .e=errors .l=limits}

---

## 1. O que é o LIN para Agentes de IA

O **LIN** é uma linguagem de sistemas numéricos orientada a verificação formal e execução determinística em CPU e GPU (OpenCL).
Para um agente de IA, programar em LIN significa:
- **Zero Undefined Behavior (UB)**: Comportamento bit-exact idêntico em todas as plataformas.
- **Fail-Closed em Compilação**: Divisões por zero, variáveis não declaradas e erros de sintaxe são rejeitados imediatamente.
- **Auto-Verificação (`!self_check`)**: Todo módulo deve incluir testes internos executáveis.

---

## 2. Subconjunto Canônico `@LIN:AI_SAFE`

```text
Definição de Função:   !nome(param1: int, param2: int) -> int { ... }
Atribuição:            x = expr;
Condicional:           ?(cond) { then_block; } : { else_block; }
Laço:                  #(cond) { body_block; }
Retorno:               ^expr;
Chamada:               nome(arg1, arg2)
```

### Exemplo: Fatorial Recursivo e Verificado
```lin
@LIN:L1c:0.2
~G{.target="ai_safe_kernel"}

!fact(n: int) -> int {
  ?(n <= 1) {
    ^1;
  }
  ^n * fact(n - 1);
}

!self_check() -> int {
  err = 0;
  ?(fact(6) != 720) {
    err = err + 1;
  }
  ?(fact(1) != 1) {
    err = err + 1;
  }
  ^err;
}

=ex{fact, self_check}
```

---

## 3. Taxonomia Estável de Erros (`--ai-feedback`)

Quando invocado com `--ai-feedback`, o compilador retorna JSON estruturado no seguinte padrão:

| Classe | Código Estável | Causa | Sugestão |
|---|---|---|---|
| `ParserError` | `E_SYNTAX_MISSING_RPAREN` | Falta `)` | Adicionar parêntese fechando. |
| `ParserError` | `E_SYNTAX_MISSING_SEMICOLON` | Falta `;` | Adicionar ponto-e-vírgula ao final do statement. |
| `SemanticError` | `E_SEMANTIC_DIV_ZERO` | `x / 0` ou `x % 0` | Guardar o divisor com `?(y != 0)`. |
| `SemanticError` | `E_SEMANTIC_UNDEFINED_VAR` | Uso de identificador não associado | Declarar e inicializar a variável antes do uso. |
| `ExecutionError` | `E_EXEC_DIV_ZERO` | Divisão por zero detectada em execução | Proteger denominadores em tempo de execução. |
| `ExecutionError` | `E_EXEC_STACK_OVERFLOW` | Vazamento de pilha no frame | Garantir retorno único com `sp == 1`. |

---

## 4. Limites de Execução da LinVM

- **Stack Size**: 256 slots de `i64`.
- **Locals Frame**: 64 registradores locais por frame.
- **Max Recursion Depth**: 192 frames (`VM_MAX_DEPTH`).
- **Instruction Step Limit**: 200.000.000 passos (prevenção de travamento / halting problem).
