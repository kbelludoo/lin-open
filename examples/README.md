# Exemplos Práticos do LIN — Computação Verificável e Recibos Criptográficos

Este diretório contém exemplos reais, práticos e executáveis do ecossistema LIN.
Diferente de linguagens convencionais (onde o código é executado e o resultado precisa ser aceito por "confiança cega"), no LIN toda computação é determinística e gera um **Recibo Criptográfico SHA-256 (LCR)** auditável por qualquer pessoa, regulador ou contrato inteligente sem confiar no servidor.

---

## Como Rodar as Demonstrações (1 Comando)

Para rodar a suíte visual completa com 7 casos reais:

```bash
# Rodar todas as demonstrações com medições de passos e tempos:
python3 examples/run_demos.py

# Ou abrir o menu interativo:
python3 examples/run_demos.py --interactive
```

---

## Índice dos Exemplos Práticos

### 1. DeFi & Automated Market Maker ([`amm_swap.lin`](./amm_swap.lin))
* **O que faz:** Implementa o motor de swap de tokens de produto constante ($x \cdot y = k$) do Uniswap v2 com taxa ajustável (ex: 0,30%) e função de verificação da conservação de liquidez.
* **Onde o Lin é melhor:** No Ethereum L1, processar 2.000 swaps custa **$70.000 dólares** em gás. Com Lin, o lote é resolvido off-chain e liquidado no contrato por apenas **$4,20** (16.599x mais barato), mantendo o poder de *slashing* imediato se houver qualquer tentativa de inflação de saldo.
* **Como executar no terminal:**
  ```bash
  # 1. Validar tipos e sintaxe do módulo
  ./transpile/c/bin/lin_c0 check examples/amm_swap.lin

  # 2. Executar swap (ReservaIn=1.000.000, ReservaOut=4.000.000, In=10.000, Taxa=30 bps):
  ./transpile/c/bin/lin_c0 vm examples/amm_swap.lin calculate_swap_out 1000000 4000000 10000 30
  # Retorna: 39486 tokens em 24 passos LinBC1

  # 3. Auditar a invariante K com saída honesta (39.486 tokens):
  ./transpile/c/bin/lin_c0 vm examples/amm_swap.lin verify_invariant_k 1000000 4000000 10000 39486
  # Retorna: 1 (Legítimo - Liquidez Preservada)

  # 4. Auditar tentativa de fraude com saída forjada (50.000 tokens):
  ./transpile/c/bin/lin_c0 vm examples/amm_swap.lin verify_invariant_k 1000000 4000000 10000 50000
  # Retorna: 0 (Fraude Bloqueada)
  ```

---

### 2. Motor de Risco de Crédito & Compliance Bancário ([`credit_risk_scoring.lin`](./credit_risk_scoring.lin))
* **O que faz:** Modelo de pontuação de crédito (0 a 1000) e aprovação de empréstimo baseado em comprometimento de renda (DTI), score de bureau e histórico de atrasos sob regras do Banco Central / Basileia.
* **Onde o Lin é melhor:** Gera um recibo imutável do cálculo. O Banco Central ou o próprio consumidor pode auditar matematicamente que nenhuma variável abusiva foi usada, garantindo compliance sem precisar expor dados sigilosos ou códigos proprietários.
* **Como executar no terminal:**
  ```bash
  # Cliente A - Baixo Risco (Renda=8000, Parcela=1600, Bureau=750, Atrasos=0):
  ./transpile/c/bin/lin_c0 vm examples/credit_risk_scoring.lin calculate_credit_score 8000 1600 750 0
  # Retorna: Score 800 -> Aprovado

  # Cliente B - Alto Risco (Renda=8000, Parcela=3500, Bureau=750, Atrasos=3):
  ./transpile/c/bin/lin_c0 vm examples/credit_risk_scoring.lin calculate_credit_score 8000 3500 750 3
  # Retorna: Score 360 -> Reprovado
  ```

---

### 3. Rate Limiter Criptográfico para SaaS & APIs ([`api_rate_limiter.lin`](./api_rate_limiter.lin))
* **O que faz:** Algoritmo Token Bucket para controle de tráfego de APIs e cobrança de quotas em tempo real.
* **Onde o Lin é melhor:** Em APIs tradicionais (OpenAI, AWS, Stripe), clientes disputam faturas alegando cobrança indevida ou corte abusivo de serviço. Com Lin, o provedor emite um recibo do estado do balde de tokens que prova matematicamente se a requisição estourou a cota contratada.
* **Como executar no terminal:**
  ```bash
  # Requisição Normal (Capacidade=100, Saldo=10, Recarga=5/s, Passou=10s, Pede=20):
  ./transpile/c/bin/lin_c0 vm examples/api_rate_limiter.lin evaluate_request 100 10 5 10 20
  # Retorna: 40 (Permitido, novo saldo de tokens)

  # Requisição em Excesso (Capacidade=100, Saldo=10, Recarga=5/s, Passou=2s, Pede=50):
  ./transpile/c/bin/lin_c0 vm examples/api_rate_limiter.lin evaluate_request 100 10 5 2 50
  # Retorna: -1 (Throttled / Bloqueado por limite de taxa)

  # Auditoria do Bloqueio:
  ./transpile/c/bin/lin_c0 vm examples/api_rate_limiter.lin audit_throttled_decision -1
  # Retorna: 1 (Bloqueio legítimo auditado)
  ```

---

### 4. Prova de Inclusão em Árvore Merkle ([`merkle_prover.lin`](./merkle_prover.lin))
* **O que faz:** Verificador de inclusão criptográfica de 3 níveis para até 8 nós de lote.
* **Onde o Lin é melhor:** Permite que clientes leves (mobile, IoT ou contratos inteligentes) comprovem que seu pagamento ou documento está gravado em um bloco sem ter que baixar gigabytes de dados.
* **Como executar no terminal:**
  ```bash
  # Prova Legítima (Folha 100 contra Raiz 1626317746 com irmãos s0, s1, s2):
  ./transpile/c/bin/lin_c0 vm examples/merkle_prover.lin verify_inclusion_3 100 200 1482393480 999999 0 1626317746
  # Retorna: 1 (Inclusão Comprovada em 122 passos)

  # Prova Forjada (Folha alterada para 101):
  ./transpile/c/bin/lin_c0 vm examples/merkle_prover.lin verify_inclusion_3 101 200 1482393480 999999 0 1626317746
  # Retorna: 0 (Adulteração Rejeitada)
  ```

---

### 5. Inteligência Artificial & TinyML Determinística ([`neural_mlp.lin`](./neural_mlp.lin))
* **O que faz:** Rede Neural Multilayer Perceptron (MLP 4x4x2) quantizada em números inteiros (INT8) para detecção de anomalias em sensores industriais IoT (temperatura, vibração, corrente, pressão).
* **Onde o Lin é melhor:** Modelos de IA tradicionais sofrem com *GPU drift* (diferenças de precisão de ponto flutuante entre placas Nvidia, AMD e CPUs Intel/ARM alteram as decisões da rede). No Lin, todo cálculo opera em ponto fixo determinístico, gerando bit por bit o mesmo resultado.
* **Como executar no terminal:**
  ```bash
  # Leitura Normal de Sensor (Temp=5, Vib=2, Amp=10, Bar=1):
  ./transpile/c/bin/lin_c0 vm examples/neural_mlp.lin predict_sensor_state 5 2 10 1
  # Retorna: 1 (Operação Normal)

  # Leitura com Anomalia Crítica (Temp=100, Vib=-50, Amp=20, Bar=80):
  ./transpile/c/bin/lin_c0 vm examples/neural_mlp.lin predict_sensor_state 100 -50 20 80
  # Retorna: 0 (Alerta de Falha Iminente)
  ```

---

### 6. Defesa contra Ataques Red Team & Bombas DoS (Fail-Closed)
* **O que faz:** O parser e a VM do Lin possuem barreiras matemáticas de profundidade rígidas (`LIN_PARSER_MAX_DEPTH = 64`, `LIN_VM_MAX_DEPTH = 192`).
* **Onde o Lin é melhor:** Em Node, Python ou compiladores convencionais em C, enviar expressões com dezenas de milhares de operadores esgota a pilha de execução nativa do sistema operacional, causando `SIGSEGV` (exit 139) e derrubando servidores em produção. No Lin, o erro é abortado de forma limpa (*fail-closed*) em menos de 2 milissegundos sem derrubar o processo.
* **Como testar no terminal:**
  ```bash
  # Ataque com 100.000 operadores de negação unária:
  ./transpile/c/bin/lin_c_receipt --expr "$(python3 -c 'print("-" * 100000 + "1")')" --env "x=1"
  # Retorna: Código 2 (error.ParseTooDeep) — Zero crash do servidor!

  # Ataque com 25.000 parênteses aninhados:
  ./transpile/c/bin/lin_c_receipt --expr "$(python3 -c 'print("(" * 25000 + "1" + ")" * 25000)')" --env "x=1"
  # Retorna: Código 2 (error.ParseTooDeep) em 0.79ms
  ```

---

### 7. Recibos Criptográficos de Computação (LCR SHA-256 Engine)
* **O que faz:** Emite e valida recibos estruturados de computação onde a árvore Merkle vincula o código-fonte, os parâmetros de entrada, o número exato de passos e o resultado final.
* **Onde o Lin é melhor:** Qualquer terceiro pode verificar o recibo com o binário C nativo ou com um oráculo independente em Python padrão (cleanroom), sem precisar confiar no gerador.
* **Como testar no terminal:**
  ```bash
  # 1. Gerar recibo oficial:
  ./transpile/c/bin/lin_c0 receipt create --source "return x * x;" --input 9 > /tmp/meu_recibo.rulel

  # 2. Auditar com oráculo independente em Python:
  python3 tools/verify_compute_receipt.py --receipt /tmp/meu_recibo.rulel --source "return x * x;"
  # Saída: PASS: FULL_CONSENSUS: Merkle root verified and execution replayed (f(9) = 81)

  # 3. Simular tentativa de fraude (trocar resultado 81 por 999999):
  sed -i 's/\.o=81/\.o=999999/' /tmp/meu_recibo.rulel
  ./transpile/c/bin/lin_c0 receipt verify --receipt /tmp/meu_recibo.rulel
  # Saída: FAIL: Compute Receipt TAMPERED! (Rejeição imediata)
  ```

---

### 8. Algoritmos Arbitrários & Fuzzing Algébrico ([`custom_algorithms.lin`](./custom_algorithms.lin))
* **O que faz:** Demonstra que o Lin executa qualquer algoritmo geral iterativo (`while`), condicional (`?`) e chamadas de funções com recursão.
* **Onde o Lin é melhor:** Não é hardcoded nem limitado a expressões simples. O Lin executa 1.000 expressões matemáticas aleatórias complexas com 100% de equivalência bit a bit contra o Python e executa repositórios reais inteiros (QOI, TinyExpr, SipHash-2-4).
* **Como testar no terminal:**
  ```bash
  # 1. Fibonacci iterativo:
  ./transpile/c/bin/lin_c0 vm examples/custom_algorithms.lin fibonacci 10
  # Retorna: 55 (em 173 passos LinBC1)

  # 2. Conjectura de Collatz (3n+1) para n=27:
  ./transpile/c/bin/lin_c0 vm examples/custom_algorithms.lin collatz_steps 27
  # Retorna: 111 passos (executa 2.271 instruções na VM em < 1ms)

  # 3. Raiz Quadrada Inteira de Newton-Raphson para 2.000.000:
  ./transpile/c/bin/lin_c0 vm examples/custom_algorithms.lin integer_sqrt 2000000
  # Retorna: 1414 (em 268 passos LinBC1)

  # 4. Fuzzing de 1.000 expressões aleatórias arbitrárias (+, -, *, /, %, ==, !=, <, <=, >, >=):
  python3 tools/verify_arbitrary_fuzz.py 1000
  # Saída: PASS: 1000/1000 expressões aleatórias arbitrárias com 100% de consenso bit-exato!
  ```

---


## Como Escrever Código LIN (Sintaxe em 3 Minutos)

O LIN foi desenhado para ser enxuto, minimalista e imune a comportamento indefinido:

| Conceito | Sintaxe no LIN | Exemplo |
| :--- | :--- | :--- |
| **Cabeçalho Obrigatório** | `@LIN:L1c:0.2` | Primeira linha do arquivo |
| **Função** | `!nome(param: int) -> int { ... }` | `!dobro(x: int) -> int { ^x * 2; }` |
| **Retorno** | `^expressao;` | `^resultado;` |
| **Condicional** | `?(condicao) { ... } : { ... };` | `?(x > 0) { r = 1; } : { r = 0; };` |
| **Variáveis Locais** | Atribuição direta sem tipo | `total = preco * qtd;` |
| **Exportação de Funções** | `=ex{fn1, fn2}` | Última linha indicando as funções públicas |
