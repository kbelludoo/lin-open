// Generic Rust Trace Emitter

export function emitRust(ast) {
  let code = `// Generic Rust Emit with Semantic Trace Execution\n#![allow(dead_code, unused_variables, unused_mut, non_snake_case)]\n\n`;

  for (const fn of ast.functions) {
    const paramsList = fn.params.map(p => `${p.name}: i32`).join(', ');
    const myEff = fn.effects[0] || 'Pure';

    code += `pub fn ${fn.name}(${paramsList}, caller_effect: &str, trace: &mut Vec<String>) -> Result<i32, &'static str> {\n`;
    code += `    trace.push(format!("ENTER:{}", "${fn.name}"));\n`;
    code += `    let my_effect = "${myEff}";\n`;
    code += `    if caller_effect == "Pure" && my_effect != "Pure" {\n`;
    code += `        trace.push(format!("EFFECT_LEAK:Pure_calls_{}", my_effect));\n`;
    code += `        trace.push("ABORT:EFFECT_LEAK".to_string());\n`;
    code += `        return Err("EFFECT_LEAK");\n`;
    code += `    }\n`;

    // Preconditions
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'pre') {
        code += `    if !(${c.expr}) {\n`;
        code += `        trace.push("PRE_FAIL:c${i}".to_string());\n`;
        code += `        trace.push("ABORT:PRECONDITION_VIOLATED".to_string());\n`;
        code += `        return Err("PRECONDITION_VIOLATED");\n`;
        code += `    } else {\n`;
        code += `        trace.push("PRE_PASS:c${i}".to_string());\n`;
        code += `    }\n`;
      }
    }

    // Body / Calls
    if (fn.calls) {
      const callArgs = fn.params.map(p => p.name).join(', ');
      code += `    trace.push(format!("CALL:{}", "${fn.calls.target}"));\n`;
      code += `    let result = ${fn.calls.target}(${callArgs}, my_effect, trace)?;\n`;
    } else {
      let bodyExpr = fn.body.replace(/^\^/g, '').replace(/let result = /g, '').trim();
      code += `    let result = ${bodyExpr};\n`;
    }

    // Postconditions
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'post') {
        code += `    if !(${c.expr}) {\n`;
        code += `        trace.push("POST_FAIL:c${i}".to_string());\n`;
        code += `        trace.push("ABORT:POSTCONDITION_VIOLATED".to_string());\n`;
        code += `        return Err("POSTCONDITION_VIOLATED");\n`;
        code += `    } else {\n`;
        code += `        trace.push("POST_PASS:c${i}".to_string());\n`;
        code += `    }\n`;
      }
    }

    code += `    trace.push(format!("RETURN:{}", result));\n`;
    code += `    Ok(result)\n}\n\n`;
  }

  return code;
}
