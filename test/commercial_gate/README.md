# Gate de Prontidão Comercial — Nível Piloto

Este gate automatizado (`gate_readiness_pilot.py`) estabelece os critérios objetivos de aceitação que o componente LIN deve cumprir antes de qualquer oferta de **piloto técnico comercial**.

---

## 1. Os 5 Pilares Obrigatórios

| Pilar | Escopo da Prova | Critério de Aceitação | Status |
| :--- | :--- | :--- | :--- |
| **1. Correção Matemática** | 114 vetores cobrindo casos normais, extremos de liquidez, reservas desbalanceadas e entradas inválidas/negativas. | 100% bit-exact contra o oráculo canônico Uniswap V2; fail-closed em zeros/negativos. | **PASS** |
| **2. Emissão LINBC1** | Reemissão determinística em checkout limpo e teste de consenso roundtrip fonte vs. bytecode. | Bytes idênticos e status `CONSENSUS` confirmado no C0. | **PASS** |
| **3. Matriz Criptográfica** | Verificação de caminhos Merkle SHA-256 e injeção de mutações em folhas, nós irmãos (`sibling0`, `sibling1`) e raízes. | 100% de detecção e rejeição de qualquer mutação adversarial. | **PASS** |
| **4. Sanitização de Memória** | Compilação do host com GCC `-fsanitize=address,undefined` (ASan/UBSan) + fuzzing de truncamento de bytecode. | Zero erros de memória e 100% de rejeições limpas (*fail-closed*) sem crashes ou SIGSEGV. | **PASS** |
| **5. Perfil de Desempenho** | Amostragem estatística de latência individual de execução do bytecode em hardware documentado. | Relatório com métricas reproduzíveis: Média, p50, p95 e p99. | **PASS** |

---

## 2. Como Executar

```bash
python3 test/commercial_gate/gate_readiness_pilot.py
```
