/**
 * Peripheral: extract simple py/go/rs fns → JS-shaped {name,params,body}
 * for LIN rewrite. Not nucleus. Skip anything not a single return expr.
 */
export function extractNativeFns(text, lang) {
  const L = String(lang || '').toLowerCase();
  if (L === 'python') return extractPy(text);
  if (L === 'go') return extractGo(text);
  if (L === 'rust') return extractRs(text);
  if (L === 'c') return extractC(text);
  if (L === 'java') return extractJava(text);
  return [];
}

function expandDefines(text) {
  const defs = [];
  const re = /^#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$/gm;
  let m;
  while ((m = re.exec(text))) {
    defs.push({ k: m[1], v: m[2].trim() });
  }
  let out = text;
  for (const d of defs) {
    out = out.replace(new RegExp(`\\b${d.k}\\b`, 'g'), d.v);
  }
  return out;
}

function matchBrace(src, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function cBodyToJs(body) {
  let s = String(body);
  s = s.replace(/\/\*[\s\S]*?\*\//g, '');
  s = s.replace(/^\s*\/\/.*$/gm, '');
  s = s.replace(/\basprintf\s*\(\s*&([A-Za-z_][\w]*)\s*,\s*([^,]+),\s*([^)]+)\)/g, '$1 = _lia_sprintf($2, $3)');
  s = s.replace(/\bstrtoll\s*\(\s*([A-Za-z_][\w]*)\s*,\s*NULL\s*,\s*10\s*\)/g, 'parseInt($1, 10)');
  s = s.replace(/\bstrstr\s*\(\s*([A-Za-z_][\w]*)\s*,\s*("[^"]+")\s*\)/g, '$1.indexOf($2)>=0');
  s = s.replace(/\b(long long|long|int|size_t|hash_t|char\s*\*|const char\s*\*|unsigned|double|float|void)\s+/g, 'let ');
  s = s.replace(/\blet \*/g, 'let ');
  s = s.replace(/,\s*\*/g, ', ');
  s = s.replace(/\bNULL\b/g, 'null');
  return s.trim();
}

export function extractC(text) {
  const expanded = expandDefines(text);
  const out = [];
  const re = /(?:^|\n)(?:static\s+|inline\s+)*(?:const\s+)?(?:unsigned\s+)?(?:long long|long|int|size_t|hash_t|char\s*\*|double|float|void)\s+\*?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{/g;
  let m;
  while ((m = re.exec(expanded))) {
    const name = m[1];
    if (/^test_|main$/i.test(name)) continue;
    const open = expanded.indexOf('{', m.index);
    const close = matchBrace(expanded, open);
    if (close < 0) continue;
    const cBody = expanded.slice(open + 1, close);
    if (/#include|goto |struct |typedef |\*\*/.test(cBody)) continue;
    const params = m[2].split(',').map((p) => {
      const t = p.trim();
      if (!t || t === 'void') return '';
      const parts = t.replace(/\s+\*/g, ' *').split(/\s+/);
      return parts[parts.length - 1].replace(/^\*+/, '');
    }).filter(Boolean);
    if (params.some((p) => /[^A-Za-z0-9_]/.test(p))) continue;
    out.push({
      name,
      params,
      body: cBodyToJs(cBody),
      cBody,
      hostLang: 'c',
    });
  }
  return out;
}

function extractPy(text) {
  const out = [];
  const re = /^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:\s*\n([ \t]+)return\s+([^\n]+)/gm;
  let m;
  while ((m = re.exec(text))) {
    const name = m[1];
    if (name.startsWith('_')) continue;
    const params = m[2].split(',').map((p) => p.trim().split('=')[0].split(':')[0].trim()).filter((p) => p && p !== 'self');
    const expr = m[4].trim().replace(/\s+#.*$/, '');
    if (/lambda|await|yield|raise|None|True|False/.test(expr) && /None|True|False/.test(expr)) {
      /* map None/True/False below */
    }
    if (/lambda|await|yield|raise/.test(expr)) continue;
    const js = expr.replace(/\bNone\b/g, 'null').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false');
    out.push({ name, params, body: `return ${js};` });
  }
  return out;
}

function extractGo(text) {
  const out = [];
  const re = /func\s+([A-Z][A-Za-z0-9_]*)\s*\(([^)]*)\)[^{]*\{\s*return\s+([^;}]+)[;]?\s*\}/g;
  let m;
  while ((m = re.exec(text))) {
    const params = m[2].split(',').map((p) => {
      const t = p.trim().split(/\s+/);
      return t[0] || '';
    }).filter(Boolean);
    if (params.some((p) => /[^A-Za-z0-9_]/.test(p))) continue;
    out.push({ name: m[1], params, body: `return ${m[3].trim()};` });
  }
  return out;
}

function rsBodyToJs(body) {
  let s = String(body);
  s = s.replace(/\/\*[\s\S]*?\*\//g, '');
  s = s.replace(/^\s*\/\/.*$/gm, '');
  // let x = expr; -> x=expr;
  s = s.replace(/\blet\s+mut\s+([A-Za-z_][\w]*)/g, '$1');
  s = s.replace(/\blet\s+([A-Za-z_][\w]*)/g, '$1');
  // return expr; -> ^expr;
  s = s.replace(/\breturn\s+/g, '^');
  // if cond { } else if { } else { }
  s = s.replace(/\bif\s+([^\{]+)\s*\{/g, '?($1){');
  s = s.replace(/\}\s*else\s+if\s*\(([^)]+)\)\s*\{/g, ':($1){');
  s = s.replace(/\}\s*else\s*\{/g, ':{');
  // for x in a..b -> #(x=a;x<b;x++) (best-effort)
  s = s.replace(/\bfor\s+([A-Za-z_][\w]*)\s+in\s+(\d+)\s*\.\.(\d+)\s*\{/g, '#($1=$2;$1<$3;$1++){');
  s = s.replace(/\bfor\s+([A-Za-z_][\w]*)\s+in\s+0\.\.([A-Za-z_][\w]*)\.len\s*\(\)\s*\{/g, '#($1=0;$1<$2.length;$1++){');
  s = s.replace(/\bfor\s+([A-Za-z_][\w]*)\s+in\s+([A-Za-z_][\w]*)\.iter\s*\(\)\s*\{/g, '#($1=0;$1<$2.length;$1++){');
  // method calls: s.len() -> s.length, s.is_empty() -> s.length===0
  s = s.replace(/\.len\s*\(\)/g, '.length');
  s = s.replace(/\.is_empty\s*\(\)/g, '.length===0');
  // unwrap / expect -> identity (best-effort)
  s = s.replace(/\.unwrap\s*\(\)/g, '');
  s = s.replace(/\.expect\s*\([^)]+\)/g, '');
  return s.trim();
}

function extractRs(text) {
  const out = [];
  const re = /fn\s+([a-z][A-Za-z0-9_]*)\s*\(([^)]*)\)[^{]*\{/g;
  let m;
  while ((m = re.exec(text))) {
    const name = m[1];
    const params = m[2].split(',').map((p) => p.trim().split(':')[0].trim()).filter((p) => p && p !== 'self' && p !== '&self' && !p.startsWith('&'));
    const open = text.indexOf('{', m.index + m[0].length - 1);
    const close = matchBrace(text, open);
    if (close < 0) continue;
    const rsBody = text.slice(open + 1, close);
    if (/unsafe|macro|await|#\[|=>|\|/.test(rsBody)) continue;
    const jsBody = rsBodyToJs(rsBody);
    if (!jsBody) continue;
    out.push({ name, params, body: jsBody, rsBody, hostLang: 'rust' });
  }
  return out;
}

function javaBodyToJs(body) {
  let s = String(body);
  s = s.replace(/\/\*[\s\S]*?\*\//g, '');
  s = s.replace(/^\s*\/\/.*$/gm, '');
  s = s.replace(/\.isEmpty\s*\(\s*\)/g, '.length===0');
  s = s.replace(/\.length\s*\(\s*\)/g, '.length');
  s = s.replace(/\b(boolean|Boolean|int|Integer|long|Long|String|double|float|char)\s+/g, 'let ');
  // if (cond) { -> ?(cond){
  s = s.replace(/\bif\s*\(([^)]+)\)\s*\{/g, '?($1){');
  // } else if (cond) { -> :(cond){
  s = s.replace(/\}\s*else\s+if\s*\(([^)]+)\)\s*\{/g, ':($1){');
  // } else { -> :{
  s = s.replace(/\}\s*else\s*\{/g, ':{');
  // for (int i=0; i<n; i++) { -> #(i=0;i<n;i++){
  s = s.replace(/\bfor\s*\(\s*(?:int|long|String)\s+([A-Za-z_][\w]*)\s*=\s*([^;]+);\s*([^;]+);\s*([^)]+)\)\s*\{/g, '#($1=$2;$3;$4){');
  // while (cond) { -> while(cond){  (compiler supports while)
  s = s.replace(/\bwhile\s*\(([^)]+)\)\s*\{/g, 'while($1){');
  // return expr; -> ^expr;
  s = s.replace(/\breturn\s+/g, '^');
  s = s.replace(
    /return\s+([^?]+?)\s*\?\s*([^:]+?)\s*:\s*([^;]+);/g,
    'if ($1) return $2; return $3;',
  );
  return s.trim();
}

export function extractJava(text) {
  const out = [];
  const re = /(?:public|private|protected)?\s*static\s+(?:final\s+)?(?:boolean|Boolean|int|Integer|long|Long|String|double|void)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{/g;
  let m;
  while ((m = re.exec(text))) {
    const name = m[1];
    if (/^test|main$/i.test(name)) continue;
    const open = text.indexOf('{', m.index + m[0].length - 1);
    const close = matchBrace(text, open);
    if (close < 0) continue;
    const javaBody = text.slice(open + 1, close);
    if (/stream\s*\(|::|->|new |class |throw |@|try\s*\{|catch\s*\{/.test(javaBody)) continue;
    const params = m[2].split(',').map((p) => {
      const t = p.trim();
      if (!t) return '';
      const parts = t.split(/\s+/);
      return parts[parts.length - 1];
    }).filter(Boolean);
    if (params.some((p) => /[^A-Za-z0-9_]/.test(p))) continue;
    out.push({
      name,
      params,
      body: javaBodyToJs(javaBody),
      javaBody,
      hostLang: 'java',
    });
  }
  return out;
}
