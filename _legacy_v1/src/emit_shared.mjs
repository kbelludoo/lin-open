/**
 * Shared helpers for LIA multi-target emitters.
 * @typedef {{type:'assign', id:string, op:string, expr:string}} AssignStmt
 * @typedef {{type:'return', expr:string}} ReturnStmt
 * @typedef {{type:'expr', expr:string}} ExprStmt
 * @typedef {{type:'throw', expr:string}} ThrowStmt
 * @typedef {{type:'if', cond:string, then:Stmt[], elseIf:{cond:string,body:Stmt[]}[], else:Stmt[]|null}} IfStmt
 * @typedef {{type:'for', init:string, cond:string, step:string, body:Stmt[]}} ForStmt
 * @typedef {{type:'while', cond:string, body:Stmt[]}} WhileStmt
 * @typedef {AssignStmt|ReturnStmt|ExprStmt|ThrowStmt|IfStmt|ForStmt|WhileStmt} Stmt
 */

import { rewriteHostExpr, rewriteIifeTernary, rewriteTernaries, foldPlus, collapseHostChains } from './emit_rewrite.mjs';

/** Matches src/clone_lin_full_repo_gate.lin defaultEmitTarget — prefer TS until a real bench exists. */
export const DEFAULT_EMIT_TARGET = 'ts';

export const TARGETS = [
  'ts', 'js', 'py', 'go', 'rust', 'c', 'java',
  'cs', 'lua', 'elixir', 'crystal', 'kotlin', 'hcl',
  'julia', 'scala', 'haskell', 'prolog',
  'zig', 'nim', 'asm',
];

/** Real nucleus: compile + toolchain check. Stub langs may emit but are not suite_rate. */
export const REAL_TARGETS = ['ts', 'js', 'py', 'go', 'rust', 'c', 'java'];
export const STUB_TARGETS = TARGETS.filter((t) => !REAL_TARGETS.includes(t));
export const GATE_REQUIRED = ['ts', 'js', 'py', 'go', 'rust', 'java'];

export function formatNucleusMulti(summary) {
  return REAL_TARGETS.map((t) => {
    const s = summary?.[t] || { PASS: 0, SKIP: 0, FAIL: 0 };
    return `${t}:P${s.PASS || 0}/S${s.SKIP || 0}/F${s.FAIL || 0}`;
  }).join(' ');
}

/** Never a Px/S0/F0 score — stub langs are not suite_rate. */
export function formatStubIntel() {
  return `EXPERIMENTAL_NOT_PASS ${STUB_TARGETS.join(',')} no_toolchain_no_oracle`;
}

const STUB_PASS_RE = /\b(?:cs|lua|elixir|crystal|kotlin|hcl|julia|scala|haskell|prolog|zig|nim|asm):P\d+\/S\d+\/F\d+\s*/g;

export function stripStubPassScores(text) {
  return String(text || '').replace(STUB_PASS_RE, '');
}

/** INTEL multi= from real nucleus only. Ignores stub keys and stray asm:P15 tokens. */
export function honestNucleusMulti(summaryOrLine) {
  if (summaryOrLine && typeof summaryOrLine === 'object' && !Array.isArray(summaryOrLine)) {
    const only = {};
    for (const t of REAL_TARGETS) only[t] = summaryOrLine[t] || { PASS: 0, SKIP: 0, FAIL: 0 };
    return formatNucleusMulti(only);
  }
  const summary = {};
  for (const tok of String(summaryOrLine || '').split(/\s+/)) {
    const m = tok.match(/^([a-z]+):P(\d+)\/S(\d+)\/F(\d+)$/);
    if (!m || !REAL_TARGETS.includes(m[1])) continue;
    summary[m[1]] = { PASS: Number(m[2]), SKIP: Number(m[3]), FAIL: Number(m[4]) };
  }
  return formatNucleusMulti(summary);
}

export function snakeCase(name) {
  return String(name)
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/-/g, '_')
    .toLowerCase();
}

/** `_` is a blank/keyword on Rust/Java; keep a real binding for coerce + body. */
const RESERVED_EMIT_ID = /^(type|fn|let|mut|impl|pub|struct|enum|match|use|mod|crate|self|Self|super|where|async|await|dyn|move|ref|box|func|interface|select|chan|defer|go|map|package|range|var|const|fallthrough|default|case|switch|break|continue|return|if|else|for|import|clone|as|in|loop|trait|unsafe|extern|static|true|false|new|try|catch|throw|this|null|class|public|private|protected|void|int|long|boolean|byte|char|short|float|double|abstract|final|native|synchronized|throws|extends|implements|instanceof|assert|volatile|transient|do|while|yield|typeof|override|virtual|init|main|bool|string|error|rune|uint|uintptr|any|comparable|make|len|cap|append|copy|delete|panic|recover|close|complex|real|imag|print|println|iota|nil|int8|int16|int32|int64|uint8|uint16|uint32|uint64|float32|float64|complex64|complex128|and|del|elif|except|finally|from|global|is|lambda|nonlocal|not|or|pass|raise|with|None|True|False|def|elif|auto|register|signed|unsigned|sizeof|typedef|union|goto|restrict|inline|wait|notify|notifyAll|getClass|hashCode|equals|toString|finalize|strictfp)$/;

export function safeEmitId(id) {
  let s = String(id || '');
  if (!s || s === '_' || s === '__') return '_u';
  s = s.replace(/\$/g, 'dollar').replace(/[^A-Za-z0-9_]/g, '_');
  if (!s || !/^[A-Za-z_]/.test(s)) s = `id_${s || 'x'}`;
  if (RESERVED_EMIT_ID.test(s)) return `${s}_`;
  return s;
}

/** Unique host-safe names for a LIN fn list. transform maps LIN name → host ident before reserve-rename. */
export function emitNameMap(fns, transform = (n) => String(n || '')) {
  const used = new Set();
  const map = Object.create(null);
  for (const fn of fns || []) {
    const raw = String(fn.name || '');
    let name = safeEmitId(transform(raw));
    while (used.has(name)) name = `${name}_u`;
    used.add(name);
    map[raw] = name;
  }
  return map;
}

export function isNoopExpr(expr) {
  return /^(nil|null|None|0|""|'')(\(\))?$/.test(String(expr || '').trim());
}

/** Split LIN/JS param lists; strip `size=21` so Go/Rust/Java/C signatures stay valid. */
export function parseParamList(raw) {
  const items = String(raw || '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
  const names = [];
  const defaults = [];
  const sigPy = [];
  const sigTs = [];
  for (const item of items) {
    const m = item.match(/^([A-Za-z_$][\w$]*)\s*=\s*(.+)$/);
    if (m) {
      const id = safeEmitId(m[1]);
      names.push(id);
      defaults.push({ name: id, value: m[2].trim() });
      sigPy.push(`${id}=${m[2].trim()}`);
      sigTs.push(`${id}: unknown = ${m[2].trim()}`);
    } else {
      const id = safeEmitId(item.replace(/\?$/, '').replace(/:\s*[\w[\]|]+$/, '').trim() || item);
      names.push(id);
      sigPy.push(id);
      sigTs.push(`${id}: unknown`);
    }
  }
  return { names, defaults, sigPy, sigTs };
}

export function emitNilDefaults(defaults, target) {
  return (defaults || []).map(({ name, value }) => {
    if (target === 'go') return `\tif ${name} == nil { ${name} = ${value} }`;
    if (target === 'java' && /^["']/.test(value)) return `    if (${name} == null) ${name} = ${value};`;
    if (target === 'c' && /^["']/.test(value)) return `  if (!${name}) ${name} = ${value};`;
    return null;
  }).filter(Boolean);
}

/** Detect JS-runtime-only surface (Buffer/crypto) — stub on non-JS targets. */
export function isJsRuntimeOnly(body, name) {
  if (/^(meridiem|preparse|postformat|months|monthsShort|translate|plural|padZoneStr|monthDiff|prettyUnit|absFloor|padStart|relativeTimeFormatter|relativeTimeWithPlural|relativeTimeWithTense|relativeTimeWithMutation|ordinal|defaultExport|isUndefined|dual|threeFour|correctGrammarCase|resolveTemplate|lastNumber|softMutation|mutation|specialMutationForYears|createChalk|chalkFactory|applyStyle|createBuilder|createStyler|createModelConverters|applyOptions|assertValidLevel|stringReplaceAll|stringEncaseCRLFWithFirstIndex|rainbow|animateString|outputConf|sourcemapConf|monolithConf|debounce|throttle|restArguments|optimizeCb|clone|constant|create|after|before|first|last|rest|initial|range|object|result|bound|template|escapeChar|mixin|memoize|wrap|negate|compose|uniqueId|times|tap|size|noop|identity|pairs|invert|functions|has|get|property|propertyOf|matcher|iteratee|sample|shuffle|sortBy|sortedIndex|uniq|unzip|deepGet|tagTester|ctor|baseCreate|baseIteratee|chainResult|shallowProperty|toBufferView|toPath|keyInObj|alternateIsDataView|isBoolean|isElement|isEmpty|isEqual|isFinite|isMatch|isNaN|isNull|isObject|isTypedArray|cycleTracker|ie11fingerprint|emulatedSet|collectNonEnumProps|createAssigner|createEscaper|createIndexFinder|createPredicateIndexFinder|createReduce|createSizePropertyCheck|executeBound|group|findKey|find|findWhere|every|some|contains|pluck|where|filter|reject|map|mapObject|each|flatten|intersection|values|keys|allKeys|chunk|compact|max|min|toArray|random|_)$/.test(name || '')) {
    return true;
  }
  return /\b(Buffer|crypto|bufferAllocUnsafe|timingSafeEqual|process|Intl|arguments|instanceof)\b/.test(body)
    || /\bthis\./.test(body)
    || /\bthis\[/.test(body)
    || /\bswitch\b/.test(body)
    || /\bnew\s+Date\b/.test(body)
    || /\bLs\b/.test(body)
    || /\bObject\.(setPrototypeOf|defineProperty|defineProperties|entries|create)\b/.test(body)
    || /\\u\{/.test(body)
    || /\bdo\b/.test(body)
    || /\b_\b/.test(body)
    || /#\([^;)]*\bin\b/.test(body)
    || /\bfor\s*\([^;)]*\bin\b/.test(body)
    || /~\(/.test(body)
    || /\.call\b|\.apply\b/.test(body)
    || /\btypeof\b/.test(body)
    || /\bnew\s+[A-Z]/.test(body)
    || /\bimport\.meta\b/.test(body)
    || /\?\?|\?\./.test(body)
    || /\bas\b/.test(body)
    || /:\s*[A-Z]/.test(body)
    || /\b(Array|Vec|Option|Result|Box|Rc|RefCell|HashMap|BTreeMap|VecDeque)<[A-Za-z_$][\w$]*>/.test(body)
    || /`/.test(body)
    || /LIN_TS_ERASE/.test(body)
    || /=>/.test(body)
    || /\.\.\./.test(body)
    || /\btry\b|\bclass\b|\bthrow\b/.test(body)
    || body.length > 2400
    || /\b(fs|path|os|url|http|https|net|child_process|util|stream|worker_threads|Bun|Deno)\b/.test(body)
    || /\b(fileURLToPath|createHash|createRequire|spawnSync|execSync|readFileSync|writeFileSync|process\.env|process\.argv)\b/.test(body)
    || /\b(isObject|isArray|isArrayLike|isFunction|isString|isEmpty|filter|map|each|values|keys|cb|extend|identity|matcher|property|flatten|contains|indexOf|Boolean|createSizePropertyCheck|getLength)\b/.test(body);
}

const FREE_HOST_SKIP = /^(if|for|return|true|false|null|undefined|function|var|let|const|new|typeof|instanceof|delete|in|of|switch|case|break|continue|try|catch|throw|else|while|do|Math|JSON|Object|Array|String|Number|Boolean|Date|Error|RegExp|True|False|None|NULL|NaN|Infinity|console|parseInt|parseFloat|isNaN|isFinite|len|str|float|int|bool|interface|String|new)$/;

/** Undeclared host caps (Ls, IS_DAYJS, FORMAT_DEFAULT) so py/go/rust/java compile. */
export function collectFreeHostIds(body, params, fnNames) {
  const bound = new Set([...(params || []), ...(fnNames || [])]);
  const free = new Set();
  const s = String(body || '');
  if (/\bthis\b/.test(s)) free.add('this');
  const re = /\b([A-Za-z_][\w]*)\b/g;
  let m;
  while ((m = re.exec(s))) {
    const id = m[1];
    if (bound.has(id) || id.startsWith('_lia_') || id.startsWith('__')) continue;
    if (FREE_HOST_SKIP.test(id)) continue;
    if (/^[A-Z]/.test(id) || /^(Ls|L)$/.test(id)) free.add(id);
  }
  return [...free];
}

export function emitFreeHostDecls(ids, target) {
  return (ids || []).map((raw) => {
    const id = target === 'java' && raw === 'this' ? '_lia_this' : raw;
    if (target === 'go') return `\tvar ${id} interface{}\n\t_ = ${id}`;
    if (target === 'py') return `    ${id} = None`;
    if (target === 'rust') return `    let ${id} = String::new();`;
    if (target === 'java') return `    Object ${id} = null;`;
    if (target === 'c') return `  const char *${id} = "";`;
    return '';
  }).filter(Boolean);
}

/** Sibling fn used as a value (not a call) — stub so Rust/Java compile. */
export function rewriteFnValues(body, fnNames, stub) {
  let s = String(body || '');
  for (const name of fnNames || []) {
    if (!/^[A-Za-z_][\w]*$/.test(name)) continue;
    s = s.replace(new RegExp(`\\b${name}\\b(?!\\s*\\()`, 'g'), stub);
  }
  return s;
}

export function isNumishId(id) {
  const s = String(id || '').replace(/_+$/, '');
  return /^(len|n|i|idx|count|num|ms|msAbs)$/i.test(s);
}

export function isBoolFnName(name) {
  return /^(is[A-Z]|want[A-Z]|has[A-Z]|can[A-Z]|safeCompare)|is_|want_|has_|can_|empty|startsWith|endsWith|contains|typeof|row_is|all_rows|refuse_|lang_is|multi_all/i.test(String(name || ''));
}

export function isBoolishId(id) {
  const s = String(id || '').replace(/_+$/, '');
  return /^(ok|flag|valid|done|withMain|rustOk|aOk|bOk|full|alive)$/i.test(s);
}

function numericPlusOperand(t) {
  let x = String(t || '').trim();
  while (x.startsWith('(') && x.endsWith(')')) x = x.slice(1, -1).trim();
  if (/^_lia_num\b/.test(x)) return true;
  if (/^-?\d+$/.test(x)) return true;
  return isNumishId(x) || /^(res|total|sum)$/i.test(x);
}

/** Keep numeric `+` (res+i, n+n); only cat when a side is a string/cat helper. */
export function plusIsNumeric(a, b) {
  const x = String(a || '').trim();
  const y = String(b || '').trim();
  if (/^["']/.test(x) || /^["']/.test(y)) return false;
  if (/_lia_str|_lia_cat|String\.valueOf|_lia_sprintf/.test(x + y) && !/_lia_num/.test(x + y)) return false;
  return numericPlusOperand(x) && numericPlusOperand(y);
}

export function inferTypes(stmts) {
  const types = new Map();
  function allStmts(list) {
    const out = [];
    for (const st of list || []) {
      out.push(st);
      if (st.then) out.push(...allStmts(st.then));
      for (const e of st.elseIf || []) out.push(...allStmts(e.body));
      if (st.else) out.push(...allStmts(st.else));
      if (st.body) out.push(...allStmts(st.body));
    }
    return out;
  }
  const all = allStmts(stmts);
  for (let pass = 0; pass < 4; pass++) {
    let changed = false;
    for (const st of all) {
      if (st.type === 'assign' && st.op === '=') {
        const rhs = String(st.expr || '').trim();
        let t = null;
        if (/~\(|=>/.test(rhs)) t = 'string';
        else if (/\.to_string\s*\(\)|String\s*\(|"[^"]*"|'[^']*'/.test(rhs)) t = 'string';
        else if (/\/.+\/[gimsuy]*|\b_lia_re_exec\b/.test(rhs)) t = 'string';
        else if (/^(true|false)$/.test(rhs)) t = 'bool';
        else if (/==|!=|<=|>=|<|>/.test(rhs)) t = 'bool';
        else if (/\b(length|len|is_empty|Math\.abs|Math\.round|_lia_abs|_lia_round|_lia_num|parseFloat)\b/.test(rhs)) t = 'int';
        else if (/[a-zA-Z_$][\w$]*\s*[+\-*/]\s*[a-zA-Z_$][\w$]*(\[[^\]]+\])?/.test(rhs)) {
          if (types.get(st.id) === 'string' || isStringishId(st.id)) t = 'string';
          else t = 'int';
        }
        else if (/[a-zA-Z_$][\w$]*\s*\+\+/.test(rhs)) t = 'int';
        else if (/[a-zA-Z_$][\w$]*\s*[+\-*/%]\s*\d/.test(rhs)) t = 'int';
        else if (/^\d+\s*[+\-*/]\s*[a-zA-Z_$][\w$]*/.test(rhs)) t = 'int';
        else if (/^\d+$/.test(rhs)) t = 'int';
        else if (/^[A-Za-z_][\w]*$/.test(rhs) && types.has(rhs)) t = types.get(rhs);
        if (t && types.get(st.id) !== t) {
          if (!(types.get(st.id) === 'string' && t === 'int')) {
            types.set(st.id, t);
            changed = true;
          }
        }
      } else if (st.type === 'return') {
        let rhs = String(st.expr || '').trim();
        if (rhs.startsWith('return ') || rhs.startsWith('return\t')) rhs = rhs.slice(6).trim();
        let t = null;
        if (/~\(|=>/.test(rhs)) t = 'string';
        else if (/\.to_string\s*\(\)|String\s*\(|"[^"]*"|'[^']*'/.test(rhs)) t = 'string';
        else if (/\/.+\/[gimsuy]*|\b_lia_re_exec\b/.test(rhs)) t = 'string';
        else if (/^(true|false)$/.test(rhs)) t = 'bool';
        else if (/===|!==|==|!=|<=|>=|<|>|&&|\|\||is_empty/.test(rhs)) t = 'bool';
        else if (/\b(length|len|is_empty|Math\.abs|Math\.round|_lia_abs|_lia_round|_lia_num|parseFloat)\b/.test(rhs)) t = 'int';
        else if (/^\d+$/.test(rhs) || /^\d+\.\d+$/.test(rhs)) t = 'int';
        else if (/^[A-Za-z_][\w]*$/.test(rhs) && types.has(rhs)) t = types.get(rhs);
        else if (/[a-zA-Z_$][\w$]*\s*[+\-*/%&|^]\s*[a-zA-Z_$0-9]/.test(rhs)) t = 'int';
        else if (/^\[.*\]$/.test(rhs)) t = 'array';
        if (t && types.get('__return') !== t) {
          types.set('__return', t);
          changed = true;
        }
      }
    }
    if (!changed) break;
  }
  return types;
}

export function isStringishId(id) {
  const s = String(id || '');
  if (isNumishId(s)) return false;
  return /^(str|ch|pad|fmt|s|key|name|cache|match|unit|matchUnit|value|id|alphabet|urlAlphabet)$/i.test(s) || /str|fmt|ch|pad|alphabet/i.test(s);
}

function asBoolCond(rewritten, target) {
  let t = String(rewritten || '').trim();
  if (!t) return t;
  if (/^\([A-Za-z_][\w]*\)$/.test(t)) t = t.slice(1, -1);
  if (/true|false|is_empty|_lia_empty|_lia_falsy|_lia_truthy|_lia_includes|_lia_re_test|_lia_and|==|!=|<=|>=|<|>/.test(t)) return t;
  const callm = t.match(/^([A-Za-z_][\w]*)\s*\(/);
  if (callm && isBoolFnName(callm[1])) return t;
  if (/_lia_obj\(|_lia_get\(|_lia_at\(/.test(t)) {
    if (target === 'rust') return `!${t}.is_empty()`;
    if (target === 'java') return `_lia_truthy(${t})`;
    if (target === 'go') return `!_lia_falsy(${t})`;
    if (target === 'c') return '0';
  }
  if (/^[A-Za-z_][\w]*$/.test(t) && !isNumishId(t)) {
    if (target === 'java') return `_lia_truthy(${t})`;
    if (target === 'rust') return `!${t}.is_empty()`;
    if (target === 'go') return `!_lia_falsy(${t})`;
    if (target === 'c') return `${t} != NULL && ${t}[0] != 0`;
  }
  if (target === 'go' || target === 'c' || target === 'java' || target === 'rust') return `(${t}) != 0`;
  return t;
}

export function emitCond(cond, target) {
  let t = String(cond || '').trim();
  t = t.replace(/\b([A-Za-z_][\w]*)--\s*>\s*0/g, '$1 > 0');
  t = t.replace(/\b([A-Za-z_][\w]*)--/g, '$1 != 0');
  if (t === 'true') {
    if (target === 'c') return '1';
    if (target === 'go') return 'true';
    return 'true';
  }
  if (/^[A-Za-z_][\w]*$/.test(t) && isNumishId(t)) {
    if (target === 'go') return `_lia_num(${t})!=0`;
    if (target === 'rust' || target === 'java' || target === 'c') return `${t} != 0`;
  }
  return asBoolCond(rewriteExpr(t, target), target);
}

function emitDottedSet(id, rhs, target, pad) {
  const idx = String(id).match(/^([A-Za-z_$][\w$]*)\[(.+)\]$/);
  const obj = idx ? idx[1] : id.slice(0, String(id).indexOf('.'));
  const key = idx ? rewriteExpr(idx[2], target) : JSON.stringify(id.slice(String(id).indexOf('.') + 1));
  if (target === 'py') return `${pad}_lia_set(${obj}, ${key}, ${rhs})`;
  if (target === 'go') return `${pad}_lia_set(${obj}, ${key}, ${rhs})`;
  if (target === 'rust') return `${pad}_lia_set(&${obj}, ${key}, ${rhs});`;
  if (target === 'java') return `${pad}_lia_set(${obj}, ${key}, ${rhs});`;
  if (target === 'c') return `${pad}_lia_set(${obj}, ${key});`;
  return `${pad}${id} = ${rhs};`;
}

export function assignOpLine(id, op, expr, target, pad, types) {
  const rhs = rewriteExpr(expr, target);
  if (String(id).includes('.') || /\[[^\]]+\]/.test(String(id))) return emitDottedSet(id, rhs, target, pad);
  const rhsId = /^[A-Za-z_][\w]*$/.test(String(rhs).trim()) ? String(rhs).trim() : null;
  const idType = types?.get(id);
  if (op === '=') {
    if (target === 'rust' && /^".*"$/.test(String(rhs).trim())) {
      return `${pad}${id} = ${rhs}.to_string();`;
    }
    if (target === 'rust' && (idType === 'String' || idType === 'string') && rhsId) {
      return `${pad}${id} = ${rhsId}.clone();`;
    }
    return `${pad}${id} = ${rhs}${target === 'go' ? '' : ';'}`;
  }
  if (op === '+=') {
    if (isNumishId(id)) {
      if (target === 'go') return `${pad}${id} = _lia_num(${id}) + _lia_num(${rhs})`;
      if (target === 'rust') return `${pad}${id} = ${id} + (${rhs});`;
      return `${pad}${id} += ${rhs};`;
    }
    if (target === 'go') return `${pad}${id} = _lia_cat(${id}, ${rhs})`;
    if (target === 'rust') return `${pad}${id} = format!("{}{}", &${id}, &${rhs});`;
    if (target === 'c') return `${pad}${id} = _lia_cat_c(${id}, ${rhs});`;
    return `${pad}${id} = ${id} + ${rhs};`;
  }
  const bin = op.endsWith('=') ? op.slice(0, -1) : op;
  if (target === 'go') return `${pad}${id} = _lia_num(${id}) ${bin} _lia_num(${rhs})`;
  if (target === 'rust') return `${pad}${id} = ${id} ${bin} ${rhs};`;
  return `${pad}${id} ${op} ${rhs};`;
}

/** JS `while (++i < n)` → increment then compare (Go/Rust have no prefix ++ in cond). */
export function splitPrefixIncCond(cond) {
  const m = String(cond || '').match(/^\+\+([A-Za-z_][\w]*)\s*([<>]=?)\s*([\s\S]+)$/);
  if (!m) return null;
  return { id: m[1], op: m[2], rhs: m[3].trim() };
}

function rewriteTemplateLiterals(s, target) {
  return String(s || '').replace(/`([^`]*)`/g, (_, inner) => {
    const parts = [];
    let last = 0;
    const re = /\$\{([^}]*)\}/g;
    let m;
    while ((m = re.exec(inner))) {
      if (m.index > last) parts.push(JSON.stringify(inner.slice(last, m.index)));
      parts.push(m[1]);
      last = m.index + m[0].length;
    }
    if (last < inner.length) parts.push(JSON.stringify(inner.slice(last)));
    if (!parts.length) return '""';
    if (target === 'go') return parts.reduce((a, b) => `_lia_cat(${a},${b})`);
    if (target === 'c') return parts.reduce((a, b) => `_lia_cat_c(${a},${b})`);
    if (target === 'rust') return parts.reduce((a, b) => `format!("{}{}", &${a}, &${b})`);
    return parts.join(' + ');
  });
}

function stripJsArrowIife(s) {
  let t = String(s || '');
  if (/\bNumber\.isFinite\b/.test(t) && (t.includes('=>') || t.includes('__c'))) {
    const m = t.match(/Number\.isFinite\s*\(\s*([A-Za-z_][\w]*)\s*\)/);
    if (m) return `_lia_isfinite(${m[1]})`;
    const plus = t.match(/\+\s*([A-Za-z_][\w]*)/);
    if (plus) return `_lia_isfinite(${plus[1]})`;
  }
  t = t.replace(/\bNumber\.isFinite\b(?!\s*\()/g, 'true');
  return t;
}

function stubClosureExpr(target) {
  if (target === 'go') return 'nil';
  if (target === 'rust') return 'String::new()';
  if (target === 'java') return 'null';
  if (target === 'c') return '0';
  if (target === 'py') return 'None';
  if (target === 'ts') return '(() => "")';
  return null;
}

export function rewriteExpr(expr, target) {
  let s = String(expr || '');
  if (/~\(|=>/.test(s)) {
    const stub = stubClosureExpr(target);
    if (stub != null) return stub;
  }
  if (target === 'js' || target === 'ts') {
    s = rewriteIifeTernary(s);
    s = s.replace(/!==/g, '!==');
    s = s.replace(/!=(?!\s*(?:null|undefined)\b)/g, '!==');
    s = s.replace(/(^|[^=!<>])==(?!=)(?!\s*(?:null|undefined)\b)/g, '$1===');
    return s;
  }
  s = rewriteHostExpr(s, target);
  if (target !== 'js' && target !== 'ts') {
    s = s.replace(/\\u\{([0-9a-fA-F]+)\}/g, (_, h) => {
      const n = parseInt(h, 16);
      if (target === 'rust') return `\\u{${h.toLowerCase()}}`;
      if (n <= 0xFF) return `\\x${n.toString(16).padStart(2, '0')}`;
      return `\\u${n.toString(16).padStart(4, '0')}`;
    });
  }
  s = s.replace(/\bdelete\s+/g, '');
  s = s.replace(/\barguments\b/g, target === 'py' ? 'None' : target === 'go' ? 'nil' : target === 'c' ? '0' : target === 'rust' ? 'String::new()' : 'null');
  s = stripJsArrowIife(s);
  s = s.replace(/\?\./g, '.');
  s = s.replace(/\?\?/g, '||');
  s = rewriteTemplateLiterals(s, target);
  s = s.replace(/\bArray\s*\(([^)]*)\)\s*\.\s*join\s*\(([^)]*)\)/g, '_lia_str($2)');
  s = s.replace(
    /([A-Za-z_][\w]*)\.(?!length\b|trim\b|charCodeAt\b|indexOf\b|includes\b)([A-Za-z_][\w]*)\b(?!\s*\()(?!\s*=(?!=))/g,
    target === 'rust' ? '_lia_get(&$1,"$2")' : '_lia_get($1,"$2")',
  );
  s = collapseHostChains(s);
  if (target !== 'rust') s = s.replace(/\b[A-Za-z_][\w]*\.clone\s*\(/g, '_lia_obj(');
  let prevObj;
  do {
    prevObj = s;
    s = s.replace(/\{[^{}]*\}/g, '_lia_obj()');
  } while (s !== prevObj);
  s = s.replace(/\b([A-Za-z_][\w]*)\s*-\s*\1\b/g, '0');
  if (target === 'py') {
    s = s.replace(/&&/g, ' and ').replace(/\|\|/g, ' or ');
    s = s.replace(/!(?!=)/g, 'not ');
    s = s.replace(/\btypeof\s+([A-Za-z_][\w]*)/g, '_lia_typeof($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s+instanceof\s+[A-Za-z_][\w.]*/g, '_lia_instanceof($1)');
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisNaN\s*\(/g, '_lia_isnan(');
    s = s.replace(/===/g, '==').replace(/!==/g, '!=');
    s = s.replace(/\bString\(([^)]+)\)/g, 'str($1)');
    s = s.replace(/\bNumber\(([^)]+)\)/g, 'float($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.length\b/g, 'len($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.trim\s*\(\s*\)/g, '$1.strip()');
    s = s.replace(/([A-Za-z_][\w]*)\.charCodeAt\(([^)]+)\)/g, 'ord($1[$2])');
    s = s.replace(/\btrue\b/g, 'True').replace(/\bfalse\b/g, 'False');
    s = s.replace(/\bnull\b/g, 'None').replace(/\bundefined\b/g, 'None');
    return rewriteTernaries(s, (c, a, b) => `(${a} if ${c} else ${b})`);
  }
  if (target === 'go') {
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/_lia_falsy\(([A-Za-z_][\w]*)\)&&\1!=0/g, '_lia_falsy($1)');
    s = s.replace(/!(?!=)([A-Za-z_][\w]*)\b(?!\s*[\(.])/g, '_lia_falsy($1)');
    s = s.replace(/''/g, '""');
    s = s.replace(/'([^']*)'/g, (_, inner) => JSON.stringify(inner));
    s = s.replace(
      /((?:_lia_get\([^)]+\)|_lia_at\([^)]+\)|[A-Za-z_][\w]*))\s*\|\|\s*((?:_lia_get\([^)]+\)|_lia_at\([^)]+\)|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))/g,
      '_lia_or($1,$2)',
    );
    s = s.replace(/!(?!=)([A-Za-z_][\w]*\([^)]*\))/g, '_lia_falsy($1)');
    s = s.replace(/&_lia_/g, '_lia_');
    s = s.replace(/\btypeof\s+([A-Za-z_][\w]*)/g, '_lia_typeof($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s+instanceof\s+[A-Za-z_][\w.]*/g, '_lia_instanceof($1)');
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisNaN\s*\(/g, '_lia_isnan(');
    s = s.replace(/===/g, '==').replace(/!==/g, '!=');
    s = s.replace(/\bString\(([^)]+)\)/g, '_lia_str($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.length\b/g, '_lia_len($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*-\s*_lia_len\(/g, '_lia_num($1)-_lia_len(');
    s = s.replace(/([A-Za-z_][\w]*)\.trim\s*\(\s*\)/g, '_lia_str($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.charCodeAt\(([^)]+)\)/g, '_lia_code_at($1,$2)');
    s = s.replace(/\btrue\b/g, 'true').replace(/\bfalse\b/g, 'false');
    s = s.replace(/\bcache\[([^\]]+)\]/g, 'cache[_lia_num($1)]');
    s = s.replace(/\b([A-Za-z_][\w]*)\[([^\]]+)\]/g, '_lia_at($1,$2)');
    s = collapseHostChains(s);
    s = s.replace(/\b([A-Za-z_][\w]*)\s*&\s*/g, '_lia_num($1) & ');
    s = s.replace(/\bnull\b|\bundefined\b/g, 'nil');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*(<=|>=|<|>|==|!=)\s*(-?\d+)/g, '_lia_num($1) $2 $3');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\/\s*([A-Za-z_][\w]*)\b/g, '_lia_num($1)/_lia_num($2)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\*\s*(\d+\.\d+)/g, '_lia_f64($1)*$2');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*%\s*(-?\d+)/g, '_lia_num($1)%$2');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\*\s*([A-Za-z_][\w]*)\b/g, (m, a, b) => (
      plusIsNumeric(a, b) || isNumishId(a) || isNumishId(b) ? `_lia_num(${a})*_lia_num(${b})` : m
    ));
    s = s.replace(/\b([A-Za-z_][\w]*)\s*(<=|>=|<|>)\s*([A-Za-z_][\w]*)\b(?!\s*\()/g, '_lia_num($1) $2 _lia_num($3)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*(<=|>=|<|>)\s*(_lia_f64\([^)]+\)\s*\*\s*\d+\.\d+)/g, '_lia_f64($1) $2 $3');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*==\s*("(?:\\.|[^"\\])*")/g, '_lia_str($1)==$2');
    s = s.replace(/!_lia_get\(([^)]+)\)/g, '_lia_falsy(_lia_get($1))');
    s = rewriteTernaries(s, (c, a, b) => `_lia_if(${c},${a},${b})`);
    let prevGo;
    do {
      prevGo = s;
      s = s.replace(
        /((?:_lia_cat\([^()]*\)|_lia_str\([^)]+\)|_lia_round\([^)]+\)|\([^()]+\)|[A-Za-z_][\w]*\[[^\]]+\]|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))\s*\+\s*((?:_lia_cat\([^()]*\)|_lia_str\([^)]+\)|_lia_round\([^)]+\)|\([^()]+\)|[A-Za-z_][\w]*\[[^\]]+\]|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))/g,
        (m, a, b) => {
          if (/_lia_num/.test(a) || /_lia_num/.test(b)) return m;
          return plusIsNumeric(a, b) ? `_lia_num(${a})+_lia_num(${b})` : `_lia_cat(${a},${b})`;
        },
      );
    } while (s !== prevGo);
    s = s.replace(
      /\(?(_lia_round\(_lia_num\([^)]+\)\s*\/\s*_lia_num\([^)]+\)\))\)?\s*\+\s*("(?:\\.|[^"\\])*")/g,
      '_lia_cat($1,$2)',
    );
    return s;
  }
  if (target === 'java') {
    s = s.replace(/\bthis\b/g, '_lia_this');
    s = s.replace(/!([A-Za-z_][\w]*)\s*&&\s*\1\s*!==?\s*0/g, '_lia_empty($1)');
    s = s.replace(/\btypeof\s+([A-Za-z_][\w]*)/g, '_lia_typeof($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s+instanceof\s+[A-Za-z_][\w.]*/g, '_lia_instanceof($1)');
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/([A-Za-z_][\w]*)\.trim\s*\(\s*\)/g, '$1.trim()');
    s = s.replace(/===/g, '==').replace(/!==/g, '!=');
    s = s.replace(/\bnull\b|\bundefined\b/g, 'null');
    s = s.replace(/'([^']*)'/g, (_, inner) => JSON.stringify(inner));
    s = s.replace(
      /([A-Za-z_][\w]*)\s*\|\|\s*("(?:\\.|[^"\\])*")/g,
      '(_lia_empty($1) ? $2 : $1)',
    );
    s = s.replace(/\bString\(([^)]+)\)/g, 'String.valueOf($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\/\s*([A-Za-z_][\w]*)\b/g, '_lia_num($1)/_lia_num($2)');
    s = s.replace(/([A-Za-z_][\w]*)\.length\b(?!\s*\()/g, 'String.valueOf($1).length()');
    s = s.replace(/\bparseInt\s*\(\s*([A-Za-z_$][\w]*)\s*,\s*10\s*\)/g, 'Long.parseLong($1)');
    s = s.replace(/\bcache\[([^\]]+)\]/g, 'cache[(int)($1)]');
    s = s.replace(/\b([A-Za-z_][\w]*)\[([^\]]+)\]/g, '_lia_at($1,$2)');
    s = collapseHostChains(s);
    s = s.replace(/!_lia_get\(([^)]+)\)/g, '!_lia_truthy(_lia_get($1))');
    s = s.replace(/_lia_get\(([^)]+)\)\s*\?/g, '_lia_truthy(_lia_get($1)) ?');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*!=\s*0\b/g, (_, id) => (
      isNumishId(id) ? `${id} != 0` : `_lia_empty(${id})`
    ));
    s = s.replace(/\b([A-Za-z_][\w]*)\s*==\s*0\b/g, (_, id) => (
      isNumishId(id) ? `${id} == 0` : `_lia_empty(${id})`
    ));
    s = rewriteTernaries(s, (c, a, b) => {
      const cond = /_lia_get\(|_lia_obj\(/.test(c) ? `_lia_truthy(${c})` : c;
      return `(${cond} ? ${a} : ${b})`;
    });
    let prevJ;
    do {
      prevJ = s;
      s = s.replace(
        /((?:String\.valueOf\([^)]+\)|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))\s*\+\s*((?:String\.valueOf\([^)]+\)|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))/g,
        (m, a, b) => (
          plusIsNumeric(a, b) || isNumishId(a) || isNumishId(b) ? m : `String.valueOf(${a})+String.valueOf(${b})`
        ),
      );
    } while (s !== prevJ);
    s = s.replace(
      /\(?(_lia_round\(_lia_num\([^)]+\)\s*\/\s*_lia_num\([^)]+\)\))\)?\s*\+\s*("(?:\\.|[^"\\])*")/g,
      'String.valueOf($1)+$2',
    );
    return s;
  }
  if (target === 'c') {
    s = s.replace(/!([A-Za-z_][\w]*)\s*&&\s*\1\s*!=\s*0/g, '($1 == NULL || $1[0] == 0)');
    s = s.replace(/'([^']*)'/g, (_, inner) => JSON.stringify(inner));
    s = s.replace(/\btypeof\s+([A-Za-z_][\w]*)/g, '_lia_typeof($1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s+instanceof\s+[A-Za-z_][\w.]*/g, '_lia_instanceof($1)');
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/===/g, '==').replace(/!==/g, '!=');
    s = s.replace(/\btrue\b/g, '1').replace(/\bfalse\b/g, '0');
    s = s.replace(/\bnull\b|\bundefined\b/g, 'NULL');
    s = s.replace(
      /([A-Za-z_][\w]*)\s*\|\|\s*((?:"(?:\\.|[^"\\])*"|[A-Za-z_][\w]*))/g,
      '_lia_or_c($1,$2)',
    );
    s = s.replace(/\bparseInt\s*\(\s*([A-Za-z_][\w]*)\s*,\s*10\s*\)/g, 'strtoll($1, NULL, 10)');
    s = s.replace(/([A-Za-z_][\w]*)\.indexOf\(([^)]+)\)\s*>=\s*0/g, 'strstr($1, $2)');
    s = s.replace(/([A-Za-z_][\w]*)\.includes\(([^)]+)\)/g, 'strstr($1, $2)');
    s = s.replace(/\bMath\.floor\s*\(([^)]+)\)/g, '($1)');
    s = s.replace(/\bString\(([^)]+)\)/g, '(const char *)($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.length\b/g, '(long long)strlen($1)');
    s = s.replace(/([A-Za-z_][\w]*)\.trim\s*\(\s*\)/g, '$1');
    s = s.replace(/\b_lia_sprintf\s*\(/g, '_lia_sprintf_ll(');
    let prevC;
    do {
      prevC = s;
      s = s.replace(
        /((?:_lia_cat_c\([^()]*\)|[A-Za-z_][\w]*\[[^\]]+\]|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))\s*\+\s*((?:_lia_cat_c\([^()]*\)|[A-Za-z_][\w]*\[[^\]]+\]|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))/g,
        (m, a, b) => {
          if (plusIsNumeric(a, b)) return m.includes(')+(') ? m : `(${a})+(${b})`;
          return `_lia_cat_c(${a},${b})`;
        },
      );
    } while (s !== prevC);
    return s;
  }
  if (target === 'rust') {
    s = s.replace(/'([^']*)'/g, (_, inner) => JSON.stringify(inner));
    s = s.replace(/\bString\(([A-Za-z_][\w]*)\s*\|\|\s*""\)/g, '$1.clone()');
    s = s.replace(/\bString\(([A-Za-z_][\w]*)\)/g, '$1.clone()');
    s = s.replace(/([A-Za-z_][\w]*)\s*\|\|\s*\[\]/g, 'if $1.is_empty() { _lia_arr(&[]) } else { $1.clone() }');
    s = s.replace(/\[\s*\]/g, '_lia_arr(&[])');
    s = s.replace(/\[((?:"(?:\\.|[^"])*"\s*,\s*)*"(?:\\.|[^"])*")\]/g, (_, inner) => `_lia_arr(&[${inner}])`);
    s = s.replace(
      /([A-Za-z_][\w]*)\s*\|\|\s*("(?:\\.|[^"\\])*"|[A-Za-z_][\w]*)/g,
      'if $1.is_empty() { $2.to_string() } else { $1.clone() }',
    );
    s = s.replace(/\.is_empty\(\)\s*&&\s*[A-Za-z_][\w]*\s*!=\s*0/g, '.is_empty()');
    s = s.replace(/\bNumber\.isFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/!(?!=)([A-Za-z_][\w]*)\b(?!\s*[\(.])/g, '$1.is_empty()');
    s = s.replace(/\btypeof\s+([A-Za-z_][\w]*)/g, '_lia_typeof(&$1)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s+instanceof\s+[A-Za-z_][\w.]*/g, '_lia_instanceof(&$1)');
    s = s.replace(/\bisFinite\s*\(/g, '_lia_isfinite(');
    s = s.replace(/\bisNaN\s*\(/g, '_lia_isnan(');
    s = s.replace(/===/g, '==').replace(/!==/g, '!=');
    s = s.replace(/\bString\(([^)]+)\)/g, '$1.to_string()');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\*\s*1\.5\b/g, '($1*3/2)');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*\/\s*([A-Za-z_][\w]*)\b/g, '_lia_num($1)/_lia_num($2)');
    s = s.replace(/\b_lia_abs\(([^)&][^)]*)\)/g, '_lia_abs(&$1)');
    s = s.replace(/\b_lia_num\(([^)&][^)]*)\)/g, '_lia_num(&$1)');
    s = s.replace(/\b_lia_isfinite\(([^)&][^)]*)\)/g, '_lia_isfinite(&$1)');
    s = s.replace(/\b_lia_includes\(([^,&][^,)]*)/g, '_lia_includes(&$1');
    s = s.replace(/([A-Za-z_][\w]*)\.length\b/g, '_lia_len(&$1)');
    s = s.replace(/([A-Za-z_][\w]*)\.trim\s*\(\s*\)/g, '$1.trim()');
    s = s.replace(/([A-Za-z_][\w]*)\.charCodeAt\(([^)]+)\)/g, '$1.as_bytes()[$2 as usize] as i64');
    s = s.replace(/([A-Za-z_][\w]*)\.charAt\s*\(/g, '_lia_at(&$1,');
    s = s.replace(/([A-Za-z_][\w]*)\.indexOf\s*\(/g, '_lia_index_of(&$1,');
    s = s.replace(/([A-Za-z_][\w]*)\.push\s*\(/g, '_lia_push(&mut $1,');
    s = s.replace(/\bObject\.keys\s*\(/g, '_lia_keys(');
    s = s.replace(/!!\(/g, '_lia_truthy(');
    s = s.replace(/\btrue\b/g, 'true').replace(/\bfalse\b/g, 'false');
    s = s.replace(/\b([A-Za-z_][\w]*)\s*!=\s*0\b/g, (_, id) => (
      isNumishId(id) || !isStringishId(id) ? `${id} != 0` : `!${id}.is_empty()`
    ));
    s = s.replace(/\b([A-Za-z_][\w]*)\s*==\s*0\b/g, (_, id) => (
      isNumishId(id) || !isStringishId(id) ? `${id} == 0` : `${id}.is_empty()`
    ));
    s = s.replace(/\bcache\[([^\[\]]+)\]/g, '_lia_cache_get(&cache, $1)');
    let prevAt;
    do {
      prevAt = s;
      s = s.replace(/\b([A-Za-z_][\w]*)\[([^\[\]]+)\]/g, '_lia_at(&$1,$2)');
    } while (s !== prevAt);
    s = collapseHostChains(s);
    s = s.replace(/!_lia_get\(([^)]+)\)/g, '_lia_get($1).is_empty()');
    s = s.replace(/_lia_get\(_lia_get\(/g, '_lia_get(&_lia_get(');
    s = s.replace(/\(_lia_str\(([^)]+)\)\)/g, '_lia_str($1)');
    s = rewriteTernaries(s, (c, a, b) => {
      const cond = /_lia_get\(|_lia_obj\(/.test(c) ? `!${c}.is_empty()` : c;
      return `(if ${cond} { ${a} } else { ${b} })`;
    });
    s = s.replace(/\bnull\b|\bundefined\b/g, 'String::new()');
    let prevRs;
    do {
      prevRs = s;
      s = s.replace(
        /((?:_lia_cat\([^()]*\)|_lia_str\([^)]+\)|_lia_round\([^)]+\)|_lia_cache_get\([^)]+\)|\([^()]+\)|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))\s*\+\s*((?:_lia_cat\([^()]*\)|_lia_str\([^)]+\)|_lia_round\([^)]+\)|_lia_cache_get\([^)]+\)|\([^()]+\)|[A-Za-z_][\w]*|"(?:\\.|[^"\\])*"))/g,
        (m, a, b) => (plusIsNumeric(a, b) ? m.replace(/\s*\+\s*/, '+') : `_lia_cat(&${a},&${b})`),
      );
    } while (s !== prevRs);
    let prevRsFold;
    do {
      prevRsFold = s;
      s = s.replace(
        /(_lia_cat\([^)]*(?:\([^)]*\)[^)]*)*\))\s*\+\s*(_lia_cat\([^)]*(?:\([^)]*\)[^)]*)*\))/g,
        '_lia_cat(&$1,&$2)',
      );
    } while (s !== prevRsFold);
    s = s.replace(
      /\(?(_lia_round\(_lia_num\([^)]+\)\s*\/\s*_lia_num\([^)]+\)\))\)?\s*\+\s*("(?:\\.|[^"\\])*")/g,
      '_lia_cat(&$1,&$2)',
    );
    s = foldPlus(s, (a, b) => (plusIsNumeric(a, b) ? null : `_lia_cat(&(${a}),&(${b}))`));
    return s;
  }
  return s;
}

export function defaultOutPath(inPath, target) {
  const ext = { js: '.js', ts: '.ts', py: '.py', go: '.go', rust: '.rs', c: '.c', java: '.java' }[target] || `.${target}`;
  const base = String(inPath).replace(/\.(lia|ail|lin)$/i, '');
  return `${base}.compiled${ext}`;
}

export function emitBanner(target) {
  return `/* generated by lia multi-emit → ${target} */`;
}
