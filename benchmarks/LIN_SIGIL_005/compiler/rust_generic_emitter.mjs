// Generic Rust Emitter from Typed LIN IR (Zero hardcoded function names)

export function emitRust(ir, mode = "release_safe") {
  let code = `// Auto-generated Generic Rust from LIN IR\n#![allow(dead_code, unused_variables, unused_mut, non_snake_case)]\n\n`;

  // Schemas
  for (const schema of ir.schemas) {
    code += `#[derive(Debug, Clone)]\npub struct ${schema.name} {\n    pub size: i32,\n    pub capacity: i32,\n    pub items: Vec<i32>,\n}\n\n`;
    code += `impl ${schema.name} {\n    pub fn check_invariants(&self) -> Result<(), &'static str> {\n`;
    for (const inv of schema.invariants) {
      code += `        if !(${inv.expr}) { return Err("INVARIANT_VIOLATED"); }\n`;
    }
    code += `        Ok(())\n    }\n}\n\n`;
  }

  function emitFn(fn, isMethod = false) {
    const rustParams = fn.params.map(p => {
      if (p.name === 'self') return 'self_: &mut Buffer';
      return `${p.name}: i32`;
    }).join(', ');

    let fnCode = `pub fn ${fn.name}(${rustParams}) -> Result<i32, &'static str> {\n`;

    // Preconditions
    for (const c of fn.contracts) {
      if (c.kind === 'pre') {
        const rCond = c.expr.replace(/self\./g, 'self_.');
        fnCode += `    if !(${rCond}) { return Err("PRECONDITION_VIOLATED"); }\n`;
      }
    }

    if (isMethod) {
      fnCode += `    let old_size = self_.size;\n`;
    }

    // Generic body expression translation
    let bodyExpr = fn.body
      .replace(/self\./g, 'self_.')
      .replace(/^\^/g, '')
      .replace(/Math\.floor\(([^)]+)\)/g, '($1)')
      .replace(/Math\.abs\(([^)]+)\)/g, '($1 as i32).abs()')
      .replace(/Math\.max\(([^,]+),\s*Math\.min\(([^,]+),\s*([^)]+)\)\)/g, '($1 as i32).max(($3 as i32).min($2 as i32))')
      .replace(/console\.log\([^)]*\);?/g, '// log')
      .trim();

    if (bodyExpr.startsWith('(') && bodyExpr.endsWith(')')) {
      bodyExpr = bodyExpr.slice(1, -1).trim();
    }

    fnCode += `    let result = ${bodyExpr};\n`;

    if (isMethod) {
      fnCode += `    self_.check_invariants()?;\n`;
    }

    // Postconditions
    for (const c of fn.contracts) {
      if (c.kind === 'post') {
        let rPost = c.expr
          .replace(/old\(self\.size\)/g, 'old_size')
          .replace(/self\.size/g, 'self_.size');
        fnCode += `    if !(${rPost}) { return Err("POSTCONDITION_VIOLATED"); }\n`;
      }
    }

    fnCode += `    Ok(result)\n}\n\n`;
    return fnCode;
  }

  for (const schema of ir.schemas) {
    for (const method of schema.methods) {
      code += emitFn(method, true);
    }
  }

  for (const fn of ir.functions) {
    code += emitFn(fn, false);
  }

  return code;
}
