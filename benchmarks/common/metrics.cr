# Common/Benchmark Utilities for Crystal

module BenchUtils
  # Gera expressões LIN sintéticas para teste de parsing
  def self.generate_lin_expressions(count : Int32) : Array(String)
    templates = [
      "let x{i} = {val}",
      "fn f{i}(x) = x + {val}",
      "if x > {val} then y else z",
      "match x with | Some(v) -> v | None -> {val}",
      "{val} |> fn x -> x * 2",
      "[1..{val}] |> map(fn x -> x^2)",
      "type T{i} = {{ field: Int, value: String }}",
    ]
    
    (1..count).map do |i|
      template = templates[i % templates.size]
      template.gsub("{i}", i.to_s).gsub("{val}", (i * 7).to_s)
    end
  end

  # Gera termos para hash consing
  def self.generate_terms(count : Int32) : Array(Term)
    (1..count).map do |i|
      Term.new(
        kind: i % 5 == 0 ? :var : :app,
        name: "t#{i}",
        args: i > 1 ? ["t#{i-1}", "t#{i-2}"] : [] of String,
        value: i * 13
      )
    end
  end

  # Gera grafo de dependências
  def self.build_dependency_graph(nodes : Int32, edges : Int32) : DependencyGraph
    graph = DependencyGraph.new
    nodes.times { |i| graph.add_node("node_#{i}") }
    
    edges.times do |i|
      from = "node_#{i % nodes}"
      to = "node_#{(i * 3 + 7) % nodes}"
      graph.add_edge(from, to) if from != to
    end
    
    graph
  end

  # Gera AST grande para serialização
  def self.build_large_ast(node_count : Int32) : ASTNode
    root = ASTNode.new(:root, "main")
    build_subtree(root, node_count, 0)
    root
  end

  private def self.build_subtree(parent : ASTNode, remaining : Int32, depth : Int32)
    return if remaining <= 0 || depth > 10
    
    children_count = [remaining // 10, 5].min
    children_count.times do |i|
      child = ASTNode.new(:expr, "expr_#{remaining}_#{i}")
      parent.add_child(child)
      build_subtree(child, remaining - i, depth + 1)
    end
  end

  # Mede tempo de execução com warmup
  macro measure(name, iterations = 5, warmup = 2)
    puts "Benchmark: #{name}"
    
    # Warmup
    {{warmup}}.times do
      {{yield}}
    end
    
    # Medição
    times = [] of Float64
    {{iterations}}.times do
      start = Time.monotonic
      {{yield}}
      elapsed = (Time.monotonic - start).total_milliseconds
      times << elapsed
    end
    
    avg = times.sum / times.size
    min = times.min
    max = times.max
    stddev = Math.sqrt(times.map { |t| (t - avg) ** 2 }.sum / times.size)
    
    puts "  Avg: #{avg.round(2)}ms, Min: #{min.round(2)}ms, Max: #{max.round(2)}ms, StdDev: #{stddev.round(2)}ms"
    puts "  Throughput: #{(1000.0 / avg).round(2)} ops/sec"
    
    { avg, min, max, stddev }
  end

  # Coleta stats de memória (Linux-specific)
  def self.get_memory_stats : NamedTuple(rss: Float64, peak: Float64)
    rss = 0.0
    peak = 0.0
    
    begin
      File.each_line("/proc/self/status") do |line|
        if line.starts_with?("VmRSS:")
          rss = line.split[1].to_f
        elsif line.starts_with?("VmHWM:")
          peak = line.split[1].to_f
        end
      end
    rescue
      # Fallback: valor zero se não conseguir ler
      rss = 0.0
      peak = 0.0
    end
    
    { rss: rss / 1024.0, peak: peak / 1024.0 } # KB -> MB
  end
end

# Estruturas de dados para benchmarks

class Term
  getter kind : Symbol
  getter name : String
  getter args : Array(String)
  getter value : Int32

  def initialize(@kind, @name, @args, @value)
  end

  def_hash @kind, @name, @args, @value
end

class DependencyGraph
  @nodes = {} of String => Set(String)
  @reverse = {} of String => Set(String)

  def add_node(name : String)
    @nodes[name] ||= Set(String).new
    @reverse[name] ||= Set(String).new
  end

  def add_edge(from : String, to : String)
    @nodes[from] ||= Set(String).new
    @reverse[to] ||= Set(String).new
    @nodes[from] << to
    @reverse[to] << from
  end

  def topological_sort : Array(String)
    visited = Set(String).new
    result = [] of String
    
    @nodes.keys.each do |node|
      visit(node, visited, result) if !visited.includes?(node)
    end
    
    result.reverse
  end

  private def visit(node : String, visited : Set(String), result : Array(String))
    return if visited.includes?(node)
    visited << node
    @nodes[node]?.each { |neighbor| visit(neighbor, visited, result) }
    result << node
  end

  def detect_cycles : Bool
    # Detecção simples de ciclos via DFS
    rec_stack = Set(String).new
    visited = Set(String).new
    
    @nodes.keys.any? do |node|
      has_cycle(node, visited, rec_stack)
    end
  end

  private def has_cycle(node : String, visited : Set(String), rec_stack : Set(String)) : Bool
    return false if visited.includes?(node)
    
    visited << node
    rec_stack << node
    
    @nodes[node]?.each do |neighbor|
      return true if !visited.includes?(neighbor) && has_cycle(neighbor, visited, rec_stack)
      return true if rec_stack.includes?(neighbor)
    end
    
    rec_stack.delete(node)
    false
  end
end

class ASTNode
  getter type : Symbol
  getter name : String
  getter children : Array(ASTNode)

  def initialize(@type, @name, @children = [] of ASTNode)
  end

  def add_child(child : ASTNode)
    @children << child
  end

  def to_json : String
    # Serialização JSON simplificada
    children_json = @children.map(&.to_json).join(",")
    "{\"type\":\"#{@type}\",\"name\":\"#{@name}\",\"children\":[#{children_json}]}"
  end

  def self.from_json(json : String) : ASTNode
    # Deserialização JSON simplificada (parser real seria mais complexo)
    # Esta é uma versão stub para benchmark
    ASTNode.new(:stub, "parsed")
  end
end
