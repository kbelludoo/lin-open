// LIN In-Memory VM & Sandbox Engine (Dogfooding vm_core.lin)
import vm from 'node:vm';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { validateSandboxSpec, assertJsSyntaxCore } = require('./vm_core.compiled.cjs');

let hostRequire = null;

function getRequire() {
  if (!hostRequire) hostRequire = createRequire(import.meta.url);
  return hostRequire;
}

export function runInMemory(jsCode, opts = {}) {
  const m = { exports: {} };
  const sandbox = {
    module: m,
    exports: m.exports,
    require: makeRequireShim(),
    console: opts.console || console,
    Buffer,
    TextEncoder,
    TextDecoder,
    URL,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    queueMicrotask,
  };
  const context = vm.createContext(sandbox);
  const script = new vm.Script(String(jsCode), { filename: opts.filename || 'lin-in-memory.js' });
  script.runInContext(context, { timeout: opts.timeoutMs || 5000 });
  const exported = sandbox.module.exports;
  const fn = new Function('m', 'return m');
  void fn;
  return exported === undefined ? m.exports : exported;
}

function makeRequireShim() {
  return (spec) => {
    if (validateSandboxSpec(spec)) {
      const modName = spec.startsWith('node:') ? spec : `node:${spec}`;
      return getRequire()(modName);
    }
    throw new Error(`LIN_SANDBOX_REQUIRE: ${spec} not allowed in memory sandbox`);
  };
}

export function assertJsSyntax(code) {
  assertJsSyntaxCore(code);
  try {
    new Function(String(code));
    return true;
  } catch (e) {
    throw new Error(`LIN_JS_SYNTAX: ${e.message}`);
  }
}
