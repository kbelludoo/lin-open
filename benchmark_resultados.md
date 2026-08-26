# Benchmark de Fibonacci - Comparação entre Linguagens

Teste: Cálculo recursivo de fib(40) = 102334155
(exeto Ruby e Python que usaram fib(35) = 9227465 devido à lentidão)

## Resultados (tempo de execução em ms):

| Linguagem      | Versão         | Tempo (ms) | Categoria     |
|----------------|----------------|------------|---------------|
| **C**          | GCC            | ~249       | Compilada Nativa |
| **C++**        | G++ -O2        | ~263       | Compilada Nativa |
| **Rust**       | rustc 1.63 -O  | ~270       | Compilada Nativa |
| **Java**       | OpenJDK        | ~446       | JVM           |
| **Go**         | go run         | ~664       | Compilada Nativa |
| **Crystal**    | crystal --release | ~614    | Compilada Nativa |
| **JavaScript** | Node.js        | ~1400      | Interpretada/JIT |
| **Ruby**       | ruby 3.1       | ~1088*     | Interpretada  |
| **Python**     | python3        | ~1624*     | Interpretada  |

*Ruby e Python testados com fib(35) ao invés de fib(40)

## Análise por Categoria:

### 🥇 Líderes de Performance (< 300ms)
1. **C** - Mais rápido, controle total de memória
2. **C++** - Quase igual ao C, com abstrações
3. **Rust** - Performance similar a C/C++, com segurança de memória

### 🥈 Performance Intermediária (400-700ms)
4. **Java** - JVM madura, bom JIT
5. **Crystal** - Sintaxe Ruby-like, performance próxima de C
6. **Go** - Compilação rápida, concorrência nativa

### 🥉 Performance Moderada (> 1000ms)
7. **Ruby** - Flexível, mas lento para computação intensiva
8. **JavaScript (Node.js)** - V8 JIT ajuda, mas ainda limitado
9. **Python** - Mais lento, ótimo para prototipagem

## Conclusões:

- **Crystal** surpreende: sintaxe elegante com performance 2.5x melhor que Ruby
- **Rust** mantém promessa: performance C++ com segurança de memória
- **Linguagens compiladas** (C, C++, Rust) dominam em performance bruta
- **Interpretadas** (Python, Ruby) são mais lentas mas ótimas para desenvolvimento rápido

