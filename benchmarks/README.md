# LIN/DICE-L Benchmark Suite

## Visão Geral

Esta suíte de benchmarks avalia linguagens de programação para o núcleo de execução do DICE-L.

## Estrutura

```
benchmarks/
├── README.md              # Este arquivo
├── common/                # Código compartilhado (geradores, métricas)
│   ├── generators.cr      # Geradores de dados de teste (Crystal)
│   ├── generators.rs      # Geradores de dados de teste (Rust)
│   └── metrics.cr         # Coleta e reporte de métricas
├── crystal/               # Implementações em Crystal
│   ├── 01_parsing.cr
│   ├── 02_ir_builder.cr
│   ├── 03_hashcons.cr
│   ├── 04_dedup.cr
│   ├── 05_serialization.cr
│   ├── run_all.sh
│   └── shard.yml
├── rust/                  # Implementações em Rust
│   ├── src/
│   │   ├── main.rs
│   │   ├── benchmarks/
│   │   └── Cargo.toml
│   └── run_all.sh
├── run_all.sh             # Executa todos os benchmarks
└── compare_results.py     # Análise comparativa dos resultados
```

## Como Executar

### Todos os Benchmarks (ambas linguagens)

```bash
./run_all.sh
```

### Apenas Crystal

```bash
cd crystal
./run_all.sh
```

### Apenas Rust

```bash
cd rust
./run_all.sh
```

### Benchmark Individual

```bash
# Crystal
crystal run crystal/01_parsing.cr --release

# Rust
cd rust && cargo run --release --bin 01_parsing
```

## Benchmarks Incluídos

| # | Nome | Descrição | Peso |
|---|------|-----------|------|
| 1 | Parsing de AST | Análise sintática de código LIN | 2x |
| 2 | Construção do IR | Criação da representação intermediária | 2x |
| 3 | HashCons | Deduplicação estrutural via hash consing | 3x |
| 4 | Deduplicação | Identificação de termos idênticos | 2x |
| 5 | Serialização | I/O de estruturas (JSON/binário) | 1x |
| 6 | Matching Semântico | Pattern matching com regras semânticas | 3x |
| 7 | Resolução de Dependências | Graph traversal e topological sort | 1x |
| 8 | Execução de Regras | Engine de reescrita de termos | 2x |
| 9 | Tool Chaining | Pipeline completo (parser→IR→optimizer→codegen) | 1x |
| 10 | Memória/Latência | Profile de alocação e GC | 2x |
| 11 | Concorrência | Paralelização de workloads | 1x |
| 12 | Cold Start | Tempo de inicialização | 1x |
| 13 | Throughput | Performance sustentada | 2x |
| 14 | Consumo de RAM | Uso de memória em diferentes cenários | 2x |

## Métricas Coletadas

Para cada benchmark:

- **Tempo de execução** (média, mediana, desvio padrão)
- **Throughput** (operações/segundo)
- **Uso de memória** (RSS, pico, alocações)
- **Cold start time** (quando aplicável)

## Interpretação dos Resultados

Cada linguagem recebe nota 1-5 por dimensão, com pesos conforme tabela acima.

**Score final** = Σ(peso × nota) / Σ(peso)

- ≥ 4.5: Altamente Recomendado
- 3.5-4.4: Recomendado
- 2.5-3.4: Neutro
- < 2.5: Não Recomendado

## Requisitos

- Crystal >= 1.20
- Rust >= 1.70
- Python 3.8+ (para análise de resultados)

## Status

- ✅ Plano definido
- ⏳ Implementação em andamento
- ⏳ Coleta de dados
- ⏳ Análise comparativa
