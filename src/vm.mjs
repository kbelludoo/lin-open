import vm from 'node:vm';
import { createRequire } from 'node:module';

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
  const allowed = new Map([
    ['node:crypto', () => getRequire()('node:crypto')],
    ['crypto', () => getRequire()('node:crypto')],
    ['node:buffer', () => getRequire()('node:buffer')],
    ['buffer', () => getRequire()('node:buffer')],
    ['node:util', () => getRequire()('node:util')],
    ['util', () => getRequire()('node:util')],
  ]);
  return (spec) => {
    if (allowed.has(spec)) return allowed.get(spec)();
    throw new Error(`LIN_SANDBOX_REQUIRE: ${spec} not allowed in memory sandbox`);
  };
}

export function assertJsSyntax(code) {
  try {
    new Function(String(code));
    return true;
  } catch (e) {
    throw new Error(`LIN_JS_SYNTAX: ${e.message}`);
  }
}
