# Demonstração Prática: Integrando LIN / LinVM em um Projeto Existente

Este diretório demonstra como incorporar um módulo LIN compilado em uma aplicação hospedeira convencional (em C/C++).

---

## 1. O Problema no Software Tradicional
Em sistemas financeiros, motores de precificação ou regras de negócio críticas escritas em C/C++:
- Falhas de memória (`buffer overflow`, ponteiros soltos, `malloc` com vazamento de memória) causam incidentes graves.
- Loops acidentais ou recursões não limitadas travam a aplicação.
- Resultados podem divergir entre diferentes compiladores ou plataformas.

## 2. A Solução com LIN
A lógica sensível é isolada em um arquivo nativo LIN ([`risk_engine.lin`](risk_engine.lin)), compilada uma única vez para uma **imagem canônica de bytecode LINBC1** ([`risk_engine.linbc`](risk_engine.linbc)), e executada pela **LinVM C11** diretamente no processo da sua aplicação.

### Vantagens Concretas Provadas:
1. **Zero Heap Allocation**: Executa em arena estática pré-alocada pelo host. `malloc` e `free` não são usados durante a execução.
2. **Imunidade a Buffer Overflows**: Toda indexação e acesso a pilha são validados e falham de forma segura (*fail-closed*).
3. **Contagem Determinística de Passos (`steps`)**: A LinVM contabiliza exatamente quantos passos cada função levou para executar (ex: 16 passos para cálculo normal, 31 passos para análise completa de fraude).
4. **Imagem com Integridade Criptográfica (SHA-256)**: O host valida o cabeçalho e o digest do bytecode antes de autorizar qualquer instrução.

---

## 3. Como Reproduzir

### Passo 1: Verificar e Compilar o Módulo LIN
```bash
# Validar tipagem e linting
./zig-out/bin/lin_native check examples/integration_demo/risk_engine.lin
./zig-out/bin/lin_native lint examples/integration_demo/risk_engine.lin

# Compilar para bytecode canônico LINBC1
./transpile/c/bin/lin_c0 image examples/integration_demo/risk_engine.lin -o examples/integration_demo/risk_engine.linbc
```

### Passo 2: Compilar e Rodar a Aplicação C Integrada
```bash
gcc -O2 -Wall -Wextra -std=c11 \
  -Itranspile/c/lin_c \
  -o examples/integration_demo/main_app \
  examples/integration_demo/main_app.c \
  transpile/c/lin_c/lin_linbc1.c \
  transpile/c/lin_c/lin_vm.c \
  transpile/c/lin_c/lin_sha256.c \
  transpile/c/lin_c/lin_common.c \
  transpile/c/lin_c/lin_token.c \
  transpile/c/lin_c/lin_ast.c \
  transpile/c/lin_c/lin_parse.c \
  transpile/c/lin_c/lin_str.c

# Executar
./examples/integration_demo/main_app
```
