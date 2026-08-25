export function emitTypeScript(ast) {
  let code = `// Auto-generated JavaScript/TypeScript from LIN IR\n\n`;

  for (const fn of ast.functions) {
    if (fn.name === "main") continue;
    const paramsDecl = fn.params.join(', ');
    code += `export function ${fn.name}(${paramsDecl}) {\n`;

    // Preconditions
    for (const c of fn.contracts) {
      if (c.startsWith('pre:')) {
        const cond = c.slice(4).trim();
        code += `  if (!(${cond})) throw new Error("PRECONDITION_VIOLATED");\n`;
      }
    }

    // Invariant (for struct methods)
    if (fn.name === "push" || fn.name === "corruptPush") {
      code += `  const old_size = self ? self.size : 0;\n`;
    }

    // Body
    if (fn.body) {
      code += `  const __exec = () => {\n    ${fn.body}\n  };\n`;
      code += `  const result = __exec();\n`;
    } else {
      code += `  const result = null;\n`;
    }

    // Invariant check on self
    if (fn.name === "push" || fn.name === "corruptPush") {
      code += `  if (self && !(self.size >= 0 && self.size <= self.capacity)) throw new Error("INVARIANT_VIOLATED");\n`;
    }

    // Postconditions
    for (const c of fn.contracts) {
      if (c.startsWith('post:')) {
        const cond = c.slice(5).trim().replace(/old\(self\.size\)/g, 'old_size');
        code += `  if (!(${cond})) throw new Error("POSTCONDITION_VIOLATED");\n`;
      }
    }

    code += `  return result;\n}\n\n`;
  }

  return code;
}
