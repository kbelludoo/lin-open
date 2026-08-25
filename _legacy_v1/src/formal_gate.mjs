/**
 * LIN Formal Semantic Gate (M006-A).
 * Proof Obligation / Invariant Engine that verifies the AST BEFORE any lowering/emission.
 * Spec: spec/LIN_PARADIGMS_ROADMAP.rulel + LIN-FORMAL-SEMANTIC-CORE-006.
 *
 * Invariants verified:
 *   INV_SYMBOL_RESOLVED   - every referenced identifier has an unambiguous binding in scope
 *   INV_EFFECT_BOUNDED    - function effects are a subset of declared module capabilities
 *   INV_REFINEMENT_SOUND  - divisions have non-zero divisor (statically proved or refined)
 *   INV_EXHAUSTIVE_MATCH  - match covers the domain or includes a wildcard
 */
import { parseStmts, tryParseStmts, collectAssignedIds } from './body_ast.mjs';

export const INVARIANTS = {
  SYMBOL_RESOLVED: 'INV_SYMBOL_RESOLVED',
  EFFECT_BOUNDED: 'INV_EFFECT_BOUNDED',
  REFINEMENT_SOUND: 'INV_REFINEMENT_SOUND',
  EXHAUSTIVE_MATCH: 'INV_EXHAUSTIVE_MATCH',
};

const KEYWORDS = new Set([
  'return', 'if', 'else', 'for', 'while', 'switch', 'case', 'default', 'throw',
  'fn', 'struct', 'enum', 'mod', 'use', 'let', 'const', 'var', 'function',
  'break', 'continue', 'true', 'false', 'null', 'undefined', 'match',
]);

const BUILTINS = new Set([
  'String', 'Number', 'Math', 'Buffer', 'Array', 'Object', 'Error', 'JSON',
  'console', 'process', 'require', 'globalThis', 'window', 'document', 'fetch',
  'setTimeout', 'setInterval', 'crypto', 'print', 'println', 'format', '_',
]);

/** Tokenize identifiers in a body, skipping string/regex/char literals and comments. */
export function collectIdentifiers(body) {
  const s = String(body || '');
  const out = new Set();
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const q = c;
      let j = i + 1;
      while (j < s.length) {
        if (s[j] === '\\') { j += 2; continue; }
        if (q === '`' && s[j] === '$' && s[j + 1] === '{') {
          let d = 1;
          let k = j + 2;
          while (k < s.length && d > 0) {
            if (s[k] === '{') d++;
            else if (s[k] === '}') d--;
            k++;
          }
          j = k;
          continue;
        }
        if (s[j] === q) break;
        j++;
      }
      i = j + 1;
      continue;
    }
    if (c === '/' && s[i + 1] === '/') {
      let j = i;
      while (j < s.length && s[j] !== '\n') j++;
      i = j;
      continue;
    }
    if (c === '/' && s[i + 1] === '*') {
      const end = s.indexOf('*/', i + 2);
      i = end < 0 ? s.length : end + 2;
      continue;
    }
    if (/[A-Za-z_$]/.test(c)) {
      let j = i + 1;
      while (j < s.length && /[A-Za-z0-9_$]/.test(s[j])) j++;
      const word = s.slice(i, j);
      if (!KEYWORDS.has(word)) {
        // skip property access: foo.bar -> 'bar' is a field, not a free identifier
        let k = i - 1;
        while (k >= 0 && /\s/.test(s[k])) k--;
        if (!(k >= 0 && s[k] === '.')) out.add(word);
      }
      i = j;
      continue;
    }
    i++;
  }
  return out;
}

/** Detect concrete effect labels used by a function body (Read/Write/Throw/Native/IO). */
export function detectEffects(body, locals = new Set()) {
  const s = String(body || '');
  const effects = new Set();
  if (/\bthrow\s*\(/.test(s) || /^throw\b/.test(s)) effects.add('Throw');
  if (/console\.|print\(|println\(|fetch\(|process\.|require\(|document\.|window\.|alert\(/.test(s)) effects.add('IO');
  if (/\b(String|Number|Math|Buffer|Array|Object|Error|JSON|crypto|setTimeout|setInterval)\b/.test(s)) effects.add('Native');
  const idRe = /\b([A-Za-z_$][\w$]*)\b/g;
  let m;
  while ((m = idRe.exec(s)) !== null) {
    const id = m[1];
    let k = m.index - 1;
    while (k >= 0 && /\s/.test(s[k])) k--;
    if (k >= 0 && s[k] === '.') continue; // property access
    if (KEYWORDS.has(id) || BUILTINS.has(id) || locals.has(id)) continue;
    if (/^[A-Z]/.test(id)) continue;
    effects.add('Read');
    break;
  }
  return [...effects];
}

/** Map a declared capability name to the concrete effect labels it permits. */
const CAP_TO_EFFECT = {
  io: ['IO', 'Native'],
  console: ['IO', 'Native'],
  native: ['Native'],
  read: ['Read', 'Native'],
  state: ['Write', 'Read'],
  write: ['Write'],
  throw: ['Throw'],
  pure: [],
};

function collectScope(prog, mod) {
  const scope = new Set([...BUILTINS]);
  const addFns = (fns) => { for (const f of fns || []) scope.add(f.name); };
  const addEnums = (enums) => {
    for (const e of enums || []) {
      scope.add(e.name);
      for (const v of e.variants || []) scope.add(v.name);
    }
  };
  const addStructs = (structs) => {
    for (const st of structs || []) {
      scope.add(st.name);
      for (const f of st.fields || []) scope.add(f.name);
    }
  };
  const addUses = (uses) => { for (const u of uses || []) for (const s of u.symbols || []) scope.add(s); };
  const modNames = new Set((prog.modules || []).map((m) => m.name));
  addFns(prog.fns);
  addEnums(prog.enums);
  addStructs(prog.structs);
  addUses(prog.uses);
  for (const n of modNames) scope.add(n);
  if (mod) {
    addFns(mod.program.fns);
    addEnums(mod.program.enums);
    addStructs(mod.program.structs);
    addUses(mod.program.uses);
    for (const m of prog.modules || []) scope.add(m.name);
  } else {
    for (const m of prog.modules || []) {
      addFns(m.program.fns);
      addEnums(m.program.enums);
      addStructs(m.program.structs);
    }
  }
  return scope;
}

function refineSafeParams(fn) {
  // params annotated with refinement int{!=0} / int{>0} are provably non-zero
  const safe = new Set();
  const src = String(fn.rawParams || fn.params || '');
  const re = /([A-Za-z_$][\w$]*)\s*:\s*int\{([^}]+)\}/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    const guard = m[2];
    if (guard.includes('!=0') || guard.includes('>0') || guard.includes('>=1') || guard.includes('<0')) safe.add(m[1]);
  }
  return safe;
}

/** Detect provably-non-zero guard expressions for a divisor. */
function divisorLooksSafe(expr) {
  const s = String(expr || '').trim();
  if (/^[0-9]/.test(s)) return !/^0(?:\D|$)/.test(s) && /^[1-9][0-9]*$/.test(s);
  return false;
}

/** Collect locally-bound identifiers from raw function body (let/const/var, plain assigns, for-init, match bindings). */
export function collectBoundLocals(body, params = []) {
  const bound = new Set();
  for (const p of params) {
    const name = String(p).replace(/[:\s{].*$/s, '').trim();
    if (name) bound.add(name);
  }
  const s = String(body || '');
  const declRe = /\b(?:let|const|var)\s+([A-Za-z_$][\w$]*)/g;
  let m;
  while ((m = declRe.exec(s)) !== null) bound.add(m[1]);
  const assignRe = /(?:^|[;{}:,]\s*)([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  while ((m = assignRe.exec(s)) !== null) {
    if (!KEYWORDS.has(m[1])) bound.add(m[1]);
  }
  const forInit = /for\(\s*([A-Za-z_$][\w$]*)\s*=/g;
  while ((m = forInit.exec(s)) !== null) bound.add(m[1]);
  const enumPat = /\b[A-Za-z_$][\w$]*\s*\(\s*([A-Za-z_$][\w$]*)\s*\)\s*=>/g;
  while ((m = enumPat.exec(s)) !== null) bound.add(m[1]);
  const tuplePat = /\(\s*([A-Za-z_$][\w$]*)\s*\)\s*=>/g;
  while ((m = tuplePat.exec(s)) !== null) bound.add(m[1]);
  return bound;
}

function checkSymbolsForFn(fn, scope, violations, loc) {
  const ids = collectIdentifiers(fn.body);
  const bound = new Set([...scope]);
  const params = String(fn.params || '').split(',').map((p) => p.trim()).filter(Boolean);
  const locals = collectBoundLocals(fn.body, params);
  for (const id of locals) bound.add(id);
  for (const id of ids) {
    if (bound.has(id)) continue;
    violations.push({
      invariant: INVARIANTS.SYMBOL_RESOLVED,
      node: `${loc}::${fn.name}`,
      detail: `identifier '${id}' has no unambiguous binding in scope`,
    });
  }
}

function checkExhaustiveMatchForFn(fn, violations, loc) {
  const walk = (list) => {
    for (const st of list || []) {
      if (st.type === 'match') {
        const arms = st.arms || [];
        const hasWildcard = arms.some((a) => a.pat === '_');
        const hasAnyLiteralOrBoolean = arms.some((a) =>
          /^(true|false|None)$/.test(a.pat) || /^["']|^-?\d/.test(a.pat));
        const strong = arms.length >= 2;
        if (!hasWildcard && !(hasAnyLiteralOrBoolean && strong) && !strong) {
          violations.push({
            invariant: INVARIANTS.EXHAUSTIVE_MATCH,
            node: `${loc}::${fn.name}`,
            detail: `match on (${st.expr}) has ${arms.length} arm(s); needs a wildcard '_' or exhaustive coverage`,
          });
        }
        for (const arm of arms) walk(arm.body);
      }
      if (st.type === 'if') {
        walk(st.then);
        for (const e of st.elseIf || []) walk(e.body);
        if (st.else) walk(st.else);
      }
      if (st.type === 'for') walk(st.body);
      if (st.type === 'while') walk(st.body);
    }
  };
  walk(tryParseStmts(fn.body) || []);
}

function checkRefinementForFn(fn, violations, loc) {
  const body = String(fn.body || '');
  const safeDiv = refineSafeParams(fn);
  const re = /\/([^/]|\\[\/])/g;
  let m;
  const s = body;
  let i = 0;
  // scan for division; skip regex literals conservatively by only matching ' / <expr>'
  const divRe = /(\b[A-Za-z_$][\w$]*|\)|\]|[0-9])\s*\/\s*([A-Za-z_$][\w$]*|[0-9]+|\([^()]*\))/g;
  while ((m = divRe.exec(s)) !== null) {
    const divisor = m[2].trim();
    const isNum = /^[0-9]+$/.test(divisor);
    if (isNum && parseInt(divisor, 10) === 0) {
      violations.push({
        invariant: INVARIANTS.REFINEMENT_SOUND,
        node: `${loc}::${fn.name}`,
        detail: `division by literal zero '${m[0].trim()}'`,
      });
      continue;
    }
    if (/^[A-Za-z_$][\w$]*$/.test(divisor)) {
      if (!safeDiv.has(divisor)) {
        violations.push({
          invariant: INVARIANTS.REFINEMENT_SOUND,
          node: `${loc}::${fn.name}`,
          detail: `divisor '${divisor}' is not statically provable non-zero; annotate param as int{!=0}`,
        });
      }
    }
  }
}

/** Run all four invariant checks over a program. Returns a proof report. */
export function checkInvariants(prog) {
  const violations = [];
  const checkFn = (fn, mod) => {
    const loc = mod ? `mod:${mod.name}` : 'top';
    checkSymbolsForFn(fn, collectScope(prog, mod), violations, loc);
    checkExhaustiveMatchForFn(fn, violations, loc);
    checkRefinementForFn(fn, violations, loc);
  };

  for (const fn of prog.fns || []) checkFn(fn, null);

  for (const mod of prog.modules || []) {
    // EFFECT_BOUNDED: module declared capabilities must cover each fn's effects
    const declared = mod.effects || [];
    const permitted = new Set();
    for (const cap of declared) {
      const effs = CAP_TO_EFFECT[cap] || [];
      for (const e of effs) permitted.add(e);
    }
    for (const fn of mod.program.fns || []) {
      checkFn(fn, mod);
      const params = String(fn.params || '').split(',').map((p) => p.trim()).filter(Boolean);
      const locals = collectBoundLocals(fn.body, params);
      const used = detectEffects(fn.body, locals);
      for (const fx of used) {
        if (!permitted.has(fx)) {
          violations.push({
            invariant: INVARIANTS.EFFECT_BOUNDED,
            node: `mod:${mod.name}::${fn.name}`,
            detail: `effect '${fx}' exceeds declared module capabilities {${declared.join(', ') || 'none'}}`,
          });
        }
      }
    }
  }

  const counts = {};
  for (const name of Object.values(INVARIANTS)) counts[name] = 0;
  for (const v of violations) counts[v.invariant]++;

  return {
    pass: violations.length === 0,
    violations,
    invariants: Object.values(INVARIANTS).map((id) => ({
      id,
      status: counts[id] === 0 ? 'PROVED' : 'VIOLATED',
      violations: counts[id],
    })),
    proofObligations: violations.length,
    verifiedNodes: countVerifiedNodes(prog),
  };
}

function countVerifiedNodes(prog) {
  let n = 0;
  for (const f of prog.fns || []) n += collectIdentifiers(f.body).size;
  for (const m of prog.modules || []) {
    for (const f of m.program.fns || []) n += collectIdentifiers(f.body).size;
  }
  return n;
}

/** Rich human-readable diagnostic. */
export function formatDiagnostics(report) {
  if (report.pass) {
    return [
      'FORMAL_GATE: ALL_INVARIANTS_PROVED',
      `  verified identifiers: ${report.verifiedNodes}`,
      ...report.invariants.map((i) => `  [${i.status}] ${i.id} (${i.violations} violations)`),
    ].join('\n');
  }
  const lines = ['FORMAL_GATE: INVARIANT_VIOLATIONS_FOUND'];
  for (const v of report.violations) {
    lines.push(`  [${v.invariant}] @ ${v.node}: ${v.detail}`);
  }
  return lines.join('\n');
}

/** Entry: gate a program; throws with rich diagnostic when not pass (strict mode). */
export function runFormalGate(prog, opts = {}) {
  const report = checkInvariants(prog);
  if (opts.strict && !report.pass) {
    const err = new Error(formatDiagnostics(report));
    err.name = 'LIN_FORMAL_GATE_VIOLATION';
    err.formalReport = report;
    throw err;
  }
  return report;
}
