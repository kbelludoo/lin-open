#!/usr/bin/env node
/**
 * Benchmark & Demonstration of LIN In-Memory Execution.
 */
import fs from 'node:fs';
import { runLinInMemory } from '../src/lin_memory_runner.mjs';

const linSample = `
@v=1
!fn add(a, b) ^ a + b
!fn pad(str, len, ch=" ") {
  $pad = ch || " "
  $res = "" + str
  # (; res.length < len; ) res = pad + res
  ^ res
}
`;

console.log('=== TESTANDO LIN EXECUÇÃO IN-MEMORY (ZERO DISK I/O) ===\n');

const res = runLinInMemory(linSample);

console.log('Código compilado em memória:');
console.log(res.compiledCode);
console.log('\n--- Métricas de Execução ---');
console.log(`Tempo de Compilação + Carga: ${res.latencyMs} ms`);
console.log(`Footprint do Código: ${res.memoryFootprintBytes} bytes`);

if (res.exports.add) {
  console.log('\n--- Invocando Funções do LIN Carregadas na Memória ---');
  console.log(`add(10, 25) = ${res.exports.add(10, 25)}`);
  console.log(`pad("42", 6, "0") = "${res.exports.pad("42", 6, "0")}"`);
}
console.log('\n======================================================');
