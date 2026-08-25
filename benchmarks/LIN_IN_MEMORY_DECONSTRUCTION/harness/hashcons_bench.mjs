// HashCons Microsecond-Precision Benchmark
// Measures cold vs warm symbol lookup latencies (p50, p95, p99)

export function benchmarkHashConsLookups(totalSymbols = 1000, totalQueries = 50000) {
  // 1. Build Canonical HashCons Memory Map
  const symbolMap = new Map();
  const symbolNames = [];

  for (let i = 0; i < totalSymbols; i++) {
    const sym = `mod_${Math.floor(i / 10)}_fn_${i % 10}`;
    const node = {
      id: `0x${i.toString(16).padStart(8, '0')}`,
      name: sym,
      module: `mod_${Math.floor(i / 10)}`,
      contracts: ['ret !== undefined'],
      effect: 'Pure',
      callees: [`fn_${(i + 1) % totalSymbols}`]
    };
    symbolMap.set(sym, node);
    symbolNames.push(sym);
  }

  // 2. Measure Cold Lookup Latencies (First 1,000 accesses)
  const coldLatenciesNs = [];
  for (let i = 0; i < 1000; i++) {
    const query = symbolNames[i];
    const t0 = process.hrtime.bigint();
    const res = symbolMap.get(query);
    const t1 = process.hrtime.bigint();
    if (res) coldLatenciesNs.push(Number(t1 - t0));
  }

  // 3. Measure Warm Steady-State Lookups (50,000 queries)
  const warmLatenciesNs = [];
  const tStartWarm = performance.now();
  for (let i = 0; i < totalQueries; i++) {
    const query = symbolNames[i % symbolNames.length];
    const t0 = process.hrtime.bigint();
    const res = symbolMap.get(query);
    const t1 = process.hrtime.bigint();
    if (res) warmLatenciesNs.push(Number(t1 - t0));
  }
  const warmTotalMs = performance.now() - tStartWarm;

  // Calculate percentiles
  warmLatenciesNs.sort((a, b) => a - b);
  const p50Ns = warmLatenciesNs[Math.floor(warmLatenciesNs.length * 0.50)];
  const p95Ns = warmLatenciesNs[Math.floor(warmLatenciesNs.length * 0.95)];
  const p99Ns = warmLatenciesNs[Math.floor(warmLatenciesNs.length * 0.99)];
  const avgNs = warmLatenciesNs.reduce((a, b) => a + b, 0) / warmLatenciesNs.length;

  return {
    total_symbols_indexed: totalSymbols,
    total_queries: totalQueries,
    throughput_lookups_per_sec: Math.round(totalQueries / (warmTotalMs / 1000)),
    cold_lookup_avg_us: Number((coldLatenciesNs.reduce((a, b) => a + b, 0) / coldLatenciesNs.length / 1000).toFixed(3)),
    warm_lookup_p50_us: Number((p50Ns / 1000).toFixed(3)),
    warm_lookup_p95_us: Number((p95Ns / 1000).toFixed(3)),
    warm_lookup_p99_us: Number((p99Ns / 1000).toFixed(3)),
    warm_lookup_avg_us: Number((avgNs / 1000).toFixed(3))
  };
}
