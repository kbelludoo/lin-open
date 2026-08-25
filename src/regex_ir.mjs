/**
 * LIN Regex IR — capability nativa (spec/LIN_REGEX_001.rulel).
 * Fora do núcleo: parser/emitters consomem; verifier intacto.
 */

const REGEX_LIT_RE = /^\/(.*)\/([gimsuyvd]*)$/s;

export const FLAGS_PORTABLE = new Set(['i', 'g', 'm', 's', 'u']);
export const FLAGS_OPTIONAL = new Set(['d', 'y', 'v']);

export function parseRegexLiteral(text) {
  const s = String(text || '');
  const m = REGEX_LIT_RE.exec(s);
  if (!m) return null;
  return { kind: 'regex', pattern: unescapeSource(m[1]), rawPattern: m[1], flags: m[2] || '' };
}

/** O lexer entrega o literal cru; o pattern interno mantém escapes como escritos. */
function unescapeSource(p) {
  return p;
}

export function isRegexNode(part) {
  return part && typeof part === 'object' && part.kind === 'regex';
}

/** Classifica capabilities usadas por um padrão segundo LIN_REGEX_001. */
export function analyzeRegex(pattern, flags = '') {
  const caps = { optional: [], portableOnly: true };
  if (/[?<=]/.test('') === false) { /* noop, mantém fluxo claro */ }
  if (/\(\?<?[=!]/.test(pattern)) caps.optional.push('lookaround');
  if (/\(\?<[^!=>][^>]*>/.test(pattern)) caps.optional.push('named_group');
  if (/\\k</.test(pattern)) caps.optional.push('named_backref');
  if (/\\[1-9]/.test(pattern)) caps.optional.push('backreference');
  if (/\\p\{/i.test(pattern)) caps.optional.push('unicode_property');
  for (const f of String(flags)) {
    if (FLAGS_OPTIONAL.has(f)) caps.optional.push(`flag:${f}`);
  }
  caps.portableOnly = caps.optional.length === 0;
  return caps;
}

/** Valida padrão contra a RegExp real (oracle local); erro => inválido. */
export function validateRegex(pattern, flags = '') {
  try {
    // eslint-disable-next-line no-new
    new RegExp(pattern, flags.replace(/[dyv]/g, ''));
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e.message || e) };
  }
}

export function regexLiteralToJs(node) {
  return `/${node.rawPattern}/${node.flags}`;
}

/** Materialização por backend. Retorna código ou lança fail-closed. */
export function materializeRegex(node, target) {
  const caps = analyzeRegex(node.pattern, node.flags);
  const capTag = caps.optional.length ? ` caps=${caps.optional.join('+')}` : ' portable';
  switch (target) {
    case 'js':
    case 'ts':
      return regexLiteralToJs(node);
    case 'py': {
      if (!caps.portableOnly) throwRegexCap(target, capTag);
      const fl = ['i', 'g', 'm', 's', 'u'].filter((x) => node.flags.includes(x))
        .map((x) => ({ i: 're.I', g: '', m: 're.M', s: 're.S', u: 're.U' })[x]).filter(Boolean);
      return `re.compile(r'${pyEscape(node.rawPattern)}'${fl.length ? ', ' + fl.join('|') : ''})`;
    }
    case 'go': {
      if (!caps.portableOnly) throwRegexCap(target, capTag);
      if (node.flags.includes('u')) throwRegexCap(target, ' flag:u(RE2)');
      return `regexp.MustCompile(${JSON.stringify(goTranslate(node.rawPattern, node.flags))})`;
    }
    default:
      throwRegexCap(target, capTag + ' backend-roadmap');
  }
}

function throwRegexCap(target, tag) {
  const e = new Error(`LIN_REGEX_001: backend ${target} não materializa este regex (${tag}); fail-closed`);
  e.name = 'EmitUnsupportedError';
  e.regexCap = true;
  throw e;
}

function pyEscape(p) {
  return p.replace(/'/g, "\\'");
}

/** Traduções mínimas JS→RE2 para o subconjunto portável. */
function goTranslate(p, flags) {
  let out = p;
  if (flags.includes('i')) out = `(?i)${out}`;
  if (flags.includes('s')) out = `(?s)${out}`;
  if (flags.includes('m')) out = `(?m)${out}`;
  return out;
}
