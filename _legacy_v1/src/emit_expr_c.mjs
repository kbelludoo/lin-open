/**
 * AST-based LIN expression → C emitter.
 *
 * Fixes three classes of bugs in the legacy regex-based C emission:
 *   1. Numeric `+` mangled into _lia_cat_c for integer variables.
 *   2. Wrong declarations from name heuristics (`isStringishId`) — e.g. any
 *      variable named `s`/`check`/`value` became `const char *`.
 *   3. Precedence divergence between JS source semantics (`==` binds tighter
 *      than `&`) and emitted C (`&` binds tighter than `==`).
 *
 * Strategy: tokenize + Pratt-parse with JavaScript operator precedence,
 * then print minimal-parens C from the AST using a small type lattice
 * (i=int, s=string, c=char-read, u=unknown-treated-as-int).
 * Any construct outside the supported subset throws; callers fall back to
 * the legacy text rewriter for that statement.
 */

const P = {
  COND: 1, LOR: 2, LAND: 3, BOR: 4, BXOR: 5, BAND: 6,
  EQ: 7, REL: 8, SHIFT: 9, ADD: 10, MUL: 11, UNARY: 12, POSTFIX: 13,
};

function isIdStart(c) { return /[A-Za-z_$]/.test(c); }
function isIdChar(c) { return /[A-Za-z0-9_$]/.test(c); }
function isDigit(c) { return /[0-9]/.test(c); }

function tokenize(src) {
  const s = String(src);
  const out = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === ' ' || c === '\t' || c === '\n' || c === '\r') { i++; continue; }
    if (isDigit(c) || (c === '.' && isDigit(s[i + 1]))) {
      let j = i;
      if (c === '0' && (s[i + 1] === 'x' || s[i + 1] === 'X')) {
        j = i + 2;
        while (j < s.length && /[0-9a-fA-F]/.test(s[j])) j++;
        out.push({ k: 'num', v: s.slice(i, j), hex: true });
        i = j;
        continue;
      }
      while (j < s.length && isDigit(s[j])) j++;
      if (s[j] === '.') { j++; while (j < s.length && isDigit(s[j])) j++; out.push({ k: 'num', v: s.slice(i, j), float: true }); }
      else out.push({ k: 'num', v: s.slice(i, j) });
      i = j;
      continue;
    }
    if (c === '"' || c === "'") {
      const q = c;
      let j = i + 1;
      let raw = '';
      while (j < s.length && s[j] !== q) {
        if (s[j] === '\\') { raw += s[j] + (s[j + 1] || ''); j += 2; continue; }
        raw += s[j];
        j++;
      }
      if (j >= s.length) throw new Error('expr_c: unterminated string');
      out.push({ k: 'str', v: raw });
      i = j + 1;
      continue;
    }
    if (isIdStart(c)) {
      let j = i;
      while (j < s.length && isIdChar(s[j])) j++;
      out.push({ k: 'id', v: s.slice(i, j) });
      i = j;
      continue;
    }
    const three = s.substr(i, 3);
    if (three === '>>>' || three === '===' || three === '!==') { throw new Error('expr_c: unsupported ' + three); }
    const two = s.substr(i, 2);
    if (['<<', '>>', '<=', '>=', '==', '!=', '&&', '||', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '++', '--'].includes(two)) {
      out.push({ k: two });
      i += 2;
      continue;
    }
    if ('+-*/%<>&|^!~?:(),.[].'.includes(c)) {
      if (c === '.' && !isDigit(s[i + 1]) && !/[)\]]/.test(s[i - 1] || '')) {
        // member access dot
      }
      out.push({ k: c });
      i++;
      continue;
    }
    if (c === '=') { out.push({ k: '=' }); i++; continue; }
    throw new Error('expr_c: unexpected char ' + JSON.stringify(c));
  }
  out.push({ k: 'end' });
  return out;
}

function parseExpr(tokens) {
  let pos = 0;
  const peek = () => tokens[pos];
  const eat = (k) => {
    if (tokens[pos].k !== k) throw new Error(`expr_c: want ${k} got ${tokens[pos].k}`);
    return tokens[pos++];
  };

  function parsePrimary() {
    const t = peek();
    if (t.k === 'num') { pos++; return { n: 'num', v: t.v }; }
    if (t.k === 'str') { pos++; return { n: 'str', v: t.v }; }
    if (t.k === 'id') {
      pos++;
      if (/^(true|false|null|undefined)$/.test(t.v)) {
        if (t.v === 'true') return { n: 'num', v: '1' };
        if (t.v === 'false') return { n: 'num', v: '0' };
        throw new Error('expr_c: null/undefined unsupported');
      }
      if (/^(new|delete|typeof|instanceof|in|of|function)$/.test(t.v)) throw new Error('expr_c: kw ' + t.v);
      let node = { n: 'id', v: t.v };
      for (;;) {
        const nx = peek();
        if (nx.k === '(') {
          pos++;
          const args = [];
          if (peek().k !== ')') {
            args.push(parseAssign());
            while (peek().k === ',') { pos++; args.push(parseAssign()); }
          }
          eat(')');
          node = { n: 'call', f: node, args };
        } else if (nx.k === '[') {
          pos++;
          const idx = parseAssign();
          eat(']');
          node = { n: 'index', b: node, i: idx };
        } else if (nx.k === '.') {
          pos++;
          const prop = eat('id').v;
          if (peek().k === '(') {
            pos++;
            const args = [];
            if (peek().k !== ')') {
              args.push(parseAssign());
              while (peek().k === ',') { pos++; args.push(parseAssign()); }
            }
            eat(')');
            node = { n: 'mcall', b: node, m: prop, args };
          } else {
            node = { n: 'prop', b: node, m: prop };
          }
        } else break;
      }
      return node;
    }
    if (t.k === '(') {
      pos++;
      const e = parseAssign();
      eat(')');
      // parenthesized: wrap so printer keeps grouping explicit
      return { n: 'paren', e };
    }
    if (t.k === '-' || t.k === '+' || t.k === '~' || t.k === '!') {
      pos++;
      const e = parseUnary();
      return { n: 'un', op: t.k, e };
    }
    if (t.k === '++' || t.k === '--') {
      pos++;
      const e = parseUnary();
      return { n: 'preinc', op: t.k, e };
    }
    throw new Error('expr_c: bad primary ' + t.k);
  }

  function parsePostfix() {
    let e = parsePrimary();
    for (;;) {
      const t = peek();
      if (t.k === '++' || t.k === '--') { pos++; e = { n: 'postinc', op: t.k, e }; }
      else break;
    }
    return e;
  }

  function parseUnary() { return parsePostfix(); }

  const BIN = [
    ['||', P.LOR], ['&&', P.LAND], ['|', P.BOR], ['^', P.BXOR], ['&', P.BAND],
    ['==', P.EQ], ['!=', P.EQ],
    ['<', P.REL], ['>', P.REL], ['<=', P.REL], ['>=', P.REL],
    ['<<', P.SHIFT], ['>>', P.SHIFT],
    ['+', P.ADD], ['-', P.ADD],
    ['*', P.MUL], ['/', P.MUL], ['%', P.MUL],
  ];
  const BINSET = new Set(BIN.map((x) => x[0]));
  const PREC_OF = Object.fromEntries(BIN);

  function parseBin(minPrec) {
    let lhs = parseUnary();
    for (;;) {
      const t = peek();
      if (!BINSET.has(t.k)) break;
      const p = PREC_OF[t.k];
      if (p < minPrec) break;
      pos++;
      const rhs = parseBin(p + 1);
      lhs = { n: 'bin', op: t.k, l: lhs, r: rhs };
    }
    return lhs;
  }

  function parseAssign() {
    const e = parseBin(0);
    const t = peek();
    if (t.k === '?') {
      pos++;
      const a = parseAssign();
      eat(':');
      const b = parseAssign();
      return { n: 'cond', c: e, a, b };
    }
    return e;
  }

  const root = parseAssign();
  if (peek().k !== 'end') throw new Error('expr_c: trailing ' + peek().k);
  return root;
}

/* ---------- typed C printing ---------- */

/** Standalone typer so buildCtx can run a fixpoint without emitting. */
function mkTypeOf(strIds, fnStr, arrays) {
  return function typeOf(n) {
    switch (n.n) {
      case 'num': return 'i';
      case 'str': return 's';
      case 'paren': return typeOf(n.e);
      case 'id':
        if (strIds.has(n.v)) return 's';
        return 'i';
      case 'index':
        return typeOf(n.b) === 's' ? 'c' : 'i';
      case 'mcall': return 'i';
      case 'call': return fnStr.has(calleeName(n.f)) ? 's' : 'i';
      case 'prop': return n.m === 'length' ? 'i' : 'u';
      case 'un': return n.op === '!' ? 'i' : typeOf(n.e);
      case 'preinc': case 'postinc': return 'i';
      case 'bin':
        if (['==', '!=', '<', '>', '<=', '>='].includes(n.op)) return 'i';
        if (n.op === '+') return (typeOf(n.l) === 's' || typeOf(n.r) === 's') ? 's' : 'i';
        if (n.op === '&&' || n.op === '||') {
          // JS returns an operand, not a boolean: `x = a || 'def'` yields a
          // string when any arm is one (over-approximation toward string).
          return (typeOf(n.l) === 's' || typeOf(n.r) === 's') ? 's' : 'i';
        }
        return 'i';
      case 'cond': return typeOf(n.a);
      default: return 'u';
    }
  };
}

function calleeName(f) {
  if (f.n === 'id') return f.v;
  if (f.n === 'paren') return calleeName(f.e);
  if (f.n === 'mcall') return null;
  return null;
}

function cStrLit(raw) {
  let out = '"';
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (c === '\\') {
      const n = raw[i + 1];
      if (n === 'n') { out += '\\n'; i++; continue; }
      if (n === 't') { out += '\\t'; i++; continue; }
      if (n === 'r') { out += '\\r'; i++; continue; }
      if (n === '0') { out += '\\0'; i++; continue; }
      if (n === '\\') { out += '\\\\'; i++; continue; }
      if (n === '"') { out += '\\"'; i++; continue; }
      if (n === "'") { out += "\\'"; i++; continue; }
      out += '\\' + n; i++; continue;
    }
    if (c === '"') out += '\\"';
    else out += c;
  }
  return out + '"';
}

function cCharLit(raw) {
  const inner = cStrLit(raw).slice(1, -1);
  return "'" + inner + "'";
}

/**
 * ctx: {
 *   intIds:Set, strIds:Set, fnInt:Set, fnStr:Set, arrays:Map<name,len>
 * }
 */
export function emitExprC(src, ctx) {
  const ast = parseExpr(tokenize(src));
  const typeOf = mkTypeOf(ctx.strIds, ctx.fnStr, ctx.arrays);

  function needsParens(child, parentPrec, side) {
    const cp = precOf(child);
    if (cp === null) return false;
    return side === 'l' ? cp < parentPrec : cp <= parentPrec;
  }

  function precOf(n) {
    switch (n.n) {
      case 'bin': return { '||': P.LOR, '&&': P.LAND, '|': P.BOR, '^': P.BXOR, '&': P.BAND, '==': P.EQ, '!=': P.EQ, '<': P.REL, '>': P.REL, '<=': P.REL, '>=': P.REL, '<<': P.SHIFT, '>>': P.SHIFT, '+': P.ADD, '-': P.ADD, '*': P.MUL, '/': P.MUL, '%': P.MUL }[n.op];
      case 'cond': return P.COND;
      case 'un': return P.UNARY;
      case 'preinc': return P.UNARY;
      case 'postinc': return P.POSTFIX;
      default: return null;
    }
  }

  function emit(n) {
    switch (n.n) {
      case 'num': return { code: n.v };
      case 'str': return { code: cStrLit(n.v), ty: 's' };
      case 'paren': {
        const e = emit(n.e);
        return { code: `(${e.code})`, ty: e.ty || typeOf(n.e) };
      }
      case 'id': return { code: n.v };
      case 'index': {
        const b = emit(n.b);
        const ix = emit(n.i);
        const bt = b.ty || typeOf(n.b);
        if (bt === 's') return { code: `(unsigned char)(${b.code})[${ix.code}]`, ty: 'c' };
        return { code: `${b.code}[${ix.code}]`, ty: 'i' };
      }
      case 'prop': {
        if (n.m === 'length') {
          if (n.b.n === 'id' && ctx.arrays.has(n.b.v)) return { code: String(ctx.arrays.get(n.b.v).len), ty: 'i' };
          const b = emit(n.b);
          if ((b.ty || typeOf(n.b)) === 's') return { code: `(long long)strlen(${b.code})`, ty: 'i' };
          throw new Error('expr_c: .length on non-string');
        }
        throw new Error('expr_c: prop ' + n.m);
      }
      case 'mcall': {
        const b = emit(n.b);
        const bt = b.ty || typeOf(n.b);
        if (n.m === 'charCodeAt') {
          const a = emit(n.args[0]);
          if (bt === 's') return { code: `(long long)(unsigned char)(${b.code})[${a.code}]`, ty: 'c' };
          throw new Error('expr_c: charCodeAt on non-string');
        }
        if (n.m === 'byteLength') return { code: `(long long)strlen(${b.code})`, ty: 'i' };
        throw new Error('expr_c: mcall ' + n.m);
      }
      case 'call': {
        const nm = calleeName(n.f);
        if (!nm) throw new Error('expr_c: complex callee');
        const args = n.args.map((a) => emit(a));
        if (nm === 'strlen' || nm === 'String' || nm === 'Number') {
          if (nm === 'strlen') return { code: `(long long)strlen(${args[0].code})`, ty: 'i' };
          throw new Error('expr_c: builtin ' + nm);
        }
        const ty = ctx.fnStr.has(nm) ? 's' : 'i';
        return { code: `${nm}(${args.map((a) => a.code).join(', ')})`, ty };
      }
      case 'un': {
        const e = emit(n.e);
        return { code: `${n.op}${needsParens(n.e, P.UNARY, 'r') ? `(${e.code})` : e.code}`, ty: n.op === '!' ? 'i' : (e.ty || 'i') };
      }
      case 'preinc': {
        const e = emit(n.e);
        return { code: `${n.op}${e.code}`, ty: 'i' };
      }
      case 'postinc': {
        const e = emit(n.e);
        return { code: `${e.code}${n.op}`, ty: 'i' };
      }
      case 'cond': {
        const c = emit(n.c);
        const a = emit(n.a);
        const b = emit(n.b);
        const cs = needsParens(n.c, P.COND, 'l') ? `(${c.code})` : c.code;
        return { code: `${cs}?(${a.code}):(${b.code})`, ty: a.ty || 'i' };
      }
      case 'bin': {
        const l = emit(n.l);
        const r = emit(n.r);
        const lt = l.ty || typeOf(n.l);
        const rt = r.ty || typeOf(n.r);
        const p = precOf(n);
        let lcode = needsParens(n.l, p, 'l') ? `(${l.code})` : l.code;
        let rcode = needsParens(n.r, p, 'r') ? `(${r.code})` : r.code;
        if (n.op === '+') {
          if (lt === 's' || rt === 's') {
            return { code: `_lia_cat_c(${lt === 's' ? l.code : `(const char*)${l.code}`}, ${rt === 's' ? r.code : `(const char*)${r.code}`})`, ty: 's' };
          }
          return { code: `${lcode} + ${rcode}`, ty: 'i' };
        }
        let op = n.op;
        if (op === '==') {
          if ((lt === 'c' && rt === 's') || (lt === 's' && rt === 'c')) {
            const lit = (lt === 's' ? n.l : n.r);
            if (lit.n === 'str' && JSON.stringify(lit.v).length - 2 === 1) {
              if (lt === 's') { lcode = cCharLit(lit.v); } else { rcode = cCharLit(lit.v); }
              op = '==';
              return { code: `${lcode} == ${rcode}`, ty: 'i' };
            }
          }
          op = '==';
        }
        if (op === '!=') op = '!=';
        if ((op === '&' || op === '|' || op === '^')) {
          // force explicit parens around operands of bitwise ops when they
          // contain comparisons — C and JS disagree on relative precedence.
          if (/\b(==|!=|<=|>=|<|>)\b/.test(lcode) && !/^\(/.test(lcode)) lcode = `(${lcode})`;
          if (/\b(==|!=|<=|>=|<|>)\b/.test(rcode) && !/^\(/.test(rcode)) rcode = `(${rcode})`;
        }
        const inner = `${lcode} ${op} ${rcode}`;
        // Comparisons are always self-parenthesized: C binds & | ^ tighter
        // than == < etc., JavaScript does not. Wrapping removes the divergence.
        if (['==', '!=', '<', '>', '<=', '>='].includes(op)) return { code: `(${inner})`, ty: 'i' };
        return { code: inner, ty: typeOf(n) };
      }
      default:
        throw new Error('expr_c: node ' + n.n);
    }
  }

  const res = emit(ast);
  return res.code;
}

/** Truthiness-aware condition emission (replaces emitCond for the subset). */
export function emitCondC(src, ctx) {
  const code = emitExprC(src, ctx);
  if (/^\s*[A-Za-z_]\w*\s*$/.test(src)) {
    const id = src.trim();
    if (ctx.strIds.has(id)) return `${id} != NULL && ${id}[0] != 0`;
    if (ctx.fnStr.has(id)) return `${id} != NULL && ${id}[0] != 0`;
    return `(${code}) != 0`;
  }
  return `(${code}) != 0`;
}
/**
 * Build per-function typing context.
 * Uses its own AST-based string-type fixpoint — the legacy inferTypes()
 * misclassifies division chains like (a+b/c)/2 as regex literals.
 */
export function buildCtx(params, types, stmts, fnNames, extraStrIds, fnSigs) {
  void types;
  const strIds = new Set(extraStrIds || []);
  const intIds = new Set();
  const arrays = new Map();
  const dynArrays = new Map();
  const fnStr = new Set();
  const arrLocals = new Map();
  let retStr = false;
  const all = [];
  (function walk(list) {
    for (const st of list || []) {
      all.push(st);
      walk(st.then); walk(st.elseIf?.map((e) => e.body)); walk(st.else); walk(st.body);
    }
  })(stmts);

  // Pass 1: constant array literals
  for (const st of all) {
    if (st.type !== 'assign' || st.op !== '=') continue;
    const rhs = String(st.expr || '').trim();
    if (/^\[.*\]$/.test(rhs)) {
      const items = rhs.slice(1, -1).trim();
      if (items === '') { arrays.set(st.id, { len: 0, items: '' }); continue; }
      const parts = [];
      {
        let depth = 0, cur = '';
        for (const chx of items) {
          if (chx === '[' || chx === '(') depth++;
          else if (chx === ']' || chx === ')') depth--;
          if (chx === ',' && depth === 0) { parts.push(cur.trim()); cur = ''; }
          else cur += chx;
        }
        parts.push(cur.trim());
      }
      if (parts.every((p) => /^-?(0[xX][0-9a-fA-F]+|\d+)$/.test(p))) {
        arrays.set(st.id, { len: parts.length, items: parts.join(',') });
      } else if (!dynArrays.has(st.id)) {
        dynArrays.set(st.id, { len: parts.length, parts });
      }
    }
  }

  // Pass 1b: identifiers passed at array-param positions become locals
  const callRe = /\b([A-Za-z_]\w*)\s*\(([^()]*?)\)/g;
  for (const st of all) {
    const chunks = [st.expr, ...(Array.isArray(st.then) ? [] : [])];
    let texts = [];
    (function tw(list) {
      for (const q of list || []) {
        texts.push(q.expr || '', q.cond || '', q.init || '', q.step || '');
        tw(q.then); tw(q.elseIf?.map((e) => e.body)); tw(q.else); tw(q.body);
      }
    })(stmts);
    for (const tx of texts) {
      if (!tx) continue;
      let mm;
      callRe.lastIndex = 0;
      while ((mm = callRe.exec(String(tx)))) {
        const callee = fnSigs ? fnSigs.get(mm[1]) : null;
        if (!callee || !callee.arrPos.size) continue;
        const args = mm[2].split(',');
        for (const pos of callee.arrPos) {
          if (pos < args.length) {
            const aid = args[pos].trim();
            if (/^[A-Za-z_]\w*$/.test(aid) && !arrays.has(aid)) arrLocals.set(aid, 64);
          }
        }
      }
    }
  }

  // Pass 2: string-ness fixpoint over assignments and returns
  for (let pass = 0; pass < 4; pass++) {
    let changed = false;
    for (const st of all) {
      if (st.type === 'assign' && st.op === '=' && !arrays.has(st.id)) {
        if (!strIds.has(st.id)) {
          if (/^['"]/.test(String(st.expr || '').trim())) { strIds.add(st.id); changed = true; continue; }
          try {
            const ast = parseExpr(tokenize(String(st.expr)));
            if (mkTypeOf(strIds, fnStr, arrays)(ast) === 's') { strIds.add(st.id); changed = true; }
          } catch { /* unsupported expr — not a string source we track */ }
        }
      } else if (st.type === 'return') {
        try {
          const ast = parseExpr(tokenize(String(st.expr).replace(/^return/, '') || st.expr));
          if (mkTypeOf(strIds, fnStr, arrays)(ast) === 's') retStr = true;
        } catch { /* ignore */ }
      }
    }
    if (!changed) break;
  }

  const paramTypes = {};
  for (const p of params) {
    if (strIds.has(p)) paramTypes[p] = 'str';
    else paramTypes[p] = 'int';
  }
  return { intIds, strIds, fnStr, arrays, dynArrays, arrLocals, paramTypes, retStr };
}
