export function snakeCase(name) {
  return String(name)
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/-/g, '_')
    .toLowerCase();
}

const RESERVED_EMIT_ID = /^(type|fn|let|mut|impl|pub|struct|enum|match|use|mod|crate|self|Self|super|where|async|await|dyn|move|ref|box|func|interface|select|chan|defer|go|map|package|range|var|const|fallthrough|default|case|switch|break|continue|return|if|else|for|import|clone|as|in|loop|trait|unsafe|extern|static|true|false|new|try|catch|throw|this|null|class|public|private|protected|void|int|long|boolean|byte|char|short|float|double|abstract|final|native|synchronized|throws|extends|implements|instanceof|assert|volatile|transient|do|while|yield|typeof|override|virtual|init|main|bool|string|error|rune|uint|uintptr|any|comparable|make|len|cap|append|copy|delete|panic|recover|close|complex|real|imag|print|println|iota|nil|and|del|elif|except|finally|from|global|is|lambda|nonlocal|not|or|pass|raise|with|None|True|False|def|auto|register|signed|unsigned|sizeof|typedef|union|goto|restrict|inline)$/;

export function safeEmitId(id) {
  let s = String(id || '');
  if (!s || s === '_' || s === '__') return '_u';
  s = s.replace(/\$/g, 'dollar').replace(/[^A-Za-z0-9_]/g, '_');
  if (!s || !/^[A-Za-z_]/.test(s)) s = `id_${s || 'x'}`;
  if (RESERVED_EMIT_ID.test(s)) return `${s}_`;
  return s;
}

import { renderBody as coreRenderBody } from './render_core.mjs';

export function bodyTextOf(fn) {
  if (fn.__bodyText) return fn.__bodyText;
  const text = typeof fn.body === 'string' ? fn.body : coreRenderBody(fn.body || []);
  return text;
}

export function prepareNativeFn(fn) {
  const cloned = JSON.parse(JSON.stringify(fn.body || []));
  const aliases = new Map();
  const isPlainId = (s) => /^[A-Za-z_$][\w$]*$/.test(s);
  for (const st of cloned) {
    if (st.type === 'assign' && st.op === '=' && isPlainId(st.idPath)) {
      const parts = st.rhs?.parts || [];
      if (parts.length === 1 && parts[0].kind === 'raw') {
        const m = parts[0].text.trim().match(/^String\(\s*([A-Za-z_$][\w$]*)\s*\)$/);
        if (m) {
          aliases.set(st.idPath, m[1]);
          st.__drop = true;
        }
      }
    }
  }
  let filtered = cloned;
  if (aliases.size) {
    filtered = [];
    for (const st of cloned) {
      if (!st.__drop) filtered.push(st);
    }
  }
  const sub = (expr) => {
    if (!expr?.parts) return;
    for (const part of expr.parts) {
      if (part.kind === 'raw') {
        part.text = part.text.replace(/[A-Za-z_$][\w$]*/g, (w) => aliases.get(w) || w);
      } else {
        sub(part.node?.target);
        if (part.node?.arms) {
          for (const arm of part.node.arms) walk(arm.body);
        }
      }
    }
  };
  const walk = (stmts) => {
    for (const st of stmts) {
      if (st.type === 'assign' && aliases.has(st.idPath)) {
        st.idPath = aliases.get(st.idPath);
      }
      if (st.expr) sub(st.expr);
      if (st.rhs) sub(st.rhs);
      if (st.cond) sub(st.cond);
      if (st.target) sub(st.target);
      if (st.then) walk(st.then);
      if (st.else) walk(st.else);
      if (st.body) walk(st.body);
      if (st.elseIf) for (const ei of st.elseIf) {
        sub(ei.cond);
        walk(ei.body);
      }
      if (st.arms) for (const arm of st.arms) {
        walk(arm.body);
      }
    }
  };
  walk(filtered);
  fn.__preparedBody = filtered;
  fn.__bodyText = coreRenderBody(filtered);
  fn.body = filtered;
  return fn;
}
