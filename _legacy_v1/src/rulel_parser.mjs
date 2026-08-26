/**
 * Native RULEL parser for LIN repo.
 * Spec: spec/LIN_RULEL_PARSER.dicel
 */

function splitTopEntries(s) {
  const out = [];
  let cur = '';
  let depth = 0;
  let quote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < s.length) cur += s[++i];
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      cur += c;
      continue;
    }
    if (c === '(' || c === '{' || c === '[') depth++;
    else if (c === ')' || c === '}' || c === ']') depth--;
    if (c === ' ' && depth === 0) {
      if (cur.trim()) out.push(cur.trim());
      cur = '';
      continue;
    }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function parseValuePairs(body) {
  const entries = splitTopEntries(body);
  const obj = {};
  for (const e of entries) {
    const m = e.match(/^([A-Za-z_][\w_]*)=(.+)$/);
    if (m) obj[m[1]] = m[2];
    else obj[e] = true;
  }
  return obj;
}

function parseSigilGroup(body) {
  return parseValuePairs(body);
}

export function parseRulel(text) {
  const s = String(text || '').trim();
  const out = {
    header: null,
    sigils: {},
    blocks: {},
  };
  const headerRe = /^@RULEL:([^:\s]+):([^\s]+)/;
  const hm = s.match(headerRe);
  if (hm) {
    out.header = { id: hm[1], semver: hm[2] };
  }

  // ~R{ ... } sigil groups
  const sigilRe = /~R\{([\s\S]*?)\}/g;
  let m;
  while ((m = sigilRe.exec(s)) !== null) {
    Object.assign(out.sigils, parseSigilGroup(m[1]));
  }

  // .x{ ... } blocks
  const blockRe = /\.([a-z])\{([\s\S]*?)\}/g;
  while ((m = blockRe.exec(s)) !== null) {
    const key = m[1];
    const body = m[2];
    out.blocks[key] = parseValuePairs(body);
  }

  return out;
}

export function validateComms(parsed) {
  const required = ['m', 'r', 'f', 'a', 'c', 's', 'p'];
  const missing = required.filter((k) => !parsed.blocks[k]);
  return {
    ok: missing.length === 0,
    missing,
    header: parsed.header,
    rid: parsed.blocks.r?.R20 || parsed.blocks.r?.rid || null,
  };
}

function isMain() {
  try {
    return process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/'));
  } catch {
    return false;
  }
}

if (isMain()) {
  import('node:fs').then((fs) => import('node:path').then((path) => {
    const file = process.argv[2];
    if (!file) {
      console.error('Usage: node rulel_parser.mjs <file.rulel>');
      process.exit(2);
    }
    const text = fs.readFileSync(path.resolve(file), 'utf8');
    const parsed = parseRulel(text);
    console.log(JSON.stringify(parsed, null, 2));
  }));
}
