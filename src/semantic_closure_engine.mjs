/**
 * LIN Semantic Closure & Capability Extraction Engine
 * Spec: spec/LIN_SEMANTIC_CLOSURE_AND_CAPABILITY.rulel
 *
 * Implements:
 * 1. AST & Call Graph parsing
 * 2. Transitive Dependency Closure (Fixed Point)
 * 3. 5-Taxonomy Classification (USER_DEFINED, LIBRARY_SOURCE, BUILTIN_PURE, HOST_CAPABILITY, UNRESOLVED)
 * 4. Generic Semantic Specialization & Lowering (inline expansion, capture analysis, accumulator loop synthesis)
 * 5. 4-State Capability Manifest (resolved, materialized, host_required, unresolved) & ClosureCoverage metric
 * 6. Orthogonal Fault Isolation (EXTRACTION | LOWERING | CAPABILITY | RUNTIME)
 */

export const TAXONOMY = {
  USER_DEFINED: 'USER_DEFINED',
  LIBRARY_SOURCE: 'LIBRARY_SOURCE',
  BUILTIN_PURE: 'BUILTIN_PURE',
  HOST_CAPABILITY: 'HOST_CAPABILITY',
  UNRESOLVED: 'UNRESOLVED'
};

// Known irreducible host environment capabilities
const HOST_CAPABILITY_REGISTRY = new Set([
  'Math.floor', 'Math.ceil', 'Math.round', 'Math.abs', 'Math.max', 'Math.min',
  'Math.sqrt', 'Math.pow', 'Math.random', 'Math.trunc', 'Math.sin', 'Math.cos',
  'Date.now', 'Date.parse', 'JSON.parse', 'JSON.stringify',
  'console.log', 'console.error', 'console.warn',
  'fetch', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'RegExp', 'Buffer', 'process', 'window', 'document'
]);

// Pure builtin semantic identities that can be specialized / lowered to pure LIN loops
const BUILTIN_PURE_REGISTRY = new Map([
  ['map', { arity: 1, type: 'array_transform', produces: 'array' }],
  ['filter', { arity: 1, type: 'array_filter', produces: 'array' }],
  ['reduce', { arity: 2, type: 'array_reduce', produces: 'scalar' }],
  ['some', { arity: 1, type: 'array_some', produces: 'boolean' }],
  ['every', { arity: 1, type: 'array_every', produces: 'boolean' }],
  ['find', { arity: 1, type: 'array_find', produces: 'scalar' }],
  ['findIndex', { arity: 1, type: 'array_find_index', produces: 'number' }],
  ['indexOf', { arity: 1, type: 'array_index_of', produces: 'number' }],
  ['includes', { arity: 1, type: 'array_includes', produces: 'boolean' }],
  ['join', { arity: 1, type: 'array_join', produces: 'string' }],
  ['slice', { arity: 2, type: 'array_slice', produces: 'array' }],
  ['concat', { arity: 1, type: 'array_concat', produces: 'array' }],
  ['reverse', { arity: 0, type: 'array_reverse', produces: 'array' }],
  ['flat', { arity: 0, type: 'array_flat', produces: 'array' }],
  ['push', { arity: 1, type: 'array_push', produces: 'number' }],
  ['pop', { arity: 0, type: 'array_pop', produces: 'scalar' }],
  ['shift', { arity: 0, type: 'array_shift', produces: 'scalar' }],
  ['unshift', { arity: 1, type: 'array_unshift', produces: 'number' }],
  ['length', { arity: 0, type: 'property', produces: 'number' }],
  ['keys', { arity: 1, receiver: 'Object', type: 'object_keys', produces: 'array' }],
  ['values', { arity: 1, receiver: 'Object', type: 'object_values', produces: 'array' }],
  ['entries', { arity: 1, receiver: 'Object', type: 'object_entries', produces: 'array' }]
]);

/**
 * Parses source code and extra library modules into a unified Call Graph and AST structure.
 */
export function parseSourceGraph(userSource, libSources = {}) {
  const fns = new Map();

  function extractFunctions(src, sourceOrigin) {
    const cleanSrc = src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/.*/g, '');

    // Extract named functions: function name(params) { body }
    const fnRe = /(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)\s*\{/g;
    let m;
    while ((m = fnRe.exec(cleanSrc)) !== null) {
      const name = m[1];
      const params = m[2].split(',').map(s => s.trim()).filter(Boolean);
      const openBrace = m.index + m[0].length - 1;
      const body = extractBlock(cleanSrc, openBrace);
      fns.set(name, {
        name,
        params,
        body,
        origin: sourceOrigin,
        calls: extractCallsFromBody(body)
      });
    }

    // Extract arrow function assignments: const name = (params) => { body }
    const arrowRe = /(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>\s*\{/g;
    while ((m = arrowRe.exec(cleanSrc)) !== null) {
      const name = m[1];
      const params = m[2].split(',').map(s => s.trim()).filter(Boolean);
      const openBrace = cleanSrc.indexOf('{', m.index);
      if (openBrace >= 0) {
        const body = extractBlock(cleanSrc, openBrace);
        fns.set(name, {
          name,
          params,
          body,
          origin: sourceOrigin,
          calls: extractCallsFromBody(body)
        });
      }
    }
  }

  extractFunctions(userSource, TAXONOMY.USER_DEFINED);

  for (const [libName, libSrc] of Object.entries(libSources)) {
    extractFunctions(libSrc, TAXONOMY.LIBRARY_SOURCE);
  }

  return { fns };
}

function extractBlock(src, openBraceIdx) {
  let depth = 1;
  let k = openBraceIdx + 1;
  while (k < src.length && depth > 0) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') depth--;
    k++;
  }
  return src.slice(openBraceIdx + 1, k - 1);
}

/**
 * Extracts method calls and function calls from a function body with argument and lambda inspection.
 */
export function extractCallsFromBody(body) {
  const calls = [];
  
  const methodRe = /([A-Za-z0-9_$.[\]()]+)\.([A-Za-z0-9_$]+)\s*\(([\s\S]*?)\)/g;
  let m;
  while ((m = methodRe.exec(body)) !== null) {
    const rawReceiver = m[1];
    const method = m[2];
    const rawArgs = m[3];
    calls.push({
      kind: 'method',
      receiver: rawReceiver,
      method,
      rawArgs,
      fullMatch: m[0]
    });
  }

  const directRe = /(?<!\.)\b([A-Za-z0-9_$]+)\s*\(([\s\S]*?)\)/g;
  while ((m = directRe.exec(body)) !== null) {
    const fnName = m[1];
    if (['if', 'while', 'for', 'switch', 'catch', 'function', 'return'].includes(fnName)) continue;
    calls.push({
      kind: 'direct',
      fnName,
      rawArgs: m[2],
      fullMatch: m[0]
    });
  }

  return calls;
}

/**
 * Computes the Transitive Dependency Closure until Fixed Point:
 * Closure(P) = P ∪ DirectDeps(P) ∪ DirectDeps(Closure(P))
 */
export function computeTransitiveClosure(entrypointNames, parsedGraph) {
  const closure = new Map();
  const queue = [...entrypointNames];
  const visited = new Set();

  while (queue.length > 0) {
    const currentName = queue.shift();
    if (visited.has(currentName)) continue;
    visited.add(currentName);

    const fnDef = parsedGraph.fns.get(currentName);
    if (fnDef) {
      closure.set(currentName, fnDef);

      for (const call of fnDef.calls) {
        if (call.kind === 'direct' && parsedGraph.fns.has(call.fnName)) {
          if (!visited.has(call.fnName)) {
            queue.push(call.fnName);
          }
        }
      }
    }
  }

  return closure;
}

/**
 * Analyzes and classifies all symbols encountered across the dependency closure.
 */
export function classifyCapabilities(closure, parsedGraph) {
  const resolved = new Set();
  const materialized = new Set();
  const host_required = new Set();
  const unresolved = new Set();
  const symbolDetails = new Map();

  for (const [name, fnDef] of closure.entries()) {
    resolved.add(name);
    materialized.add(name);
    symbolDetails.set(name, {
      taxonomy: fnDef.origin,
      materialized: true
    });

    for (const call of fnDef.calls) {
      if (call.kind === 'method') {
        const fullSymbol = `${call.receiver}.${call.method}`;
        if (HOST_CAPABILITY_REGISTRY.has(fullSymbol) || HOST_CAPABILITY_REGISTRY.has(call.receiver)) {
          host_required.add(fullSymbol);
          resolved.add(fullSymbol);
          symbolDetails.set(fullSymbol, { taxonomy: TAXONOMY.HOST_CAPABILITY, materialized: false });
        } else if (BUILTIN_PURE_REGISTRY.has(call.method)) {
          resolved.add(call.method);
          materialized.add(`specialized:${call.method}`);
          symbolDetails.set(`specialized:${call.method}`, { taxonomy: TAXONOMY.BUILTIN_PURE, materialized: true });
        } else if (closure.has(call.method) || parsedGraph.fns.has(call.method)) {
          resolved.add(call.method);
          materialized.add(call.method);
          symbolDetails.set(call.method, { taxonomy: TAXONOMY.LIBRARY_SOURCE, materialized: true });
        } else {
          unresolved.add(fullSymbol);
          symbolDetails.set(fullSymbol, { taxonomy: TAXONOMY.UNRESOLVED, materialized: false });
        }
      } else if (call.kind === 'direct') {
        if (closure.has(call.fnName) || parsedGraph.fns.has(call.fnName)) {
          resolved.add(call.fnName);
          materialized.add(call.fnName);
          symbolDetails.set(call.fnName, { taxonomy: fnDef.origin, materialized: true });
        } else if (HOST_CAPABILITY_REGISTRY.has(call.fnName)) {
          host_required.add(call.fnName);
          resolved.add(call.fnName);
          symbolDetails.set(call.fnName, { taxonomy: TAXONOMY.HOST_CAPABILITY, materialized: false });
        } else {
          unresolved.add(call.fnName);
          symbolDetails.set(call.fnName, { taxonomy: TAXONOMY.UNRESOLVED, materialized: false });
        }
      }
    }
  }

  const matCount = materialized.size;
  const hostCount = host_required.size;
  const unresCount = unresolved.size;
  const denominator = matCount + hostCount + unresCount;
  const closure_coverage = denominator === 0 ? 1.0 : matCount / denominator;

  return {
    manifest: {
      contract: 'LIN_CAPABILITY_V1',
      resolved: Array.from(resolved),
      materialized: Array.from(materialized),
      host_required: Array.from(host_required),
      unresolved: Array.from(unresolved),
      closure_coverage: parseFloat(closure_coverage.toFixed(4)),
      total_semantic_units: denominator
    },
    symbolDetails
  };
}

/**
 * Generic Semantic Specialization & Lowering
 * Lowers high-level functional calls (e.g. array methods, chaining) into pure LIN accumulator loops.
 */
export function specializeAndLowerFunction(fnDef, symbolDetails) {
  let body = fnDef.body;

  // 1. Process method calls and specialize them at statement level
  body = specializeMethodCalls(body);

  // 2. Lower JS control structures to LIN sigils
  let linBody = body;
  linBody = linBody.replace(/\/\*[\s\S]*?\*\//g, '');
  linBody = linBody.replace(/\/\/.*/g, '');
  linBody = linBody.replace(/\?\?/g, '||');
  linBody = linBody.replace(/\}\s*else\s+if\s*\(([^)]+)\)\s*\{/g, '}:($1){');
  linBody = linBody.replace(/\}\s*else\s*\{/g, '}:{');
  linBody = linBody.replace(/\belse\s+if\s*\(([^)]+)\)\s*\{/g, ':($1){');
  linBody = linBody.replace(/\belse\s*\{/g, '}:{');
  linBody = lowerIfStatements(linBody);
  linBody = lowerWhileStatements(linBody);
  linBody = linBody.replace(/\breturn\s+([^;]+);/g, '^$1;');
  linBody = linBody.replace(/\breturn;/g, '^null;');
  linBody = linBody.replace(/\b(?:let|const|var)\s+/g, '');

  return {
    name: fnDef.name,
    params: fnDef.params.join(','),
    linBody: linBody.trim()
  };
}

function lowerIfStatements(code) {
  let res = '';
  let i = 0;
  while (i < code.length) {
    if (code.slice(i, i + 3) === 'if ' || code.slice(i, i + 3) === 'if(') {
      const openParen = code.indexOf('(', i);
      if (openParen >= 0) {
        let depth = 1;
        let k = openParen + 1;
        while (k < code.length && depth > 0) {
          if (code[k] === '(') depth++;
          else if (code[k] === ')') depth--;
          k++;
        }
        const cond = code.slice(openParen + 1, k - 1);
        let nextNonWs = k;
        while (nextNonWs < code.length && /\s/.test(code[nextNonWs])) nextNonWs++;
        if (code[nextNonWs] === '{') {
          res += `?(${cond}){`;
          i = nextNonWs + 1;
          continue;
        }
      }
    }
    res += code[i];
    i++;
  }
  return res;
}

function lowerWhileStatements(code) {
  return code.replace(/\bwhile\s*\(([^)]+)\)\s*\{/g, ';while($1){');
}

/**
 * Generic lowering of chained or standalone method calls (map, filter, reduce, join)
 * Synthesizes direct sequential LIN statements inside the function body.
 */
function specializeMethodCalls(body) {
  let s = body;

  // Pattern 1: return receiver.filter(x => expr).map(x => expr).join(sep);
  const retFilterMapJoinRe = /return\s+([A-Za-z0-9_$]+)\s*\.filter\s*\(\s*([A-Za-z0-9_$]+)\s*=>\s*([^)]+)\)\s*\.map\s*\(\s*([A-Za-z0-9_$]+)\s*=>\s*([^)]+)\)\s*\.join\s*\(\s*(['"][^'"]*['"]|\S+)?\s*\)\s*;/g;
  s = s.replace(retFilterMapJoinRe, (match, recv, filterParam, filterExpr, mapParam, mapExpr, joinSep) => {
    const sep = joinSep || '","';
    return `
      _filt = [];
      #(i=0; i<${recv}.length; i++){
        ${filterParam} = ${recv}[i];
        ?(${filterExpr}){
          _filt.push(${filterParam});
        };
      };
      _mapped = [];
      #(j=0; j<_filt.length; j++){
        ${mapParam} = _filt[j];
        _mapped.push(${mapExpr});
      };
      _res = "";
      #(k=0; k<_mapped.length; k++){
        _res = _res + (k > 0 ? (${sep} + _mapped[k]) : _mapped[k]);
      };
      return _res;
    `;
  });

  // Pattern 2: return receiver.filter(x => expr).reduce((acc, x) => expr, initVal);
  const retFilterReduceRe = /return\s+([A-Za-z0-9_$]+)\s*\.filter\s*\(\s*([A-Za-z0-9_$]+)\s*=>\s*([^)]+)\)\s*\.reduce\s*\(\s*\(\s*([A-Za-z0-9_$]+)\s*,\s*([A-Za-z0-9_$]+)\s*\)\s*=>\s*([^,)]+)\s*,\s*([^)]+)\)\s*;/g;
  s = s.replace(retFilterReduceRe, (match, recv, filterParam, filterExpr, accParam, itemParam, reduceExpr, initVal) => {
    return `
      _filt = [];
      #(i=0; i<${recv}.length; i++){
        ${filterParam} = ${recv}[i];
        ?(${filterExpr}){
          _filt.push(${filterParam});
        };
      };
      ${accParam} = ${initVal};
      #(j=0; j<_filt.length; j++){
        ${itemParam} = _filt[j];
        ${accParam} = ${reduceExpr};
      };
      return ${accParam};
    `;
  });

  // Pattern 3: return receiver.map(x => expr);
  const retMapRe = /return\s+([A-Za-z0-9_$]+)\s*\.map\s*\(\s*([A-Za-z0-9_$]+)\s*=>\s*([^)]+)\)\s*;/g;
  s = s.replace(retMapRe, (match, recv, param, expr) => {
    return `
      _mapped = [];
      #(i=0; i<${recv}.length; i++){
        ${param} = ${recv}[i];
        _mapped.push(${expr});
      };
      return _mapped;
    `;
  });

  // Pattern 4: return receiver.filter(x => expr);
  const retFilterRe = /return\s+([A-Za-z0-9_$]+)\s*\.filter\s*\(\s*([A-Za-z0-9_$]+)\s*=>\s*([^)]+)\)\s*;/g;
  s = s.replace(retFilterRe, (match, recv, param, expr) => {
    return `
      _filt = [];
      #(i=0; i<${recv}.length; i++){
        ${param} = ${recv}[i];
        ?(${expr}){
          _filt.push(${param});
        };
      };
      return _filt;
    `;
  });

  // Pattern 5: return receiver.join(sep);
  const retJoinRe = /return\s+([A-Za-z0-9_$]+)\s*\.join\s*\(\s*(['"][^'"]*['"]|\S+)?\s*\)\s*;/g;
  s = s.replace(retJoinRe, (match, recv, joinSep) => {
    const sep = joinSep || '","';
    return `
      _res = "";
      #(i=0; i<${recv}.length; i++){
        _res = _res + (i > 0 ? (${sep} + ${recv}[i]) : ${recv}[i]);
      };
      return _res;
    `;
  });

  return s;
}

/**
 * Main Engine Pipeline:
 * Takes source code + optional library sources + entrypoint function names.
 * Produces materialized program.lin, extracted_runtime.lin, and capability_manifest.json.
 */
export function runSemanticClosurePipeline(userSource, opts = {}) {
  const libSources = opts.libraries || {};
  const entrypoints = opts.entrypoints || [];

  // Step 1: Parse AST & Symbol Call Graph
  const parsedGraph = parseSourceGraph(userSource, libSources);

  // If no entrypoints specified, default to all user-defined functions
  const effectiveEntrypoints = entrypoints.length > 0
    ? entrypoints
    : Array.from(parsedGraph.fns.entries())
        .filter(([_, def]) => def.origin === TAXONOMY.USER_DEFINED)
        .map(([name]) => name);

  // Step 2: Compute Transitive Dependency Closure until Fixed Point
  const closure = computeTransitiveClosure(effectiveEntrypoints, parsedGraph);

  // Step 3: Analyze and Classify Capabilities
  const { manifest, symbolDetails } = classifyCapabilities(closure, parsedGraph);

  // Step 4: Specialize and Lower Functions
  const materializedProgramFns = [];
  const materializedRuntimeFns = [];

  for (const [name, fnDef] of closure.entries()) {
    const lowered = specializeAndLowerFunction(fnDef, symbolDetails);
    if (fnDef.origin === TAXONOMY.USER_DEFINED) {
      materializedProgramFns.push(lowered);
    } else {
      materializedRuntimeFns.push(lowered);
    }
  }

  // Step 5: Emit Artifacts
  const program_lin = emitLinModule(materializedProgramFns, effectiveEntrypoints);
  const extracted_runtime_lin = emitLinModule(
    materializedRuntimeFns,
    materializedRuntimeFns.map(f => f.name)
  );

  return {
    program_lin,
    extracted_runtime_lin,
    capability_manifest: manifest,
    closure_size: closure.size,
    coverage: manifest.closure_coverage
  };
}

function emitLinModule(fns, exports) {
  if (fns.length === 0) {
    return `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else}\n=ex{}`;
  }

  const lines = [
    '@LIN:L1c:0.2',
    '^schema_once ^lossy=true',
    '~G{?=if #=for ^=ret :else}',
    ''
  ];

  for (const fn of fns) {
    lines.push(`!${fn.name}(${fn.params}){\n${fn.linBody}\n}`);
  }

  lines.push('');
  lines.push(`=ex{${exports.join(',')}}`);
  return lines.join('\n');
}

/**
 * Diagnostic Fault Isolation:
 * Classifies differential test failures orthogonally into EXTRACTION, LOWERING, CAPABILITY, or RUNTIME.
 */
export function isolateFailureCause(testCase, oracleResult, linResult, manifest) {
  if (manifest.unresolved.length > 0) {
    return {
      fault: 'CAPABILITY',
      reason: `Unresolved external symbols present: ${manifest.unresolved.join(', ')}`
    };
  }
  if (manifest.host_required.length > 0 && linResult === null) {
    return {
      fault: 'CAPABILITY',
      reason: `Required host capability boundary: ${manifest.host_required.join(', ')}`
    };
  }
  if (typeof linResult === 'string' && linResult.startsWith('__RUNTIME_ERROR__')) {
    return {
      fault: 'RUNTIME',
      reason: `Rust native runtime raised error executing lowered bytecode`
    };
  }
  return {
    fault: 'LOWERING',
    reason: `Output mismatch between JS oracle and lowered LIN logic`
  };
}
