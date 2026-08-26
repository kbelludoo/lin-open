# Benchmark 01: Parsing de AST
# Testa performance na análise sintática de expressões LIN

require "./../common/metrics"

puts "=" * 60
puts "BENCHMARK 01: Parsing de AST"
puts "=" * 60
puts ""

# Gera 10.000 expressões LIN para parsing
expressions = BenchUtils.generate_lin_expressions(10_000)

# Simula parser (na implementação real, usaria o parser LIN verdadeiro)
class SimpleParser
  def self.parse(expr : String) : ParsedResult
    # Parser simplificado para benchmark
    # Na implementação real, faria análise sintática completa
    ParsedResult.new(
      success: true,
      tokens: expr.split.size,
      depth: expr.count('{') + expr.count('(')
    )
  end
end

struct ParsedResult
  getter success : Bool
  getter tokens : Int32
  getter depth : Int32

  def initialize(@success, @tokens, @depth)
  end
end

# Warmup
puts "Warmup..."
5.times do
  expressions.first(100).each { |expr| SimpleParser.parse(expr) }
end

# Benchmark principal
puts "\nExecutando benchmark (10 iterações)..."
times = [] of Float64
parsed_count = 0

10.times do |iteration|
  start = Time.monotonic
  
  expressions.each do |expr|
    result = SimpleParser.parse(expr)
    parsed_count += 1 if result.success
  end
  
  elapsed = (Time.monotonic - start).total_milliseconds
  times << elapsed
  puts "  Iteração #{iteration + 1}: #{elapsed.round(2)}ms"
end

# Estatísticas
avg = times.sum / times.size
min = times.min
max = times.max
stddev = Math.sqrt(times.map { |t| (t - avg) ** 2 }.sum / times.size)
throughput = (expressions.size * 10) / (times.sum / 1000)

puts "\n" + "=" * 60
puts "RESULTADOS"
puts "=" * 60
puts "Expressões processadas: #{parsed_count}"
puts "Tempo médio: #{avg.round(2)}ms"
puts "Tempo mínimo: #{min.round(2)}ms"
puts "Tempo máximo: #{max.round(2)}ms"
puts "Desvio padrão: #{stddev.round(2)}ms"
puts "Throughput: #{throughput.round(0)} expressões/segundo"
puts "Parsing por expressão: #{(avg / expressions.size * 1000).round(3)}µs"

# Coleta stats de memória
mem_stats = BenchUtils.get_memory_stats
puts "\nUso de memória:"
puts "  RSS: #{mem_stats[:rss].round(2)}MB"
puts "  Peak: #{mem_stats[:peak].round(2)}MB"

# Salva resultado para comparação posterior
File.write("results_01_parsing.txt", <<-RESULT
Benchmark: 01_Parsing
Language: Crystal
Expressions: #{parsed_count}
Avg_ms: #{avg.round(4)}
Min_ms: #{min.round(4)}
Max_ms: #{max.round(4)}
StdDev: #{stddev.round(4)}
Throughput: #{throughput.round(2)}
Memory_MB: #{mem_stats[:rss].round(2)}
RESULT
)

puts "\n✅ Resultados salvos em results_01_parsing.txt"
