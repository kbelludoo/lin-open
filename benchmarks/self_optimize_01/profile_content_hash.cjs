const { canonicalize, contentHash, semanticEquals, buildContentRegistry } = require('../../src/content_hash.compiled.cjs');

const ITERATIONS = 10000;

// Simpler workload - avoid string escaping issues
const workload = [
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

// Phase 1: canonicalize benchmark
console.log('=== Phase 1: canonicalize ===');
let start = process.hrtime.bigint();
for (let i = 0; i < ITERATIONS; i++) {
  for (const fn of workload) {
    canonicalize(fn.name, fn.params, fn.body);
  }
}
let elapsed = Number(process.hrtime.bigint() - start) / 1e6;
console.log('  ' + (ITERATIONS * workload.length) + ' calls: ' + elapsed.toFixed(2) + 'ms');
console.log('  Per call: ' + (elapsed / (ITERATIONS * workload.length) * 1000).toFixed(2) + 'us');

// Phase 2: contentHash benchmark
console.log('=== Phase 2: contentHash ===');
start = process.hrtime.bigint();
for (let i = 0; i < ITERATIONS; i++) {
  for (const fn of workload) {
    contentHash(fn.name, fn.params, fn.body);
  }
}
elapsed = Number(process.hrtime.bigint() - start) / 1e6;
console.log('  ' + (ITERATIONS * workload.length) + ' calls: ' + elapsed.toFixed(2) + 'ms');
console.log('  Per call: ' + (elapsed / (ITERATIONS * workload.length) * 1000).toFixed(2) + 'us');

// Phase 3: semanticEquals benchmark
console.log('=== Phase 3: semanticEquals ===');
start = process.hrtime.bigint();
for (let i = 0; i < ITERATIONS; i++) {
  for (let j = 0; j < workload.length - 1; j++) {
    semanticEquals(workload[j], workload[j + 1]);
  }
}
elapsed = Number(process.hrtime.bigint() - start) / 1e6;
console.log('  ' + (ITERATIONS * (workload.length - 1)) + ' calls: ' + elapsed.toFixed(2) + 'ms');
console.log('  Per call: ' + (elapsed / (ITERATIONS * (workload.length - 1)) * 1000).toFixed(2) + 'us');

// Phase 4: buildContentRegistry benchmark
console.log('=== Phase 4: buildContentRegistry ===');
const prog = { fns: workload.map(function(f) { return { name: f.name, params: f.params, body: f.body }; }) };
start = process.hrtime.bigint();
for (let i = 0; i < ITERATIONS; i++) {
  buildContentRegistry(prog);
}
elapsed = Number(process.hrtime.bigint() - start) / 1e6;
console.log('  ' + ITERATIONS + ' calls: ' + elapsed.toFixed(2) + 'ms');
console.log('  Per call: ' + (elapsed / ITERATIONS * 1000).toFixed(2) + 'us');

// Phase 5: Semantic output verification (oracle)
console.log('\n=== Oracle: Semantic Output ===');
var oracle = {};
for (var k = 0; k < workload.length; k++) {
  var fn = workload[k];
  oracle[fn.name] = contentHash(fn.name, fn.params, fn.body);
}
console.log('Oracle hashes:');
var keys = Object.keys(oracle);
for (var m = 0; m < keys.length; m++) {
  console.log('  ' + keys[m] + ': ' + oracle[keys[m]]);
}

// Verify determinism
console.log('\n=== Determinism Check ===');
var oracle2 = {};
for (var n = 0; n < workload.length; n++) {
  var fn2 = workload[n];
  oracle2[fn2.name] = contentHash(fn2.name, fn2.params, fn2.body);
}
var deterministic = JSON.stringify(oracle) === JSON.stringify(oracle2);
console.log('  Deterministic: ' + deterministic);
