# Trajetória Tecnológica: Python Legado → Mojo Puro → LinVM Normativa

**Projeto:** Lin-Audit Ethereum  
**Documento:** `docs/MIGRATION_PATH_MOJO_TO_LIN.md`  
**Status:** Estratégia Canônica de Transição  
**Versão:** 1.0.0  

---

## 1. Visão Geral e Hipótese Estratégica

O Lin-Audit adota uma trajetória de migração técnica com delimitações explícitas:

$$\text{Python Legado} \longrightarrow \text{Mojo Puro} \longrightarrow \text{LinVM Normativa}$$

- **Onde o LinVM brilha:** A LinVM oferece determinismo formal, ausência de heap não controlado, semântica fail-closed estrita e verificação de passos para auditorias auditáveis.
- **Onde o Mojo acelera:** O Mojo (versão 1.0+) fornece tipagem estática moderna, desempenho de nível nativo (LLVM) e execução compilada de alta performance, sem depender do interpretador CPython.
- **A regra de ouro:** **ZERO importações de Python no núcleo Mojo** (`from python import Python` é terminantemente proibido no motor criptográfico).

---

## 2. As Duas Fases da Transição

### Fase 1 — Mojo Puro Substitui o Python (Curto Prazo / M1-A)
O M1-A consolida uma implementação em **Mojo puro** (`tools/lin_audit_tx.mojo`):
- Implementação bit-a-bit de Keccak-f[1600] e Keccak-256 (padding `0x01 ... 0x80`, taxa 136 bytes);
- Parser de bytes hexadecimais e envelopes EIP-2718;
- CLI executável diretamente via `mojo run tools/lin_audit_tx.mojo`;
- Geração de vetores e oráculo de alta velocidade para testes de mutação.

### Fase 2 — LinVM como Implementação Normativa (Escopo do Grant / M1-B & M1-C)
Após a estabilização do Mojo, a semântica criptográfica é congelada e portada para a **LinVM** sob o perfil `LIN-ETH-1` ([`docs/M1_KECCAK_IMPLEMENTATION.md`](file:///home/k/Downloads/lin-master/docs/M1_KECCAK_IMPLEMENTATION.md)):
- A **LinVM** torna-se a fonte normativa oficial do veredito;
- O **Mojo** passa a operar como oráculo de validação cruzada, ferramenta de benchmark e gerador de fuzzing;
- Clientes externos (Geth / Reth) atuam como oráculos de conformidade do ecossistema.

$$\text{LinVM (Normativa)} == \text{Mojo (Referência Interna)} == \text{Geth/Reth (Oráculos Externos)}$$

---

## 3. Matriz de Responsabilidades

| Componente | Função na Arquitetura Final | Linguagem / Runtime |
| :--- | :--- | :--- |
| **Núcleo Criptográfico Normativo** | Validação de RLP, envelopes EIP-2718, Keccak-256 e emissão de veredito | **LinVM (`.linbc`)** |
| **Referência de Alta Performance & Fuzzing** | Testes de carga, fuzzing diferencial, benchmarks e verificação rápida | **Mojo Puro (`.mojo`)** |
| **Host Fino de I/O** | Leitura de disco, transporte de rede (RPC) e formatação de JSON/recibos | **C11 / Ferramental Mínimo** |
| **Validação Cruzada Externa** | Garantia de paridade com o consenso Ethereum | **Geth / Reth** |
| **Protótipo Histórico (A Ser Deprecado)** | Protótipo inicial de exploração | Python (Transição) |

---

## 4. Critérios Estritos para a Descontinuação do Python

O caminho Python só será descontinuado após:
1. O corpus de 10.000 fixtures estar congelado;
2. Mojo e LinVM apresentarem bit-exact parity em 100% dos fixtures;
3. Oráculos Geth e Reth confirmarem a igualdade dos digests;
4. Todos os 7 testes de mutação adversariais passarem em Mojo e LinVM;
5. O pipeline de CI estiver executando nativamente em Mojo e LinVM.

---

## 5. Matriz de Evidência e Política Anti-Sobrereivindicação (No-Overclaim)

Em estrita conformidade com a regra de integridade do repositório **R5 (`LABEL_TOY_VS_EXPERIMENTAL_VS_REAL_WORLD_NO_OVERCLAIM`)**, o estado empírico das implementações é delimitado abaixo:

| Dimensão | M1-A Mojo | M1-B LinVM |
| :--- | :--- | :--- |
| **Keccak-256** | **Demonstrado e versionado** (`tools/lin_audit_tx.mojo`) | Ainda não portado (especificado em `docs/M1_KECCAK_IMPLEMENTATION.md`) |
| **Envelopes EIP-2718** | **Demonstrados** (Legacy, EIP-2930, EIP-1559, EIP-4844) | Ainda não portados |
| **Comportamento Fail-Closed** | **Demonstrado** com códigos de saída determinísticos (`0` vs `1`) | A ser implementado |
| **Determinismo Criptográfico** | Vetores de teste e casos positivo/negativo comprovados | Especificado formalmente no perfil `LIN-ETH-1` |
| **Desempenho Comparável** | **Ainda não medido** | **Ainda não medido** |
| **Papel Arquitetural** | Referência de transição e oráculo de teste | Núcleo normativo oficial do projeto |

> **Nota Metodológica Obrigatória:** É terminantemente proibido alegar speedup relativo, throughput comparado ou vantagens de latência entre Mojo e LinVM sem a condução prévia de um benchmark empírico controlado e auditável sobre o corpus de 10.000 transações públicas da Mainnet.

---

## 6. Como Executar o Verificador Mojo

```bash
# Execução direta com raw transaction hex
mojo run tools/lin_audit_tx.mojo --raw 0x02f873... --claimed 0xb12892...

# Saída determinística em JSON:
# {
#   "engine": "mojo_pure_m1_a",
#   "raw_bytes_len": 118,
#   "recomputed_hash": "0xb12892bc345f93e424661f456bb031465edd87914052dce9e47179c3bff01ec3",
#   "claimed_hash": "0xb12892bc345f93e424661f456bb031465edd87914052dce9e47179c3bff01ec3",
#   "hash_matches": true,
#   "verdict": "PASS"
# }
```
