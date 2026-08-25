import { tokenize } from './lexer.mjs';
import { parseRegexLiteral } from './regex_ir.mjs';

export const LIN_HEADER = '@LIN:L1c:0.2';

export class LinParseError extends Error {
  constructor(message, tok) {
    super(tok ? `LIN_PARSE:${tok.line}:${tok.col}: ${message}` : `LIN_PARSE: ${message}`);
    this.name = 'LinParseError';
  }
}

const ASSIGN_OPS = new Set(['=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=', '>>>=', '**=', '&&=', '||=', '??=']);
const RESERVED_STMT_IDS = new Set(['return', 'function', 'var', 'let', 'const', 'case', 'default', 'new', 'delete', 'typeof', 'void', 'in', 'of', 'instanceof']);

class Parser {
  constructor(src) {
    this.src = String(src || '');
    this.toks = tokenize(this.src);
    this.pos = 0;
  }

  peek(k = 0) {
    return this.toks[Math.min(this.pos + k, this.toks.length - 1)];
  }
  next() {
    return this.toks[this.pos++];
  }
  at(type, value) {
    const t = this.peek();
    return t.type === type && (value === undefined || t.value === value);
  }
  atVal(v) {
    const t = this.peek();
    return t.type === 'punct' && t.value === v;
  }
  eat(type, value) {
    if (this.at(type, value)) {
      return this.next();
    }
    return null;
  }
  expect(type, value, what) {
    const t = this.peek();
    if (t.type !== type || (value !== undefined && t.value !== value)) {
      throw new LinParseError(`expected ${what || (value ?? type)}, got ${t.value || t.type}`, t);
    }
    return this.next();
  }
  text(fromTok, toTokExclusive) {
    return this.src.slice(fromTok.start, toTokExclusive.start);
  }
  skipTrivia() {
    while (this.at('nl') || this.at('comment')) this.next();
  }
  skipLine() {
    while (!this.at('nl') && !this.at('eof')) this.next();
  }
  findMatching(openIdx, openCh, closeCh) {
    let depth = 0;
    for (let i = openIdx; i < this.toks.length; i++) {
      const t = this.toks[i];
      if (t.type === 'punct') {
        if (t.value === openCh) depth++;
        else if (t.value === closeCh) {
          depth--;
          if (depth === 0) return i;
        }
      }
    }
    throw new LinParseError(`unmatched ${openCh}`, this.toks[openIdx]);
  }

  parseProgram() {
    const prog = {
      header: null,
      headerTag: null,
      meta: [],
      grammar: null,
      consts: null,
      exports: [],
      structs: [],
      enums: [],
      modules: [],
      uses: [],
      fns: [],
      src: this.src,
    };
    for (;;) {
      this.skipTrivia();
      if (this.at('eof')) break;
      const t = this.peek();
      if (t.type === 'punct' && t.value === '@') {
        this.next();
        const tag = this.expect('id', undefined, 'header tag');
        if (['LIN', 'LIA', 'AIL'].includes(tag.value)) {
          prog.headerTag = prog.headerTag || tag.value;
          prog.header = this.text(t, this.peekLineEnd());
          this.skipLine();
          continue;
        }
        if (!prog.header && this.at('punct', '{')) {
          const open = this.next();
          const close = this.findMatching(this.pos - 1, '{', '}');
          prog.meta.push({ text: `@${tag.value}${this.text(open, this.toks[close])}`, kv: {}, flags: [] });
          this.pos = close + 1;
          continue;
        }
        if (this.at('punct', '{')) {
          const open = this.next();
          const close = this.findMatching(this.pos - 1, '{', '}');
          prog.meta.push({ text: `@${tag.value}{...}`, kv: {}, flags: [] });
          this.pos = close + 1;
          continue;
        }
        this.skipLine();
        continue;
      }
      if (t.type === 'punct' && t.value === '~' && this.peek(1).type === 'id' && this.peek(1).value !== 'G') {
        if (this.peek(2).type === 'punct' && this.peek(2).value === '{') {
          this.next();
          this.next();
          const open = this.next();
          const close = this.findMatching(this.pos - 1, '{', '}');
          prog.meta.push({ text: `~${this.toks[this.pos - 2].value ?? ''}`, kv: {}, flags: [] });
          this.pos = close + 1;
          continue;
        }
      }
      if (t.type === 'punct' && t.value === '^') {
        const start = t;
        this.skipLine();
        prog.meta.push(parseMeta(this.text(start, this.peekSaved())));
        continue;
      }
      if (t.type === 'punct' && t.value === '~' && this.peek(1).type === 'id' && this.peek(1).value === 'G') {
        this.next();
        this.next();
        const open = this.expect('punct', '{', '~G{');
        const close = this.findMatching(this.pos - 1, '{', '}');
        prog.grammar = this.text(open, this.toks[close]);
        this.pos = close + 1;
        continue;
      }
      if (t.type === 'id' && (t.value === '$K' || t.value === '$k') && this.peek(1).type === 'punct' && (this.peek(1).value === '{' || (this.peek(1).value === '=' && this.peek(2).type === 'punct' && this.peek(2).value === '{'))) {
        this.next();
        if (this.at('punct', '=')) this.next();
        const open = this.expect('punct', '{', '$K{');
        const close = this.findMatching(this.pos - 1, '{', '}');
        prog.consts = Object.assign(prog.consts || {}, parseConstTable(this.text(open, this.toks[close]), this));
        this.pos = close + 1;
        continue;
      }
      if (t.type === 'punct' && t.value === '=' && this.peek(1).type === 'id' && this.peek(1).value === 'ex') {
        this.next();
        this.next();
        const open = this.expect('punct', '{', '=ex{');
        const close = this.findMatching(this.pos - 1, '{', '}');
        const body = this.text(open, this.toks[close]).replace(/^[^{]*\{/, '').replace(/\}\s*$/, '').replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*/g, '');
        prog.exports = prog.exports.concat(body.split(',').map((x) => x.trim()).filter(Boolean));
        this.pos = close + 1;
        continue;
      }
      if (t.type === 'id' && t.value === 'use') {
        this.next();
        const mod = this.expect('id', undefined, 'module name');
        this.expect('punct', '::', '::');
        const symbols = [];
        if (this.eat('punct', '{')) {
          for (;;) {
            this.skipTrivia();
            if (this.eat('punct', ',')) continue;
            if (this.at('punct', '}')) break;
            symbols.push(this.expect('id', undefined, 'symbol').value);
          }
          this.expect('punct', '}', '}');
        } else {
          symbols.push(this.expect('id', undefined, 'symbol').value);
        }
        this.eat('punct', ';');
        prog.uses.push({ module: mod.value, symbols });
        continue;
      }
      if (t.type === 'id' && t.value === 'mod') {
        this.next();
        const name = this.expect('id', undefined, 'mod name').value;
        const open = this.expect('punct', '{', 'mod {');
        const close = this.findMatching(this.pos - 1, '{', '}');
        const inner = this.src.slice(open.end, this.toks[close].start);
        prog.modules.push({ name, program: parseProgram(inner) });
        this.pos = close + 1;
        continue;
      }
      if (t.type === 'id' && t.value === 'struct') {
        prog.structs.push(this.parseStruct());
        continue;
      }
      if (t.type === 'id' && t.value === 'enum') {
        prog.enums.push(this.parseEnum());
        continue;
      }
      if (t.type === 'punct' && t.value === '!') {
        prog.fns.push(this.parseFn(true));
        continue;
      }
      if (t.type === 'id' && t.value === 'fn') {
        prog.fns.push(this.parseFn(false));
        continue;
      }
      throw new LinParseError(`unexpected top-level token ${JSON.stringify(t.value)}`, t);
    }
    return prog;
  }

  peekSaved() {
    return this.toks[this.pos] || this.toks[this.toks.length - 1];
  }

  peekLineEnd() {
    let i = this.pos;
    while (i < this.toks.length && this.toks[i].type !== 'nl') i++;
    return this.toks[i] || this.toks[this.toks.length - 1];
  }

  parseStruct() {
    this.expect('id', 'struct', 'struct');
    const name = this.expect('id', undefined, 'struct name').value;
    let generics = null;
    if (this.at('punct', '<')) {
      const start = this.next();
      let depth = 1;
      while (depth > 0) {
        const t = this.next();
        if (t.type === 'eof') throw new LinParseError('unterminated generics', t);
        if (t.type === 'punct' && t.value === '<') depth++;
        if (t.type === 'punct' && t.value === '>') depth--;
      }
      generics = this.text(start, this.peekSaved());
    }
    let fields = [];
    if (this.at('punct', '{')) {
      const open = this.next();
      const close = this.findMatching(this.pos - 1, '{', '}');
      fields = parseFields(this.src.slice(open.start, this.toks[close].start));
      this.pos = close + 1;
    } else {
      const end = this.peekLineEnd();
      fields = parseFields(this.text(this.peekSaved(), end));
      this.pos = end.type === 'nl' ? end : end;
    }
    return { name, generics, fields };
  }

  parseEnum() {
    this.expect('id', 'enum', 'enum');
    const name = this.expect('id', undefined, 'enum name').value;
    let generics = null;
    if (this.at('punct', '<')) {
      const start = this.next();
      let depth = 1;
      while (depth > 0) {
        const t = this.next();
        if (t.type === 'eof') throw new LinParseError('unterminated generics', t);
        if (t.type === 'punct' && t.value === '<') depth++;
        if (t.type === 'punct' && t.value === '>') depth--;
      }
      generics = this.text(start, this.peekSaved());
    }
    const variants = [];
    if (this.at('punct', '{')) {
      const open = this.next();
      const close = this.findMatching(this.pos - 1, '{', '}');
      const body = this.src.slice(open.end, this.toks[close].start);
      for (const entry of body.split(/[\n,]/)) {
        const trimmed = entry.trim().replace(/,$/, '');
        if (!trimmed) continue;
        const m = trimmed.match(/^([A-Za-z_$][\w$]*)\s*(\(([\s\S]*)\))?\s*$/);
        if (m) variants.push({ name: m[1], params: m[3] !== undefined ? m[3].trim() || null : null });
      }
      this.pos = close + 1;
    }
    return { name, generics, variants };
  }

  parseFn(bang) {
    if (bang) this.expect('punct', '!', '!');
    else this.expect('id', 'fn', 'fn');
    const name = this.expect('id', undefined, 'fn name').value;
    let generics = null;
    if (this.at('punct', '<')) {
      const start = this.next();
      let depth = 1;
      while (depth > 0) {
        const t = this.next();
        if (t.type === 'eof') throw new LinParseError('unterminated generics', t);
        if (t.type === 'punct' && t.value === '<') depth++;
        if (t.type === 'punct' && t.value === '>') depth--;
      }
      generics = this.text(start, this.peekSaved());
    }
    this.expect('punct', '(', '(');
    const openParenTok = this.toks[this.pos - 1];
    const closeParen = this.findMatching(this.pos - 1, '(', ')');
    const paramsRaw = this.src.slice(openParenTok.end, this.toks[closeParen].start);
    this.pos = closeParen + 1;

    let returnType = null;
    let effects = null;
    let cap = null;
    for (;;) {
      const t = this.peek();
      if (t.type === 'punct' && t.value === '{') break;
      if (t.type === 'eof') throw new LinParseError(`missing body for fn ${name}`, t);
      if ((t.type === 'punct' && t.value === '->') || (t.type === 'punct' && t.value === ':')) {
        const start = this.next();
        const parts = [];
        let depth = 0;
        for (;;) {
          const k = this.peek();
          if (k.type === 'eof') throw new LinParseError('unterminated return type', k);
          if (k.type === 'punct') {
            if (depth === 0 && (k.value === '{' || k.value === '~')) break;
            if ('([{'.includes(k.value)) depth++;
            else if (')]}'.includes(k.value)) {
              if (depth === 0) break;
              depth--;
            }
          }
          parts.push(this.next());
        }
        returnType = this.text(start, this.peekSaved()).trim();
        continue;
      }
      if (t.type === 'punct' && t.value === '~' && this.peek(1).type === 'id' && this.peek(1).value === 'effects') {
        this.next();
        this.next();
        const open = this.expect('punct', '{', '~effects{');
        const close = this.findMatching(this.pos - 1, '{', '}');
        effects = this.text(open, this.toks[close]).trim();
        this.pos = close + 1;
        continue;
      }
      if (t.type === 'punct' && t.value === '~' && this.peek(1).type === 'id' && this.peek(1).value === 'cap') {
        this.next();
        this.next();
        const open = this.expect('punct', '{', '~cap{');
        const close = this.findMatching(this.pos - 1, '{', '}');
        cap = this.text(open, this.toks[close]).trim();
        this.pos = close + 1;
        continue;
      }
      throw new LinParseError(`unexpected token in fn header ${JSON.stringify(t.value)}`, t);
    }
    const bodyStartTok = this.peek();
    const body = this.parseBlock();
    const bodyEndTok = this.toks[this.pos - 1];
    const rawBody = this.src.slice(bodyStartTok.start, bodyEndTok.end).replace(/^\{/, '').replace(/\}$/, '');
    const params = parseParams(paramsRaw);
    return { name, generics, params, paramsRaw, returnType, effects, cap, body, rawBody };
  }

  parseBlock() {
    this.expect('punct', '{', '{');
    const close = this.findMatching(this.pos - 1, '{', '}');
    const stmts = this.parseStmts(close);
    this.pos = close + 1;
    return stmts;
  }

  parseStmts(endIdx) {
    const stmts = [];
    for (;;) {
      while (this.atVal(';') || this.at('nl') || this.at('comment')) this.next();
      if (this.pos > endIdx || this.at('eof')) return stmts;
      if (this.at('punct', '}')) return stmts;
      const st = this.parseStmt(endIdx);
      if (st) stmts.push(st);
    }
  }

  parseStmt() {
    const t = this.peek();
    if (t.type === 'punct' && t.value === '^') {
      this.next();
      return { type: 'return', expr: this.scanExpr() };
    }
    if (t.type === 'id' && t.value === 'throw' && !this.idFollowedByScope(t)) {
      this.next();
      return { type: 'throw', expr: this.scanExpr() };
    }
    if (t.type === 'id' && t.value === 'break') {
      this.next();
      return { type: 'break' };
    }
    if (t.type === 'id' && t.value === 'continue') {
      this.next();
      return { type: 'continue' };
    }
    if (t.type === 'punct' && t.value === '?') {
      return this.parseIfChain('?');
    }
    if (t.type === 'id' && t.value === 'if' && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
      return this.parseIfChain('kw');
    }
    if (t.type === 'punct' && t.value === '#' && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
      return this.parseCForm('#');
    }
    if (t.type === 'id' && t.value === 'for' && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
      return this.parseCForm('kw');
    }
    if (t.type === 'id' && t.value === 'while' && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
      this.next();
      this.next();
      const closeP = this.findMatching(this.pos - 1, '(', ')');
      const cond = this.exprFromSpan(this.pos, closeP);
      this.pos = closeP + 1;
      const body = this.parseBlock();
      return { type: 'while', cond, body };
    }
    if (t.type === 'id' && t.value === 'match' && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
      const m = this.parseMatch();
      return { type: 'match', target: m.target, arms: m.arms };
    }
    const assign = this.tryParseAssign();
    if (assign) return assign;
    const expr = this.scanExpr();
    if (!expr.parts.length) {
      return null;
    }
    return { type: 'expr', expr };
  }

  idFollowedByScope() {
    return false;
  }
  tryParseAssign() {
    const save = this.pos;
    const t = this.peek();
    if (t.type !== 'id' || RESERVED_STMT_IDS.has(t.value)) return null;
    const startTok = t;
    this.next();
    let lhsEnd = t;
    for (;;) {
      const k = this.peek();
      if (k.type === 'eof') break;
      if (k.type === 'punct' && k.value === '.') {
        this.next();
        if (!this.at('id')) break;
        lhsEnd = this.next();
        continue;
      }
      if (k.type === 'punct' && k.value === '[') {
        const close = this.findMatching(this.pos, '[', ']');
        lhsEnd = this.toks[close];
        this.pos = close + 1;
        continue;
      }
      break;
    }
    const opTok = this.peek();
    if (opTok.type === 'punct' && ASSIGN_OPS.has(opTok.value)) {
      this.next();
      let rhs = null;
      if (this.at('id', 'match') && this.peek(1).type === 'punct' && this.peek(1).value === '(') {
        rhs = { parts: [{ kind: 'node', node: this.parseMatch() }] };
      } else {
        rhs = this.scanExpr();
      }
      return { type: 'assign', idPath: this.src.slice(startTok.start, lhsEnd.end).replace(/\s+/g, ''), op: opTok.value, rhs };
    }
    this.pos = save;
    return null;
  }

  exprFromSpan(startIdx, endIdxExclusive) {
    const saved = this.pos;
    this.pos = startIdx;
    const res = this.scanExprCore(endIdxExclusive, new Set(['eof']));
    this.pos = saved;
    return res;
  }

  scanExpr() {
    return this.scanExprCore(this.toks.length - 1, new Set([';', 'nl', '}']));
  }

  scanExprCore(endIdxExclusive, stops) {
    const parts = [];
    let rawStart = this.pos;
    let depth = 0;
    let lastLp = null;
    let i = this.pos;

    const flush = (uptoIdx) => {
      if (uptoIdx > rawStart) {
        const txt = this.src.slice(this.toks[rawStart].start, this.toks[uptoIdx].start).trim();
        if (txt) parts.push({ kind: 'raw', text: txt });
      }
    };

    while (i < endIdxExclusive) {
      const t = this.toks[i];
      if (t.type === 'eof') break;
      if (t.type === 'regex') {
        flush(i);
        const lit = parseRegexLiteral(this.src.slice(t.start, t.end));
        parts.push({ kind: 'node', node: lit || { kind: 'regex', pattern: '', flags: '', rawPattern: '' } });
        i++;
        rawStart = i;
        continue;
      }
      if (t.type === 'punct') {
        if (depth === 0 && stops.has(t.value)) break;
        if (depth === 0 && t.value === '#') {
          const nx = this.toks[i + 1];
          if (nx && nx.type === 'punct' && nx.value === '(') break;
        }
        if (depth === 0 && t.value === '?') {
          const nx = this.toks[i + 1];
          if (nx && nx.type === 'punct' && nx.value === '(') {
            let p = i - 1;
            while (p >= 0 && (this.toks[p].type === 'nl' || this.toks[p].type === 'comment')) p--;
            const ps = p >= 0 ? this.toks[p] : null;
            const operandBefore = !!ps && (
              (ps.type === 'punct' && [')', ']', '}'].includes(ps.value)) ||
              ps.type === 'id' || ps.type === 'num' ||
              ps.type === 'str' || ps.type === 'template'
            );
            if (!operandBefore) break;
          }
        }
        if (t.value === '(' || t.value === '[') {
          if (t.value === '(') lastLp = { idx: i, chunkStart: rawStart };
          depth++;
          i++;
          continue;
        }
        if (t.value === ')' || t.value === ']') {
          if (t.value === ')' && lastLp && depth <= 1) lastLp = null;
          depth = Math.max(0, depth - 1);
          i++;
          continue;
        }
        if (t.value === '}') {
          if (depth === 0) break;
          depth--;
          i++;
          continue;
        }
        if (t.value === '{') {
          depth++;
          i++;
          continue;
        }
        if (t.value === '~' && this.toks[i + 1].type === 'punct' && this.toks[i + 1].value === '(') {
          flush(i);
          const saved = this.pos;
          this.pos = i;
          const node = this.parseClosure();
          i = this.pos;
          parts.push({ kind: 'node', node });
          rawStart = i;
          void saved;
          continue;
        }
        if (t.value === '=' && this.toks[i + 1].type === 'punct' && this.toks[i + 1].value === '>') {
          const brace = this.toks[i + 2];
          if (brace && brace.type === 'punct' && brace.value === '{') {
            flush(i);
            const params = lastLp
              ? this.src.slice(this.toks[lastLp.idx].end, t.start).trim().replace(/^\(/, '').replace(/\)$/, '')
              : '';
            this.pos = i + 2;
            const body = this.parseBlock();
            parts.push({ kind: 'node', node: { kind: 'arrow', params, body } });
            i = this.pos;
            rawStart = i;
            lastLp = null;
            continue;
          }
          i += 2;
          continue;
        }
        i++;
        continue;
      }
      if (t.type === 'id') {
        if (t.value === 'function') {
          flush(i);
          this.pos = i;
          const node = this.parseFnLit();
          i = this.pos;
          parts.push({ kind: 'node', node });
          rawStart = i;
          continue;
        }
        if (
          t.value === 'match' &&
          this.toks[i + 1].type === 'punct' &&
          this.toks[i + 1].value === '(' &&
          depth === 0
        ) {
          const braceAfter = this.matchArmBrace(i);
          if (braceAfter >= 0) {
            flush(i);
            this.pos = i;
            const node = this.parseMatch();
            i = this.pos;
            parts.push({ kind: 'node', node });
            rawStart = i;
            continue;
          }
        }
        i++;
        continue;
      }
      i++;
    }
    flush(Math.min(i, endIdxExclusive));
    this.pos = Math.max(this.pos, Math.min(i, endIdxExclusive));
    return { parts };
  }

  matchArmBrace(matchIdx) {
    let j = matchIdx + 1;
    if (this.toks[j]?.value !== '(') return -1;
    let depth = 0;
    for (; j < this.toks.length; j++) {
      const t = this.toks[j];
      if (t.type === 'punct') {
        if (t.value === '(') depth++;
        else if (t.value === ')') {
          depth--;
          if (depth === 0) break;
        }
      }
    }
    let k = j + 1;
    while (k < this.toks.length && (this.toks[k].type === 'nl' || this.toks[k].type === 'comment')) k++;
    if (this.toks[k]?.type === 'punct' && this.toks[k].value === '{') return k;
    return -1;
  }

  parseClosure() {
    const tilde = this.expect('punct', '~', '~');
    this.expect('punct', '(', '(');
    const openParenTok2 = this.toks[this.pos - 1];
    const closeP = this.findMatching(this.pos - 1, '(', ')');
    const params = this.src.slice(openParenTok2.end, this.toks[closeP].start);
    this.pos = closeP + 1;
    let j = closeP + 1;
    while (j < this.toks.length && (this.toks[j].type === 'nl' || this.toks[j].type === 'comment')) j++;
    if (this.toks[j] && this.toks[j].type === 'punct' && this.toks[j].value === '{') {
      const body = this.parseBlock();
      return { kind: 'closure', params: stripTypeAnn(params), body, tok: tilde };
    }
    if (this.toks[j] && this.toks[j].type === 'punct' && this.toks[j].value === '=>') {
      this.pos = j + 1;
      const expr = this.scanExpr();
      return { kind: 'closure', params: stripTypeAnn(params), expr, tok: tilde };
    }
    throw new LinParseError('closure body expected', tilde);
  }

  parseFnLit() {
    const kw = this.expect('id', 'function', 'function');
    let name = '';
    if (this.at('id') && !RESERVED_STMT_IDS.has(this.peek().value)) {
      name = this.next().value;
    }
    this.expect('punct', '(', '(');
    const openParenTok3 = this.toks[this.pos - 1];
    const closeP = this.findMatching(this.pos - 1, '(', ')');
    const params = this.src.slice(openParenTok3.end, this.toks[closeP].start);
    this.pos = closeP + 1;
    const body = this.parseBlock();
    return { kind: 'fnlit', name, params: stripTypeAnn(params), body, tok: kw };
  }

  parseIfChain(sigil) {
    const first = this.parseIfHead(sigil);
    const entries = [];
    let els = null;
    let kwMode = sigil !== '?';
    let guard = 0;
    while (guard++ < 200) {
      let j = this.pos;
      while (j < this.toks.length && (this.toks[j].type === 'nl' || this.toks[j].type === 'comment')) j++;
      const nt = this.toks[j];
      if (!nt) break;
      if (nt.type === 'punct' && nt.value === ':') {
        const after = this.toks[j + 1];
        if (after && after.type === 'punct' && after.value === '(') {
          this.pos = j;
          const head = this.parseColonHead();
          entries.push({ cond: head.cond, body: head.body });
          continue;
        }
        if (after && after.type === 'punct' && after.value === '?') {
          this.pos = j + 1;
          const head = this.parseIfHead('?');
          entries.push({ cond: head.cond, body: head.then });
          continue;
        }
        if (after && after.type === 'id' && after.value === 'else') {
          this.pos = j + 2;
          els = this.parseBlock();
          break;
        }
        if (after && after.type === 'id' && after.value === 'if') {
          this.pos = j + 2;
          this.expect('punct', '(', '(');
          const closeP2 = this.findMatching(this.pos - 1, '(', ')');
          const cond2 = this.exprFromSpan(this.pos, closeP2);
          this.pos = closeP2 + 1;
          entries.push({ cond: cond2, body: this.parseBlock() });
          continue;
        }
        if (after && after.type === 'punct' && after.value === '{') {
          this.pos = j + 1;
          els = this.parseBlock();
          break;
        }
        this.pos = j + 1;
        const tail = this.scanExpr();
        const firstRaw = tail.parts.find((p) => p.kind === 'raw');
        if (firstRaw && /^\^/.test(firstRaw.text)) {
          firstRaw.text = firstRaw.text.replace(/^\^/, '').trim();
          return { type: 'if', cond: first.cond, then: first.then, elseIf: [], else: [{ type: 'return', expr: tail }] };
        }
        return { type: 'if', cond: first.cond, then: first.then, elseIf: [], else: [{ type: 'expr', expr: tail }] };
      }
      if (kwMode && nt.type === 'id' && nt.value === 'else') {
        this.pos = j + 1;
        if (this.at('id', 'if')) {
          this.next();
          this.expect('punct', '(', '(');
          const closeP = this.findMatching(this.pos - 1, '(', ')');
          const cond = this.exprFromSpan(this.pos, closeP);
          this.pos = closeP + 1;
          entries.push({ cond, body: this.parseBlock() });
          continue;
        }
        els = this.parseBlock();
        break;
      }
      break;
    }
    return { type: 'if', cond: first.cond, then: first.then, elseIf: entries, else: els };
  }

  parseIfHead(sigil) {
    if (sigil === '?') this.expect('punct', '?', '?');
    else this.expect('id', 'if', 'if');
    this.expect('punct', '(', '(');
    const closeP = this.findMatching(this.pos - 1, '(', ')');
    const cond = this.exprFromSpan(this.pos, closeP);
    this.pos = closeP + 1;
    const then = this.parseBlock();
    return { cond, then };
  }

  parseColonHead() {
    this.expect('punct', ':', ':');
    this.expect('punct', '(', '(');
    const closeP = this.findMatching(this.pos - 1, '(', ')');
    const cond = this.exprFromSpan(this.pos, closeP);
    this.pos = closeP + 1;
    const body = this.parseBlock();
    return { cond, body };
  }

  parseCForm(sigil) {
    if (sigil === '#') this.expect('punct', '#', '#');
    else this.expect('id', 'for', 'for');
    this.expect('punct', '(', '(');
    const openIdx = this.pos - 1;
    const closeP = this.findMatching(openIdx, '(', ')');
    const headGroups = splitTopLevelIdx(this.toks, this.pos, closeP, ';');
    this.pos = closeP + 1;
    const segText = (g) => {
      if (!g.length) return '';
      return this.src.slice(this.toks[g[0]].start, this.toks[g[g.length - 1]].end).trim();
    };
    if (headGroups.length === 3 && headGroups[0].length === 0 && headGroups[2].length === 0) {
      const g = headGroups[1];
      const cond = g.length
        ? { parts: [{ kind: 'raw', text: segText(g) }] }
        : { parts: [] };
      const body = this.parseBlock();
      return { type: 'while', cond, body };
    }
    const init = segText(headGroups[0]);
    const cg = headGroups[1];
    const cond = cg.length
      ? { parts: [{ kind: 'raw', text: segText(cg) }] }
      : { parts: [] };
    const step = segText(headGroups[2]);
    const body = this.parseBlock();
    return { type: 'for', init, cond, step, body };
  }

  parseMatch() {
    this.expect('id', 'match', 'match');
    this.expect('punct', '(', '(');
    const closeP = this.findMatching(this.pos - 1, '(', ')');
    const target = { parts: [{ kind: 'raw', text: this.src.slice(this.toks[this.pos - 1].end, this.toks[closeP].start).trim() }] };
    this.pos = closeP + 1;
    this.expect('punct', '{', '{');
    const closeB = this.findMatching(this.pos - 1, '{', '}');
    const arms = [];
    for (;;) {
      while (this.pos < closeB && (this.atVal(',') || this.atVal(';') || this.at('nl') || this.at('comment'))) this.next();
      if (this.pos >= closeB || this.at('punct', '}')) break;
      const patStart = this.pos;
      let arrowIdx = -1;
      let depth = 0;
      let i = this.pos;
      for (; i < closeB; i++) {
        const t = this.toks[i];
        if (t.type === 'punct') {
          if ('([{'.includes(t.value)) depth++;
          else if (')]}'.includes(t.value)) depth--;
          else if (depth === 0 && t.value === '=>' ) {
            arrowIdx = i;
            break;
          }
        }
      }
      if (arrowIdx < 0) throw new LinParseError('match arm missing =>', this.toks[this.pos]);
      const patRaw = this.src.slice(this.toks[patStart].start, this.toks[arrowIdx].start).trim();
      let pat = patRaw;
      let guard = null;
      const gm = splitTopLevelId(patRaw, 'if');
      if (gm) {
        pat = gm.left.trim();
        guard = gm.right.trim();
      }
      this.pos = arrowIdx + 1;
      let body;
      if (this.at('punct', '{')) {
        body = this.parseBlock();
      } else {
        const savedEnd = this.toks.length - 1;
        const expr = this.scanExprCore(savedEnd, new Set([',', ';', 'nl', '}']));
        body = [{ type: 'expr', expr }];
      }
      arms.push({ pat, guard, body });
    }
    this.pos = closeB + 1;
    return { kind: 'match', target, arms };
  }
}

function splitTopLevelIdx(toks, startIdx, endIdxExclusive, sep) {
  const groups = [[]];
  let depth = 0;
  for (let i = startIdx; i < endIdxExclusive; i++) {
    const t = toks[i];
    if (t.type === 'punct') {
      if ('([{'.includes(t.value)) depth++;
      else if (')]}'.includes(t.value)) depth--;
      else if (depth === 0 && t.value === sep) {
        groups.push([]);
        continue;
      }
    }
    groups[groups.length - 1].push(i);
  }
  return groups;
}

function splitTopLevelId(text, word) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (c === '\\') i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }
    if ('([{'.includes(c)) depth++;
    else if (')]}'.includes(c)) depth--;
    else if (depth === 0 && /\s/.test(c)) {
      const rest = text.slice(i).trimStart();
      if (rest.startsWith(word + ' ') || rest.startsWith(word + '(') || rest === word) {
        return { left: text.slice(0, i), right: text.slice(i + word.length + 1) };
      }
    }
  }
  return null;
}

export function stripTypeAnn(params) {
  if (!params || !String(params).trim()) return '';
  const parts = [];
  let current = '';
  let depth = 0;
  for (const ch of String(params)) {
    if (ch === '(' || ch === '<' || ch === '{' || ch === '[') depth++;
    else if (ch === ')' || ch === '>' || ch === '}' || ch === ']') depth--;
    if (ch === ',' && depth === 0) {
      parts.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current.trim());
  return parts
    .map((p) => (p.indexOf(':') >= 0 ? p.slice(0, p.indexOf(':')) : p).trim())
    .filter(Boolean)
    .map((p) => p.replace(/\s*\{[^}]*\}\s*$/, '').trim())
    .filter(Boolean)
    .join(', ');
}

function parseParams(paramsRaw) {
  if (!paramsRaw || !String(paramsRaw).trim()) return [];
  const parts = [];
  let current = '';
  let depth = 0;
  for (const ch of String(paramsRaw)) {
    if (ch === '(' || ch === '<' || ch === '[') depth++;
    else if (ch === ')' || ch === '>' || ch === ']') depth--;
    if (ch === ',' && depth === 0) {
      parts.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current.trim());
  return parts.filter(Boolean).map(parseParam);
}

function parseParam(p) {
  let rest = p.trim();
  let name = '';
  const nm = rest.match(/^([A-Za-z_$][\w$]*)/);
  if (nm) {
    name = nm[1];
    rest = rest.slice(name.length);
  }
  let type = null;
  let constraint = null;
  let def = null;
  const colon = rest.indexOf(':');
  if (colon >= 0) {
    rest = rest.slice(colon + 1);
    const braceIdx = rest.indexOf('{');
    const eqIdx = topLevelIndexOf(rest, '=');
    if (braceIdx >= 0 && (eqIdx < 0 || braceIdx < eqIdx)) {
      type = rest.slice(0, braceIdx).trim();
      const close = rest.lastIndexOf('}');
      constraint = rest.slice(braceIdx + 1, close >= 0 ? close : rest.length).trim();
      const after = close >= 0 ? rest.slice(close + 1) : '';
      const eq2 = topLevelIndexOf(after, '=');
      if (eq2 >= 0) def = after.slice(eq2 + 1).trim();
    } else if (eqIdx >= 0) {
      type = rest.slice(0, eqIdx).trim();
      def = rest.slice(eqIdx + 1).trim();
    } else {
      type = rest.trim();
    }
  } else {
    const eqIdx = topLevelIndexOf(rest, '=');
    if (eqIdx >= 0) {
      def = rest.slice(eqIdx + 1).trim();
    }
  }
  return { name, type, constraint, def };
}

function topLevelIndexOf(s, ch) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }
    if ('([{'.includes(c)) depth++;
    else if (')]}'.includes(c)) depth--;
    else if (depth === 0 && c === ch) return i;
  }
  return -1;
}

function parseMeta(text) {
  const kv = {};
  const flags = [];
  for (const part of text.replace(/^\^/, '').trim().split(/\s+/).filter(Boolean)) {
    const eq = part.indexOf('=');
    if (eq > 0) kv[part.slice(0, eq)] = part.slice(eq + 1);
    else flags.push(part);
  }
  return { text: text.trim(), kv, flags };
}

function parseConstTable(body) {
  const inner = body.replace(/^[^{=]*=?\s*\{/, '').replace(/\}\s*$/, '').trim();
  const entries = {};
  const flat = inner.replace(/\r?\n/g, ' ');
  for (const part of flat.split(/[ ,]+/).filter(Boolean)) {
    let eq = part.indexOf('=');
    if (eq < 0) eq = part.indexOf(':');
    if (eq < 0) continue;
    entries[part.slice(0, eq)] = part.slice(eq + 1);
  }
  return entries;
}

function parseFields(body) {
  const inner = body.replace(/^[^{]*\{/, '').replace(/\}\s*$/, '');
  const fields = [];
  for (const fLine of inner.split(/[\n,]/)) {
    const trimmed = fLine.trim().replace(/,$/, '');
    if (!trimmed) continue;
    const m = trimmed.match(/^([A-Za-z_$][\w$]*)\s*:\s*(.+)$/);
    if (m) fields.push({ name: m[1], type: m[2].trim() });
  }
  return fields;
}

export function parseProgram(src) {
  return new Parser(src).parseProgram();
}

export function parseLin(src) {
  return parseProgram(src);
}
