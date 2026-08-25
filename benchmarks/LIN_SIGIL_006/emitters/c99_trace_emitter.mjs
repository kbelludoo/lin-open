// Generic C99 Trace Emitter

export function emitC99(ast) {
  let code = `// Generic C99 Emit with Semantic Trace Execution\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <stdbool.h>\n\n`;
  code += `char g_trace[64][128];\nint g_trace_count = 0;\n\nvoid trace_push(const char* msg) {\n    if (g_trace_count < 64) {\n        strncpy(g_trace[g_trace_count], msg, 127);\n        g_trace[g_trace_count][127] = '\\0';\n        g_trace_count++;\n    }\n}\n\n`;

  // Forward declarations
  for (const fn of ast.functions) {
    const cParams = fn.params.map(p => `int ${p.name}`);
    cParams.push('const char* caller_effect');
    cParams.push('const char** err');
    code += `int ${fn.name}(${cParams.join(', ')});\n`;
  }
  code += `\n`;

  for (const fn of ast.functions) {
    const cParams = fn.params.map(p => `int ${p.name}`);
    cParams.push('const char* caller_effect');
    cParams.push('const char** err');
    const myEff = fn.effects[0] || 'Pure';

    code += `int ${fn.name}(${cParams.join(', ')}) {\n`;
    code += `    char buf[128];\n`;
    code += `    snprintf(buf, sizeof(buf), "ENTER:%s", "${fn.name}"); trace_push(buf);\n`;
    code += `    const char* my_effect = "${myEff}";\n`;
    code += `    if (strcmp(caller_effect, "Pure") == 0 && strcmp(my_effect, "Pure") != 0) {\n`;
    code += `        snprintf(buf, sizeof(buf), "EFFECT_LEAK:Pure_calls_%s", my_effect); trace_push(buf);\n`;
    code += `        trace_push("ABORT:EFFECT_LEAK");\n`;
    code += `        *err = "EFFECT_LEAK"; return -1;\n`;
    code += `    }\n`;

    // Preconditions
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'pre') {
        code += `    if (!(${c.expr})) {\n`;
        code += `        trace_push("PRE_FAIL:c${i}");\n`;
        code += `        trace_push("ABORT:PRECONDITION_VIOLATED");\n`;
        code += `        *err = "PRECONDITION_VIOLATED"; return -1;\n`;
        code += `    } else {\n`;
        code += `        trace_push("PRE_PASS:c${i}");\n`;
        code += `    }\n`;
      }
    }

    // Body / Calls
    if (fn.calls) {
      const callArgs = fn.params.map(p => p.name).join(', ');
      code += `    snprintf(buf, sizeof(buf), "CALL:%s", "${fn.calls.target}"); trace_push(buf);\n`;
      code += `    int result = ${fn.calls.target}(${callArgs}, my_effect, err);\n`;
      code += `    if (strcmp(*err, "OK") != 0) { return -1; }\n`;
    } else {
      let bodyExpr = fn.body.replace(/^\^/g, '').replace(/let result = /g, '').trim();
      code += `    int result = ${bodyExpr};\n`;
    }

    // Postconditions
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'post') {
        code += `    if (!(${c.expr})) {\n`;
        code += `        trace_push("POST_FAIL:c${i}");\n`;
        code += `        trace_push("ABORT:POSTCONDITION_VIOLATED");\n`;
        code += `        *err = "POSTCONDITION_VIOLATED"; return -1;\n`;
        code += `    } else {\n`;
        code += `        trace_push("POST_PASS:c${i}");\n`;
        code += `    }\n`;
      }
    }

    code += `    snprintf(buf, sizeof(buf), "RETURN:%d", result); trace_push(buf);\n`;
    code += `    *err = "OK"; return result;\n}\n\n`;
  }

  return code;
}
