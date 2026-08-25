// Generic Typed LIN IR Parser

export function parseLinToIR(source) {
  const lines = source.split('\n');
  const schemas = [];
  const functions = [];
  let currentSchema = null;
  let currentFn = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('@') || line.startsWith('~G')) continue;

    // Schema Declaration: ~Buffer { ... }
    if (line.startsWith('~') && !line.startsWith('~G')) {
      const match = line.match(/^~([A-Za-z_][\w]*)/);
      if (match) {
        currentSchema = {
          name: match[1],
          invariants: [],
          effects: ['HeapMut'],
          methods: []
        };
        schemas.push(currentSchema);
      }
    } else if (line.startsWith('!') && (line.includes('(') && line.includes(')'))) {
      // Function Declaration: !name(param: type, ...) -> retType
      const match = line.match(/^!([A-Za-z_][\w]*)\s*\(([^)]*)\)(?:\s*->\s*([A-Za-z_][\w]*))?/);
      if (match) {
        const fnName = match[1];
        const paramsRaw = match[2].trim();
        const retType = match[3] || 'i32';
        const params = paramsRaw ? paramsRaw.split(',').map(p => {
          const parts = p.trim().split(':');
          return { name: parts[0].trim(), type: (parts[1] || 'i32').trim() };
        }) : [];

        currentFn = {
          name: fnName,
          params,
          returnType: retType,
          contracts: [],
          effects: ['Pure'],
          body: ''
        };

        if (currentSchema) {
          currentSchema.methods.push(currentFn);
        } else {
          functions.push(currentFn);
        }
      }
    } else if (line.startsWith('%')) {
      // Contract Declaration: %(pre: ...) / %(post: ...) / %(inv: ...)
      const clean = line.substring(1).trim().replace(/^\(/, '').replace(/\)$/, '').trim();
      const colonIdx = clean.indexOf(':');
      if (colonIdx > 0) {
        const kind = clean.slice(0, colonIdx).trim(); // 'pre', 'post', 'inv'
        const expr = clean.slice(colonIdx + 1).trim();
        const contractNode = { kind, expr };
        if (currentFn) {
          currentFn.contracts.push(contractNode);
        } else if (currentSchema) {
          currentSchema.invariants.push(contractNode);
        }
      }
    } else if (line.startsWith('*')) {
      // Effect Declaration: *(Pure) / *(IO) / *(HeapMut)
      const clean = line.substring(1).trim().replace(/[()]/g, '').trim();
      if (currentFn) {
        currentFn.effects = [clean];
      } else if (currentSchema) {
        currentSchema.effects = [clean];
      }
    } else if (currentFn && line.startsWith('{')) {
      // Body Capture
      let bodyLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('}')) {
        bodyLines.push(lines[i]);
        i++;
      }
      currentFn.body = bodyLines.join('\n').trim();
      currentFn = null; // end of fn
    } else if (line === '}' && currentSchema) {
      currentSchema = null;
    }
  }

  return {
    protocol: 'LIN_TYPED_IR/1.0',
    schemas,
    functions
  };
}
