import times, strformat, math

# Fibonacci recursivo simples
proc fib(n: int): int64 =
  if n <= 1:
    return n.int64
  result = fib(n - 1) + fib(n - 2)

when isMainModule:
  echo "🔺 Nim Fibonacci Benchmark"
  echo ""
  
  let n = 40
  const iterations = 5
  
  echo fmt"Calculando fib({n})..."
  echo ""
  
  var runTimes: array[5, float]
  
  for i in 0..<iterations:
    let startTime = cpuTime()
    let result = fib(n)
    let endTime = cpuTime()
    
    let elapsed = (endTime - startTime) * 1000.0 # ms
    runTimes[i] = elapsed
    
    echo fmt"  Run {i+1}: fib({n}) = {result} | Tempo: {elapsed:.2f}ms"
  
  # Calcular média
  var total = 0.0
  for t in runTimes:
    total += t
  let avg = total / float(iterations)
  
  echo ""
  echo fmt"⏱️  Tempo médio: {avg:.2f}ms"
  echo fmt"📊 Throughput: {1000.0 / avg:.0f} iterações/s"
  echo ""
