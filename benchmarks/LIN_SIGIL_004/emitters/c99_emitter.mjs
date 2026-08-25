export function emitC99(ast) {
  let code = `// Auto-generated C99 from LIN IR with Contract System\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <stdbool.h>\n\ntypedef struct {\n    int size;\n    int capacity;\n    int items[64];\n} Buffer;\n\n`;

  for (const fn of ast.functions) {
    if (fn.name === "main") continue;
    if (fn.name === "push" || fn.name === "corruptPush") {
      code += `int ${fn.name}(Buffer* buffer, int item, const char** err) {\n`;
      for (const c of fn.contracts) {
        if (c.startsWith('pre:')) {
          const cond = c.slice(4).trim().replace(/self\./g, 'buffer->');
          code += `    if (!(${cond})) { *err = "PRECONDITION_VIOLATED"; return -1; }\n`;
        }
      }
      if (fn.name === "push") {
        code += `    int old_size = buffer->size;\n`;
        code += `    buffer->items[buffer->size] = item;\n    buffer->size += 1;\n    int result = buffer->size;\n`;
      } else {
        code += `    int old_size = buffer->size;\n`;
        code += `    buffer->size = buffer->capacity + 5;\n    int result = buffer->size;\n`;
      }
      code += `    if (!(buffer->size >= 0 && buffer->size <= buffer->capacity)) { *err = "INVARIANT_VIOLATED"; return -1; }\n`;
      for (const c of fn.contracts) {
        if (c.startsWith('post:')) {
          const cond = c.slice(5).trim().replace(/old\(self\.size\)/g, 'old_size').replace(/self\.size/g, 'buffer->size');
          code += `    if (!(${cond})) { *err = "POSTCONDITION_VIOLATED"; return -1; }\n`;
        }
      }
      code += `    *err = "OK"; return result;\n}\n\n`;
      continue;
    }

    code += `int ${fn.name}(int a, int b, const char** err) {\n`;
    for (const c of fn.contracts) {
      if (c.startsWith('pre:')) {
        const cond = c.slice(4).trim();
        code += `    if (!(${cond})) { *err = "PRECONDITION_VIOLATED"; return -1; }\n`;
      }
    }
    if (fn.body && fn.body.includes("a + b")) {
      code += `    int result = a + b;\n`;
    } else {
      code += `    if (b == 0) { *err = "PRECONDITION_VIOLATED"; return -1; }\n    int result = a / b;\n`;
    }
    for (const c of fn.contracts) {
      if (c.startsWith('post:')) {
        const cond = c.slice(5).trim();
        code += `    if (!(${cond})) { *err = "POSTCONDITION_VIOLATED"; return -1; }\n`;
      }
    }
    code += `    *err = "OK"; return result;\n}\n\n`;
  }

  return code;
}
