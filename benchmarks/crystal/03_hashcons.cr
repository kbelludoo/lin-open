# Benchmark 03: HashCons (Hash Consing)
# Testa deduplicação estrutural de termos via hash consing
# Crítico para normalização no DICE-L

require "./../common/metrics"

puts "=" * 60
puts "BENCHMARK 03: HashCons"
puts "=" * 60
puts ""

# Gera 50.000 termos (com repetições para testar deduplicação)
terms = BenchUtils.generate_terms(50_000)

# Implementação de HashCons
class HashCons
  @hash_table = {} of Int64 => Term
  @counter = 0

  def intern(term : Term) : Term
    hash = compute_hash(term)
    
    if existing = @hash_table[hash]?
      # Termo já existe, retorna o existente (deduplicação)
      existing
    else
      # Novo termo, armazena e retorna
      @hash_table[hash] = term
      @counter += 1
      term
    end
  end

  def unique_count : Int32
    @hash_table.size
  end

  def total_count : Int32
    @counter
  end

  private def compute_hash(term : Term) : Int64
    # Hash baseado na estrutura do termo (evita overflow)
    h1 = term.kind.to_s.hash
    h2 = term.name.hash
    h3 = term.value
    hash = ((h1 ^ h2 ^ h3) & 0x7FFFFFFF).to_i64
    term.args.each { |arg| hash = (hash ^ arg.hash) & 0x7FFFFFFF_i64 }
    hash
  end
end

# Warmup
puts "Warmup..."
warmup_terms = terms.first(1000)
hashcons_warmup = HashCons.new
warmup_terms.each { |term| hashcons_warmup.intern(term) }

# Benchmark principal
puts "\nExecutando benchmark (10 iterações)..."
times = [] of Float64
dedup_results = [] of Float64

10.times do |iteration|
  hashcons = HashCons.new
  
  start = Time.monotonic
  
  terms.each do |term|
    hashcons.intern(term)
  end
  
  elapsed = (Time.monotonic - start).total_milliseconds
  times << elapsed
  
  dedup_ratio = terms.size.to_f / hashcons.unique_count.to_f
  dedup_results << dedup_ratio
  
  puts "  Iteração #{iteration + 1}: #{elapsed.round(2)}ms, Dedup ratio: #{dedup_ratio.round(2)}x"
end

# Estatísticas
avg_time = times.sum / times.size
min_time = times.min
max_time = times.max
stddev_time = Math.sqrt(times.map { |t| (t - avg_time) ** 2 }.sum / times.size)

avg_dedup = dedup_results.sum / dedup_results.size
throughput = (terms.size * 10) / (times.sum / 1000)

puts "\n" + "=" * 60
puts "RESULTADOS"
puts "=" * 60
puts "Termos processados: #{terms.size * 10}"
puts "Tempo médio: #{avg_time.round(2)}ms"
puts "Tempo mínimo: #{min_time.round(2)}ms"
puts "Tempo máximo: #{max_time.round(2)}ms"
puts "Desvio padrão: #{stddev_time.round(2)}ms"
puts "Throughput: #{throughput.round(0)} termos/segundo"
puts "Taxa de deduplicação média: #{avg_dedup.round(2)}x"
puts "Tempo por intern: #{(avg_time / terms.size * 1000).round(3)}µs"

# Coleta stats de memória
mem_stats = BenchUtils.get_memory_stats
puts "\nUso de memória:"
puts "  RSS: #{mem_stats[:rss].round(2)}MB"
puts "  Peak: #{mem_stats[:peak].round(2)}MB"

# Salva resultado para comparação posterior
File.write("results_03_hashcons.txt", <<-RESULT
Benchmark: 03_HashCons
Language: Crystal
Terms: #{terms.size * 10}
Avg_ms: #{avg_time.round(4)}
Min_ms: #{min_time.round(4)}
Max_ms: #{max_time.round(4)}
StdDev: #{stddev_time.round(4)}
Throughput: #{throughput.round(2)}
DedupRatio: #{avg_dedup.round(4)}
Memory_MB: #{mem_stats[:rss].round(2)}
RESULT
)

puts "\n✅ Resultados salvos em results_03_hashcons.txt"
