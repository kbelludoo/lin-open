/**
 * LIN In-Memory Execution Engine (JIT / Memory Loader).
 * Transpiles .lin / .lia directly to JavaScript/TypeScript target in memory
 * and executes within a secure V8 VM context or dynamic module without writing files to disk.
 */
import vm from 'node:vm';
import { compileLia } from './multi_emit.mjs';

/**
 * Execute LIN code in memory and return exported bindings and results.
 * @param {string} linCode - Raw LIN or LIA code.
 * @param {object} context - Optional sandbox variables/functions.
 * @returns {object} Module exports and execution metadata.
 */
export function runLinInMemory(linCode, context = {}) {
  const startTime = process.hrtime.bigint();

  // 1. In-memory compilation (LIN -> JS)
  const compiled = compileLia(linCode, { target: 'js', stubRuntime: false });

  // 2. Prepare Sandbox Context
  const sandbox = {
    module: { exports: {} },
    exports: {},
    console,
    Math,
    Date,
    String,
    Number,
    Boolean,
    Array,
    Object,
    RegExp,
    ...context,
  };

  const vmContext = vm.createContext(sandbox);

  // 3. In-memory V8 Script execution
  const script = new vm.Script(compiled.code);
  script.runInContext(vmContext);

  const endTime = process.hrtime.bigint();
  const executionNs = Number(endTime - startTime);

  const exported = { ...sandbox.module.exports, ...sandbox.exports };

  return {
    exports: exported,
    compiledCode: compiled.code,
    latencyMs: (executionNs / 1_000_000).toFixed(4),
    memoryFootprintBytes: Buffer.byteLength(compiled.code, 'utf8'),
  };
}
