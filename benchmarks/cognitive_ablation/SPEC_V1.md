# COGNITIVE_ABLATION_BENCHMARK_V1.md
## Protocolo Experimental Congelado — Fase A: Camada Cognitiva e Recuperação Iterativa

- **Versão do Protocolo:** 1.0.0 (CONGELADO)
- **Data de Congelamento:** 2026-08-18
- **Objetivo Científico:** Medir o ganho causal atribuível estritamente à camada cognitiva LIN (representação, verificação e feedback estruturado de trauma) sobre o mesmo modelo neural, em comparação com baselines puros e oráculos independentes.

---

## 1. Princípios Metodológicos Fundamentais

1. **Invariância de Modelo:** Ao comparar sistemas da mesma classe (B, C, D, E), o modelo neural base, pesos, temperatura, seed e top_p são estritamente idênticos. A única variável independente é a camada LIN.
2. **Oracle Independente:** O `behavior_eq_gate` e o compilador LIN atuam como verificadores internos de ciclo. A aprovação final da tarefa é decidida por um **Oracle Externo Independente** (testes em caixa preta / invariantes externas), nunca pelo próprio verificador sob teste.
3. **Isolamento de Recuperação:** Falhas iniciais são desacopladas de falhas finais para evitar contaminação da taxa de recuperação.
4. **Penalização por Custo de Tentativas:** A métrica pondera tentativas ($k$), tokens consumidos e latência acumulada até a convergência.
5. **Reprodutibilidade Estrita por Artefato Imutável:** Nenhuma execução é válida sem log raw de prompts, respostas, hashes intermediários de AST, registros de trauma e hash SHA-256 do manifesto de entrada.

---

## 2. Matriz de Ablação

| Sistema ID | Arquitetura | Modelo Base | Camada LIN / Representação | Loop & Feedback |
| :--- | :--- | :--- | :--- | :--- |
| **A** | *Upper Baseline* | 70B Class (Llama-3.1-70B / Qwen-2.5-72B) | Natural / Code Padrão | Single-shot (k=1) |
| **B** | *Control Baseline*| 8B Class (Llama-3.1-8B / Qwen-2.5-7B) | Natural / Code Padrão | Single-shot (k=1) |
| **C** | *Repres. Ablation* | 8B Class | Prompt & Sintaxe LIN (sigilos) | Single-shot (k=1) |
| **D** | *Unstructured Loop*| 8B Class | Prompt & Sintaxe LIN | Loop iterativo (k ≤ 3), feedback textual genérico de erro |
| **E** | *Full LIN Cognitive*| 8B Class | Prompt & Sintaxe LIN | Loop iterativo (k ≤ 3), **Feedback Estruturado de TRAUMA** |
| **F** | *Ultra-Light Model*| 3B Class (Qwen-2.5-3B) | Prompt & Sintaxe LIN | Loop iterativo (k ≤ 3), **Feedback Estruturado de TRAUMA** |

---

## 3. Classificação dos Desfechos de Execução

Para cada tarefa $i \in \{1 \dots N\}$ e sistema $S$:

- $\mathbf{P_1}$ (**Initial Pass**): O candidato gerado na tentativa $k=1$ é aprovado pelo Oracle Independente.
- $\mathbf{F_1}$ (**Initial Fail**): O candidato gerado na tentativa $k=1$ é rejeitado pelo Verificador ou Oracle.
- $\mathbf{P_R}$ (**Recovered Pass**): Dado $\mathbf{F_1}$, o sistema converge e é aprovado pelo Oracle na tentativa $k \in \{2, 3\}$.
- $\mathbf{F_F}$ (**Final Fail**): O sistema esgota $k_{\max}=3$ tentativas sem aprovação pelo Oracle.

$$\text{Total de Tarefas } N = \mathbf{P_1} + \mathbf{P_R} + \mathbf{F_F}$$

---

## 4. Definição Matemática das Métricas

### 4.1. Taxa de Acurácia Zero-shot ($pass@1$)
$$\text{pass@1} = \frac{\mathbf{P_1}}{N}$$

### 4.2. Taxa de Acurácia Final ($pass@k$)
$$\text{pass@k} = \frac{\mathbf{P_1} + \mathbf{P_R}}{N}$$

### 4.3. Taxa de Sucesso de Recuperação ($RSR$)
Medida crítica da eficácia da camada cognitiva e da memória de trauma:
$$RSR = \begin{cases} \frac{\mathbf{P_R}}{\mathbf{F_1}}, & \text{se } \mathbf{F_1} > 0 \\ \text{N/A}, & \text{se } \mathbf{F_1} = 0 \end{cases}$$

### 4.4. Custo Médio de Resolução ($\bar{C}_{pass}$)
Calculado exclusivamente sobre tarefas resolvidas ($\mathbf{P_1} \cup \mathbf{P_R}$):
$$\bar{T}_{pass} = \frac{1}{|\text{Pass}|} \sum_{i \in \text{Pass}} \text{tokens}_i, \quad \bar{K}_{pass} = \frac{1}{|\text{Pass}|} \sum_{i \in \text{Pass}} k_i$$

### 4.5. Taxa de Repetição de Mesma Classe de Erro ($ERR$)
Mede se o modelo repete a mesma violação estrutural após receber o feedback:
$$ERR = \frac{\text{Tentativas onde } \text{violation\_class}(k) == \text{violation\_class}(k-1)}{\text{Total de retries com falha}}$$

---

## 5. Regras de Parada e Limites Operacionais

1. **Tentativas Máximas ($k_{\max}$):** 3 tentativas por tarefa.
2. **Timeout por Tentativa:** 30 segundos por inferência neural / 5 segundos por verificação determinística.
3. **Budget de Tokens:** Máximo de 2048 tokens gerados por tentativa.
4. **Critério de Aborto Imediato:** Violação catastrófica de invariante imutável do núcleo $\rightarrow \mathbf{F_F}$ imediato com flag de segurança.

---

## 6. Schemas Formais (JSON Schema)

### 6.1. Task Schema (`schemas/task.schema.json`)
Consulte o arquivo [`task.schema.json`](./schemas/task.schema.json).

### 6.2. Trauma Feedback Schema (`schemas/trauma.schema.json`)
Consulte o arquivo [`trauma.schema.json`](./schemas/trauma.schema.json).

### 6.3. Run Metrics Schema (`schemas/metrics.schema.json`)
Consulte o arquivo [`metrics.schema.json`](./schemas/metrics.schema.json).

---

## 7. Estrutura Imutável de Diretórios e Artefatos

```
benchmarks/cognitive_ablation/
├── SPEC_V1.md                          # Este documento (CONGELADO)
├── MANIFEST.json                       # Lista de 30 tarefas com SHA-256
├── schemas/
│   ├── task.schema.json
│   ├── trauma.schema.json
│   └── metrics.schema.json
├── prompts/
│   ├── B_natural_zero_shot.txt
│   ├── C_lin_zero_shot.txt
│   ├── D_lin_unstructured_retry.txt
│   ├── E_lin_trauma_retry.txt
│   └── F_lin_trauma_retry_3b.txt
├── tasks/
│   ├── T001.json ... T030.json
├── oracles/
│   ├── oracle_T001.mjs ... oracle_T030.mjs
└── harness/
    ├── mock_model_adapter.mjs          # Modelo de teste determinístico (sanity check)
    ├── real_model_adapter.mjs          # Adapter OpenAI/Ollama compatível
    ├── lin_verifier_adapter.mjs        # Interface com o compilador LIN e behavior_gate
    └── benchmark_runner.mjs            # Orquestrador da execução
```

---

## 8. Critérios de Falsificação e Decisão

1. **Hipótese de Representação ($C \text{ vs } B$):**
   - Se $\text{pass@1}(C) \le \text{pass@1}(B) - 5\%$, a hipótese de que a sintaxe/sigilos isolados aumentam zero-shot é rejeitada.
2. **Hipótese de Recuperação Cognitiva ($E \text{ vs } D$):**
   - Se $RSR(E) \le RSR(D)$, a hipótese de que o **Trauma Estruturado** melhora a capacidade de auto-correção é rejeitada.
3. **Hipótese de Eficiência do Modelo Pequeno ($F \text{ vs } B$):**
   - Se $\text{pass@k}(F) \ge \text{pass@1}(B)$ com $\text{tokens}(F) \le \text{tokens}(B)$, a hipótese de que a Camada Cognitiva LIN permite que modelos pequenos superem modelos maiores em tarefas estruturadas é preliminarmente aceita para a Fase B.
