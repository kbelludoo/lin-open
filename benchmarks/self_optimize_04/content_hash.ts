// content_hash module - TypeScript variant for SELF-OPTIMIZE-04
// Based on src/content_hash.compiled.mjs with type annotations

import { createHash } from 'node:crypto';

interface Fn {
  name: string;
  params: string;
  body: string;
}

interface ContentEntry {
  name: string;
  params: string;
  hash: string;
  bodyLen: number;
}

export function canonicalize(fnName: string, params: string, body: string): string {
  let canon: string = String(body || '').trim();
  canon = canon.replace(/\s+/g, ' ');
  
  const paramList: string[] = String(params || '').split(',');
  const clean: string[] = [];
  
  for (let i = 0; i < paramList.length; i++) {
    const p: string = paramList[i].trim().replace(/:.+$/, '');
    if (p) {
      clean.push(p);
    }
  }
  
  for (let j = 0; j < clean.length; j++) {
    const re_: RegExp = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re_, '$' + j);
  }
  
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '==').replace(/!==/g, '!=');
  canon = canon.replace(/;\s*/g, ';');
  
  return '(' + clean.length + ')' + canon;
}

export function contentHash(fnName: string, params: string, body: string): string {
  const canonical: string = canonicalize(fnName, params, body);
  const hash: string = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

export function semanticEquals(fn1: Fn, fn2: Fn): boolean {
  const h1: string = contentHash(fn1.name, fn1.params, fn1.body);
  const h2: string = contentHash(fn2.name, fn2.params, fn2.body);
  return h1 === h2;
}

export function buildContentRegistry(fns: Fn[]): Record<string, ContentEntry> {
  const registry: Record<string, ContentEntry> = {};
  for (let i = 0; i < fns.length; i++) {
    const fn: Fn = fns[i];
    const hash: string = contentHash(fn.name, fn.params, fn.body);
    registry[hash] = {
      name: fn.name,
      params: fn.params,
      hash: hash,
      bodyLen: (fn.body || '').length
    };
  }
  return registry;
}

// Benchmark runner
const ITERATIONS: number = 10000;

const workload: Fn[] = [
  { name: 'canonicalize', params: 'fnName,params,body', body: 'canon=String(body).trim()' },
  { name: 'contentHash', params: 'fnName,params,body', body: 'canonical=canonicalize(fnName,params,body)' },
  { name: 'semanticEquals', params: 'fn1,fn2', body: 'h1=contentHash(fn1.name,fn1.params,fn1.body)' },
  { name: 'buildContentRegistry', params: 'prog', body: 'registry={};fns=prog.fns' },
  { name: 'walkAst', params: 'node,visitor', body: 'if(node==null){return null}' },
  { name: 'transformAst', params: 'node,transformer', body: 'if(node==null){return null}' },
  { name: 'astNode', params: 'type,value,children', body: 'return ({type:type,value:value})' },
  { name: 'astFn', params: 'name,params,body', body: 'return astNode("fn",name,params)' },
  { name: 'inferEffects', params: 'body', body: 'effects=[];s=String(body)' },
  { name: 'checkRefinement', params: 'param,constraintText,errors', body: 'parts=constraintText.split(",")' },
];

// Phase 1: canonicalize
console.log('=== Phase 1: canonicalize ===');
let start: number = performance.now();
for (let iter = 0; iter < ITERATIONS; iter++) {
  for (const fn of workload) {
    canonicalize(fn.name, fn.params, fn.body);
  }
}
let elapsed: number = performance.now() - start;
let total: number = ITERATIONS * workload.length;
console.log(`  ${total} calls: ${elapsed.toFixed(2)}ms`);
console.log(`  Per call: ${(elapsed * 1000 / total).toFixed(2)}us`);

// Phase 2: contentHash
console.log('=== Phase 2: contentHash ===');
start = performance.now();
for (let iter = 0; iter < ITERATIONS; iter++) {
  for (const fn of workload) {
    contentHash(fn.name, fn.params, fn.body);
  }
}
elapsed = performance.now() - start;
console.log(`  ${total} calls: ${elapsed.toFixed(2)}ms`);
console.log(`  Per call: ${(elapsed * 1000 / total).toFixed(2)}us`);

// Phase 3: semanticEquals
console.log('=== Phase 3: semanticEquals ===');
start = performance.now();
for (let iter = 0; iter < ITERATIONS; iter++) {
  for (let j = 0; j < workload.length - 1; j++) {
    semanticEquals(workload[j], workload[j + 1]);
  }
}
elapsed = performance.now() - start;
const totalSE: number = ITERATIONS * (workload.length - 1);
console.log(`  ${totalSE} calls: ${elapsed.toFixed(2)}ms`);
console.log(`  Per call: ${(elapsed * 1000 / totalSE).toFixed(2)}us`);

// Phase 4: buildContentRegistry
console.log('=== Phase 4: buildContentRegistry ===');
start = performance.now();
for (let iter = 0; iter < ITERATIONS; iter++) {
  buildContentRegistry(workload);
}
elapsed = performance.now() - start;
console.log(`  ${ITERATIONS} calls: ${elapsed.toFixed(2)}ms`);
console.log(`  Per call: ${(elapsed * 1000 / ITERATIONS).toFixed(2)}us`);

// Oracle
console.log('\n=== Oracle: Semantic Output ===');
console.log('Oracle hashes:');
for (const fn of workload) {
  const hash: string = contentHash(fn.name, fn.params, fn.body);
  console.log(`  ${fn.name}: ${hash}`);
}

// Determinism
console.log('\n=== Determinism Check ===');
const oracle1: string[] = workload.map((fn: Fn) => contentHash(fn.name, fn.params, fn.body));
const oracle2: string[] = workload.map((fn: Fn) => contentHash(fn.name, fn.params, fn.body));
console.log(`  Deterministic: ${JSON.stringify(oracle1) === JSON.stringify(oracle2)}`);
