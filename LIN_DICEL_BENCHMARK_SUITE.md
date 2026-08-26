# LIN/DICE-L Benchmark Suite - Plano de Avaliação

## 📋 Visão Geral

Este documento define uma suíte de benchmarks abrangente para avaliar linguagens de programação como candidatas ao **núcleo de execução do DICE-L**, indo além do teste simplista de Fibonacci.

---

## 🎯 Objetivo

Identificar a linguagem ideal para implementar o núcleo determinístico do DICE-L, considerando:
- Performance em workloads reais do projeto
- Capacidade de representar invariantes no sistema de tipos
- Controle de memória e previsibilidade
- Ecossistema e manutenibilidade a longo prazo

---

## 🔬 Metodologia Correta

### Problema com Benchmark Anterior
O teste `fib(40)` mede apenas:
- Recursão pura
- Otimização de chamadas de função
- Performance bruta de CPU

**Não representa** as operações reais do DICE-L.

### Nova Abordagem
Benchmarks representativos das operações reais do LIN/DICE-L, testando **12 dimensões críticas**.

---

## 📊 Suite de Benchmarks Proposta

### 1. **Parsing de AST**
**Objetivo:** Medir performance na análise sintática de código LIN.

```crystal
# Exemplo: parsing de 10.000 expressões LIN
expressions = generate_lin_expressions(10000)
start = Time.monotonic
expressions.each { |expr| LIN::Parser.parse(expr) }
elapsed = Time.monotonic - start
```

**Métricas:**
- Throughput (expressões/segundo)
- Alocações de memória
- Pico de RAM

---

### 2. **Construção do IR (Intermediate Representation)**
**Objetivo:** Avaliar criação e manipulação da representação intermediária.

```rust
// Exemplo: construir IR para 5.000 funções
let functions = generate_functions(5000);
let start = Instant::now();
for func in functions {
    let ir = IRBuilder::build(func);
    ir.validate();
}
let elapsed = start.elapsed();
```

**Métricas:**
- Tempo de construção por nó IR
- Imutabilidade vs mutabilidade
- Custo de validação

---

### 3. **HashCons (Hash Consing)**
**Objetivo:** Testar deduplicação estrutural de termos via hash consing.

```crystal
# HashCons é crítico para normalização no DICE-L
terms = generate_terms(50000)
hashcons = HashCons.new
start = Time.monotonic
terms.each { |term| hashcons.intern(term) }
elapsed = Time.monotonic - start
dedup_ratio = terms.size / hashcons.unique_count
```

**Métricas:**
- Taxa de deduplicação
- Lookup time (O(1) esperado)
- Overhead de memória do hash table

---

### 4. **Deduplicação Estrutural**
**Objetivo:** Medir eficiência na identificação de termos idênticos.

```rust
let terms = generate_structural_terms(100000);
let start = Instant::now();
let mut seen = HashSet::new();
let mut duplicates = 0;
for term in terms {
    if !seen.insert(term.clone()) {
        duplicates += 1;
    }
}
```

**Métricas:**
- Comparação estrutural profunda
- Cache locality
- Uso de memória durante dedup

---

### 5. **Serialização/Deserialização**
**Objetivo:** Avaliar I/O de estruturas LIN (JSON, binário, etc).

```crystal
ast = build_large_ast(10000_nodes)
start = Time.monotonic
100.times do
  json = ast.to_json
  parsed = AST.from_json(json)
end
elapsed = Time.monotonic - start
```

**Métricas:**
- Velocidade de serialização
- Velocidade de deserialização
- Tamanho em disco/rede
- Zero-copy capabilities

---

### 6. **Matching Semântico**
**Objetivo:** Testar pattern matching avançado com regras semânticas.

```rust
let patterns = generate_patterns(1000);
let terms = generate_terms(50000);
let start = Instant::now();
for term in terms {
    for pattern in patterns {
        semantic_match(&pattern, &term);
    }
}
```

**Métricas:**
- Backtracking cost
- Unification performance
- Alpha-equivalence checking

---

### 7. **Resolução de Dependências**
**Objetivo:** Medir performance em graph traversal e topological sort.

```crystal
deps = build_dependency_graph(5000_nodes, 15000_edges)
start = Time.monotonic
order = deps.topological_sort
cycles = deps.detect_cycles
elapsed = Time.monotonic - start
```

**Métricas:**
- Graph construction time
- Topological sort speed
- Cycle detection accuracy
- Memory para grafos grandes

---

### 8. **Execução de Regras**
**Objetivo:** Avaliar engine de reescrita de termos (term rewriting).

```rust
let rules = load_rewrite_rules(500);
let mut term = generate_complex_term();
let start = Instant::now();
for _ in 0..1000 {
    term = apply_rules(&term, &rules);
}
```

**Métricas:**
- Regras aplicadas por segundo
- Conflito de regras (critical pairs)
- Terminação guarantee overhead

---

### 9. **Tool Chaining**
**Objetivo:** Medir custo de pipeline de ferramentas (parser → IR → optimizer → codegen).

```crystal
source_files = load_files(100)
start = Time.monotonic
source_files.each do |file|
  ast = Parser.parse(file)
  ir = IRBuilder.build(ast)
  optimized = Optimizer.run(ir)
  output = CodeGen.generate(optimized)
end
elapsed = Time.monotonic - start
```

**Métricas:**
- Latência do pipeline completo
- Throughput (arquivos/segundo)
- Memory pressure entre estágios

---

### 10. **Memória/Latência**
**Objetivo:** Profile detalhado de alocação e garbage collection.

```rust
let scenarios = [
    ("small_allocs", || allocate_many_small_objects()),
    ("large_allocs", || allocate_few_large_objects()),
    ("mixed", || allocate_mixed_workload()),
];

for (name, workload) in scenarios {
    let before = get_memory_stats();
    workload();
    let after = get_memory_stats();
    report(name, before, after);
}
```

**Métricas:**
- Alocações por segundo
- GC pause times (se aplicável)
- Fragmentação de heap
- Peak memory usage

---

### 11. **Concorrência**
**Objetivo:** Testar paralelização de workloads do DICE-L.

```crystal
tasks = generate_independent_tasks(1000)
start = Time.monotonic
results = tasks.map_with_pool(8) { |task| execute(task) }
elapsed = Time.monotonic - start
speedup = sequential_time / elapsed
```

**Métricas:**
- Speedup com N threads
- Contention em estruturas compartilhadas
- Lock-free performance
- Thread safety guarantees

---

### 12. **Cold Start**
**Objetivo:** Medir tempo de inicialização (importante para CLI/tools).

```rust
let start = Instant::now();
let runtime = DICELRuntime::initialize();
let parser = Parser::new();
let optimizer = Optimizer::load_rules();
let elapsed = start.elapsed();
```

**Métricas:**
- Tempo até primeira operação útil
- Tamanho do binário
- Dependências carregadas
- Lazy loading effectiveness

---

### 13. **Throughput Sustentado**
**Objetivo:** Medir performance em execução prolongada (steady state).

```crystal
duration = 60.seconds
start = Time.monotonic
operations = 0
while Time.monotonic - start < duration
  execute_random_lin_operation()
  operations += 1
end
throughput = operations / duration.seconds
```

**Métricas:**
- Operações/segundo sustentadas
- Thermal throttling impact
- Memory leaks detection
- Stability over time

---

### 14. **Consumo de RAM**
**Objetivo:** Profile detalhado de uso de memória em diferentes cenários.

```rust
let scenarios = [
    ("empty_runtime", Runtime::new()),
    ("small_project", load_project(10_files)),
    ("medium_project", load_project(100_files)),
    ("large_project", load_project(1000_files)),
];

for scenario in scenarios {
    let mem_before = get_rss();
    scenario.execute();
    let mem_after = get_rss();
    let peak = get_peak_memory();
    report(scenario.name, mem_before, mem_after, peak);
}
```

**Métricas:**
- Resident Set Size (RSS)
- Virtual memory usage
- Swap activity
- Memory efficiency (bytes por nó AST)

---

## 🏆 Critérios de Avaliação

Cada linguagem será pontuada em uma escala de 1-5 em cada dimensão:

| Pontuação | Significado |
|-----------|-------------|
| 5 | Excelente - Ideal para produção |
| 4 | Muito Bom - Pequenas otimizações necessárias |
| 3 | Bom - Aceitável com trade-offs |
| 2 | Regular - Problemas significativos |
| 1 | Ruim - Inviável para este caso de uso |

### Peso das Dimensões (para DICE-L):

| Dimensão | Peso | Justificativa |
|----------|------|---------------|
| HashCons | 3x | Crítico para normalização |
| Matching Semântico | 3x | Core do LIN |
| Memória/Latência | 2x | Previsibilidade essencial |
| Execução de Regras | 2x | Motor de reescrita |
| Parsing/IR | 2x | Pipeline fundamental |
| Concorrência | 1x | Importante mas não crítico |
| Cold Start | 1x | Relevante para UX |
| Throughput | 2x | Performance sustentada |
| Consumo RAM | 2x | Escalabilidade |

---

## 📈 Matriz de Decisão

Ao final dos benchmarks, cada linguagem receberá uma **pontuação ponderada**:

```
Score_final = Σ(peso_i × nota_i) / Σ(peso_i)
```

### Thresholds de Decisão:

| Score | Recomendação |
|-------|--------------|
| ≥ 4.5 | **Altamente Recomendado** - Adotar como núcleo |
| 3.5-4.4 | **Recomendado** - Bom candidato, validar com PoC |
| 2.5-3.4 | **Neutro** - Considerar apenas se houver outros fatores |
| < 2.5 | **Não Recomendado** - Descartar para núcleo crítico |

---

## 🧪 Implementação dos Benchmarks

### Estrutura Proposta:

```
benchmarks/
├── README.md
├── common/
│   ├── generators.cr      # Geradores de dados de teste
│   ├── metrics.cr         # Coleta de métricas
│   └── reporters.cr       # Formatação de resultados
├── crystal/
│   ├── 01_parsing.cr
│   ├── 02_ir_builder.cr
│   ├── 03_hashcons.cr
│   └── ...
├── rust/
│   ├── 01_parsing.rs
│   ├── 02_ir_builder.rs
│   ├── 03_hashcons.rs
│   └── ...
├── run_all.sh             # Script para executar tudo
└── compare_results.py     # Análise comparativa
```

### Requisitos de Implementação:

1. **Equivalência:** Cada benchmark deve ser semanticamente idêntico entre linguagens
2. **Isolamento:** Cada teste roda em processo separado para evitar contaminação
3. **Repetição:** Cada benchmark roda 5-10 vezes, reporta média e desvio padrão
4. **Warmup:** 2-3 execuções de aquecimento antes de medir
5. **Ambiente Controlado:** Mesma máquina, sem outros processos pesados

---

## 🔍 Análise Qualitativa Além de Performance

Além dos números brutos, considerar:

### Fatores Subjetivos (peso 20% na decisão final):

| Fator | Questões a Responder |
|-------|---------------------|
| **Ergonomia** | Quão produtivo é desenvolver nesta linguagem? |
| **Curva de Aprendizado** | Quanto tempo para equipe dominar? |
| **Ecossistema** | Bibliotecas disponíveis para necessidades do DICE-L? |
| **Comunidade** | Suporte ativo? Long-term viability? |
| **Tooling** | Debugger, profiler, IDE support? |
| **Segurança** | Memory safety, type safety guarantees? |
| **Interoperabilidade** | FFI com C, Python, outras linguagens? |
| **Deployment** | Facilidade de distribuir binários/runtime? |

---

## 📅 Cronograma Sugerido

| Semana | Atividade |
|--------|-----------|
| 1 | Implementar benchmarks 1-5 em Crystal e Rust |
| 2 | Implementar benchmarks 6-10 em Crystal e Rust |
| 3 | Implementar benchmarks 11-14 + executar todos |
| 4 | Expandir para outras linguagens candidatas (Zig, OCaml, etc) |
| 5 | Análise estatística dos resultados |
| 6 | Redação do relatório final e recomendação |

---

## 🎯 Próximos Passos Imediatos

1. ✅ **Definir especificação detalhada** de cada benchmark (este documento)
2. ⏳ **Implementar versão de referência** em Crystal (linguagem mais produtiva)
3. ⏳ **Portar para Rust** mantendo equivalência exata
4. ⏳ **Executar suite completa** e coletar dados
5. ⏳ **Analisar resultados** com estatística apropriada
6. ⏳ **Tomar decisão** baseada em dados + fatores qualitativos

---

## 📝 Notas Importantes

### Sobre o Benchmark de Fibonacci

O teste `fib(n)` foi útil como **prova de conceito inicial**, mostrando que:
- Rust compete com C/C++ em performance bruta
- Crystal oferece bom equilíbrio entre sintaxe e performance
- Linguagens interpretadas (Python, Ruby) têm limitações sérias em CPU-bound

**Porém**, para decidir o núcleo do DICE-L, precisamos de dados muito mais representativos.

### Por Que Esta Suite é Melhor

Esta suite:
- ✅ Testa operações **reais do DICE-L**
- ✅ Mede **múltiplas dimensões** de performance
- ✅ Considera **trade-offs** entre velocidade, memória e segurança
- ✅ Inclui fatores **qualitativos** de desenvolvimento
- ✅ Produz dados **acionáveis** para decisão arquitetural

---

## 🔗 Referências

- [The Computer Language Benchmarks Game](https://benchmarksgame.alioth.debian.org/)
- [Rust Performance Book](https://nnethercote.github.io/perf-book/)
- [Crystal Performance Tips](https://crystal-lang.org/reference/guides/performance.html)
- [Hash Consing in Practice](https://en.wikipedia.org/wiki/Hash_consing)

---

**Status:** ✅ Plano definido  
**Próximo:** Implementar benchmarks em Crystal (referência) e Rust
