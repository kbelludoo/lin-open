#!/usr/bin/env node
/**
 * LIN Target Comparator CLI & Benchmark.
 * Compares emitted code across all 17 targets and recommends the optimal one.
 */
import fs from 'node:fs';
import path from 'node:path';
import { evaluateTargets, PROFILES } from '../src/target_selector.mjs';

const args = process.argv.slice(2);
const file = args[0] || 'spec/LIA_AGENT_RULE.dicel';
const profileArg = args.find((a) => a.startsWith('--profile='))?.split('=')[1] || 'performance';

if (!fs.existsSync(file)) {
  console.error(`Arquivo não encontrado: ${file}`);
  process.exit(1);
}

const content = fs.readFileSync(file, 'utf8');
const result = evaluateTargets(content, profileArg);

console.log(`\n================ LIN TARGET COMPARATOR ================`);
console.log(`Arquivo analisado: ${path.basename(file)}`);
console.log(`Perfil selecionado: ${result.profile}`);
console.log(`Alvo Recomendado: \x1b[32m${result.recommendedTarget.toUpperCase()}\x1b[0m\n`);

console.log('| Target    | Score | Bytes | Linhas | Est. Tokens |');
console.log('|-----------|-------|-------|--------|-------------|');
for (const ev of result.evaluations) {
  if (ev.error) {
    console.log(`| ${ev.target.padEnd(9)} |  FAIL | ${ev.error.slice(0, 30)} |`);
  } else {
    console.log(
      `| ${ev.target.padEnd(9)} | ${String(ev.score).padStart(5)} | ${String(ev.bytes).padStart(5)} | ${String(ev.lines).padStart(6)} | ${String(ev.tokensEst).padStart(11)} |`
    );
  }
}
console.log(`=======================================================\n`);
