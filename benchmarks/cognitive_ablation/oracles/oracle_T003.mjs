/**
 * oracle_T003.mjs — Oráculo independente para T003 (logic_state)
 */
function transpile(code) {
  let clean = code.replace(/@LIN:[^\n]+\n/g, '').replace(/=ex\{[^\}]+\}/g, '').trim();
  clean = clean.replace(/!([a-zA-Z0-9_]+)\(([^)]*)\)\s*\{/g, 'function $1($2){');
  clean = clean.replace(/\^([^;\n\}]+)/g, 'return $1');

  let out = '';
  let i = 0;
  while (i < clean.length) {
    // Strings literais
    if (clean[i] === '"' || clean[i] === "'" || clean[i] === '`') {
      const q = clean[i];
      out += q;
      i++;
      while (i < clean.length && clean[i] !== q) {
        if (clean[i] === '\\') {
          out += clean[i] + (clean[i + 1] || '');
          i += 2;
        } else {
          out += clean[i];
          i++;
        }
      }
      if (i < clean.length) {
        out += clean[i];
        i++;
      }
      continue;
    }

    if (clean[i] === '?' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      let inStr = null;
      while (j < clean.length && depth > 0) {
        const c = clean[j];
        if (inStr) {
          if (c === '\\') j += 2;
          else if (c === inStr) { inStr = null; j++; }
          else j++;
          continue;
        }
        if (c === '"' || c === "'" || c === '`') { inStr = c; j++; continue; }
        if (c === '(') depth++;
        else if (c === ')') depth--;
        j++;
      }
      const cond = clean.slice(i + 2, j - 1);
      while (j < clean.length && /\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        out += `if (${cond}) {`;
        i = j + 1;
        continue;
      }
    }

    if (clean[i] === ':' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      let inStr = null;
      while (j < clean.length && depth > 0) {
        const c = clean[j];
        if (inStr) {
          if (c === '\\') j += 2;
          else if (c === inStr) { inStr = null; j++; }
          else j++;
          continue;
        }
        if (c === '"' || c === "'" || c === '`') { inStr = c; j++; continue; }
        if (c === '(') depth++;
        else if (c === ')') depth--;
        j++;
      }
      const cond = clean.slice(i + 2, j - 1);
      while (j < clean.length && /\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        out += `else if (${cond}) {`;
        i = j + 1;
        continue;
      }
    }

    if (clean[i] === ':' && clean[i + 1] === '{') {
      out += 'else {';
      i += 2;
      continue;
    }

    if (clean[i] === '#' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      while (j < clean.length && depth > 0) {
        if (clean[j] === '(') depth++;
        else if (clean[j] === ')') depth--;
        j++;
      }
      const loopParts = clean.slice(i + 2, j - 1).split(';');
      while (j < clean.length && /\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        if (loopParts.length === 3) {
          const init = loopParts[0].trim();
          const initStr = init ? (init.includes('=') && !init.startsWith('let ') ? `let ${init}` : init) : '';
          out += `for (${initStr}; ${loopParts[1].trim()}; ${loopParts[2].trim()}) {`;
        } else {
          out += `for (${loopParts.join(';')}) {`;
        }
        i = j + 1;
        continue;
      }
    }

    out += clean[i];
    i++;
  }
  return out;
}

export async function oracle(task, candidateResult) {
  try {
    const jsSource = transpile(candidateResult.candidate_code);
    const fn = new Function('input', `
      ${jsSource}
      return solve(input);
    `);

    for (const tc of task.test_cases) {
      const input = tc.input;
      const testPassed = (() => {
        
      const res = fn(input);
      if (input.action === 'push') {
        const nextStack = [...input.stack, input.value];
        return JSON.stringify(res) === JSON.stringify({ stack: nextStack, history: [...input.history, nextStack] });
      } else if (input.action === 'pop') {
        const nextStack = input.stack.slice(0, -1);
        return JSON.stringify(res) === JSON.stringify({ stack: nextStack, history: [...input.history, nextStack] });
      } else {
        const prevStack = input.history.length > 1 ? input.history[input.history.length - 2] : input.stack;
        const prevHist = input.history.slice(0, -1);
        return JSON.stringify(res) === JSON.stringify({ stack: prevStack, history: prevHist });
      }
    
      })();
      if (!testPassed) {
        return { passed: false, hint: 'Falha no caso de teste: ' + JSON.stringify(tc) };
      }
    }
    return { passed: true };
  } catch (err) {
    return { passed: false, hint: err.message };
  }
}
