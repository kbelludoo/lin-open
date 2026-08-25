export function renderExpr(expr) {
  if (!expr || !expr.parts) return '';
  let out = '';
  for (const part of expr.parts) {
    if (part.kind === 'raw') out += part.text;
    else out += renderNode(part.node);
  }
  return out;
}

export function renderNode(node) {
  switch (node.kind) {
    case 'closure':
    case 'fnlit': {
      const name = node.name ? ` ${node.name}` : '';
      if (node.body) {
        return `function${name}(${node.params}){${renderBody(node.body)}}`;
      }
      return `function${name}(${node.params}){return (${renderExpr(node.expr)});}`;
    }
    case 'arrow':
      return `(${node.params})=>{${renderBody(node.body)}}`;
    case 'match':
      return renderMatchArms(renderExpr(node.target), node.arms);
    default:
      throw new Error(`LIN_RENDER_NODE: unknown ${node && node.kind}`);
  }
}

export function fnParamsText(fn) {
  const segs = [];
  for (const p of fn.params || []) {
    let seg = p.name;
    if (p.def != null && p.def !== '') seg += `=${p.def}`;
    segs.push(seg);
  }
  return segs.join(',');
}

export function renderBody(stmts) {
  let out = '';
  for (const st of stmts) {
    out += renderStmt(st);
  }
  if (out && !/[;}]$/.test(out)) out += ';';
  return out;
}

function renderStmt(st) {
  switch (st.type) {
    case 'return':
      return `return ${renderExpr(st.expr)};`;
    case 'throw':
      return `throw ${renderExpr(st.expr)};`;
    case 'break':
      return 'break;';
    case 'continue':
      return 'continue;';
    case 'expr': {
      const text = renderExpr(st.expr).trim();
      if (!text) return '';
      if (/^throw\b/.test(text)) return `${text};`;
      return `${text};`;
    }
    case 'assign':
      return `${st.idPath} ${st.op} ${renderExpr(st.rhs)};`;
    case 'if':
      return renderIf(st);
    case 'blockternary':
      return `(${renderExpr(st.cond)}?${renderBody(st.then)}:${renderBody(st.elseExpr)});`;
    case 'for':
      return `for(${st.init};${renderExpr(st.cond)};${st.step}){${renderBody(st.body)}}`;
    case 'while':
      return `while(${renderExpr(st.cond)}){${renderBody(st.body)}}`;
    case 'match': {
      const target = renderExpr(st.target);
      return renderMatchArms(target, st.arms);
    }
    default:
      throw new Error(`LIN_RENDER_STMT: unknown ${st.type}`);
  }
}

function renderIf(st) {
  let out = `if(${renderExpr(st.cond)}){${renderBody(st.then)}}`;
  for (const ei of st.elseIf || []) {
    out += renderElseIf(ei);
  }
  if (st.else) {
    out += Array.isArray(st.else)
      ? `else{${renderBody(st.else)}}`
      : renderChainTail(st.else);
  }
  return out;
}

export function normalizeElse(els) {
  if (!els) return [];
  if (Array.isArray(els)) return els;
  const out = [];
  let ct = els;
  let guard = 0;
  while (ct && guard++ < 100) {
    out.push({
      type: 'if',
      cond: ct.cond == null ? { parts: [{ kind: 'raw', text: 'true' }] } : ct.cond,
      then: ct.body,
      elseIf: [],
      else: null,
    });
    ct = ct.chainTail;
  }
  return out;
}

function renderElseIf(ei) {
  return `else if(${renderExpr(ei.cond)}){${renderBody(ei.body)}}`;
}

function matchArmCond(targetExpr, arm) {
  const pat = arm.pat;
  const guard = arm.guard;
  const withGuard = (c) => (guard ? `${c}&&(${guard})` : c);

  if (pat === '_') {
    return { cond: guard ? `(${guard})` : 'true', binds: '' };
  }
  if (pat.includes('|') && !pat.startsWith('(')) {
    const subPats = pat.split('|').map((p) => p.trim()).filter(Boolean);
    return { cond: withGuard(`(${subPats.map((p) => `${targetExpr}===${p}`).join('||')})`), binds: '' };
  }
  const enumMatch = pat.match(/^([A-Za-z_$][\w$]*)\(([^)]+)\)$/);
  const tupleMatch = pat.match(/^\(([^)]+)\)$/);
  const structDestruct = pat.match(/^(?:([A-Za-z_$][\w$]*)\s*)?\{([^}]+)\}$/);

  let cond = '';
  let binds = '';
  if (enumMatch) {
    const tag = enumMatch[1];
    const v = enumMatch[2].trim();
    if (tag === 'Some') {
      cond = `(${targetExpr}!=null && (typeof ${targetExpr}==='object'?('Some' in ${targetExpr}||${targetExpr}.tag==='Some'):true))`;
      binds = `var ${v}=typeof ${targetExpr}==='object'&&${targetExpr}!==null?(${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.Some):${targetExpr};`;
    } else {
      cond = `(${targetExpr}!=null && typeof ${targetExpr}==='object' && (${targetExpr}.tag==='${tag}'||'${tag}' in ${targetExpr}))`;
      binds = `var ${v}=${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.${tag};`;
    }
  } else if (tupleMatch) {
    const elements = tupleMatch[1].split(',').map((x) => x.trim()).filter(Boolean);
    cond = `(Array.isArray(${targetExpr}) && ${targetExpr}.length >= ${elements.length})`;
    binds = elements.map((elem, idx) => `var ${elem}=${targetExpr}[${idx}];`).join('');
  } else if (structDestruct) {
    const structName = structDestruct[1];
    const fields = structDestruct[2].split(',').map((x) => x.trim()).filter(Boolean);
    cond = `(${targetExpr}!=null && typeof ${targetExpr}==='object'${structName ? ` && (${structName}===undefined || ${targetExpr} instanceof ${structName} || ${targetExpr}.__struct==='${structName}' || true)` : ''})`;
    binds = fields
      .map((f) => {
        const colon = f.indexOf(':');
        const prop = colon >= 0 ? f.slice(0, colon).trim() : f;
        const binding = colon >= 0 ? f.slice(colon + 1).trim() : f;
        return `var ${binding}=${targetExpr}.${prop};`;
      })
      .join('');
  } else if (pat === 'None') {
    cond = `(${targetExpr}==null||${targetExpr}===undefined||(typeof ${targetExpr}==='object'&&(${targetExpr}.tag==='None'||'None' in ${targetExpr})))`;
  } else if (/^[a-z_$][\w$]*$/.test(pat)) {
    binds = `var ${pat}=${targetExpr};`;
    cond = guard ? `(${guard.replace(new RegExp(`\\b${pat}\\b`, 'g'), `(${targetExpr})`)})` : 'true';
    return { cond, binds };
  } else {
    cond = `(${targetExpr}===${pat})`;
  }
  return { cond: withGuard(cond), binds };
}

export function renderMatchArms(targetExpr, arms) {
  const parts = [];
  let first = true;
  for (const arm of arms) {
    const { cond, binds } = matchArmCond(targetExpr, arm);
    const bodyStr = renderBody(arm.body);
    if (first) {
      parts.push(`if(${cond}){${binds}${bodyStr}}`);
      first = false;
    } else {
      parts.push(`else if(${cond}){${binds}${bodyStr}}`);
    }
  }
  return parts.join('');
}
