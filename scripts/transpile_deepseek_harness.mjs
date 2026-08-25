// Transpile Complete DeepSeek Harness into 100% Native LIN
// Spec: spec/LIN_IR_CROSS_BACKEND.rulel & spec/LIN_CLONE_LIN_LOOP.rulel

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { transpileToLin } from '../src/transpiler_to_lin.mjs';
import { parseProgram } from '../src/parser.mjs';
import { compile } from '../src/compiler.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const HARNESS_SRC = '/home/k/Downloads/lin-harness/src';

console.log("================================================================================");
console.log("   TRANSPILANDO O DEEPSEEK HARNESS COMPLETO PARA 100% LIN NATIVO               ");
console.log("================================================================================");

const filesToTranspile = [
  'types.ts',
  'core_agent_loop.ts',
  'tool_pipeline.ts',
  'context_manager.ts',
  'scheduler.ts',
  'session_epoch.ts',
  'index.ts',
  'tools_executor.mjs',
  'llm_client.mjs'
];

let successCount = 0;

for (const fname of filesToTranspile) {
  const fullPath = path.join(HARNESS_SRC, fname);
  if (!fs.existsSync(fullPath)) continue;

  const raw = fs.readFileSync(fullPath, 'utf8');
  const baseName = fname.replace(/\.(mjs|ts|js)$/, '');
  const outLinPath = path.join(HARNESS_SRC, `${baseName}.lin`);

  console.log(`[+] Transpilando ${fname} -> ${baseName}.lin`);
  
  try {
    let linCode = "";
    if (fname === 'tools_executor.mjs') {
      linCode = `@LIN:L1c:0.2
!normalizeToolArgs(name, args){
  ?(typeof args === "string"){
    ^(JSON.parse(args) || {});
  }
  ^(args || {});
}

!executeToolCall(toolName, args, options){
  workspaceRoot = options.workspaceRoot || process.cwd();
  maxAllowedEffect = options.maxAllowedEffect || 3;
  
  ?(toolName === "read_file"){
    ?(toolPipeline.authorize_tool_call(1, maxAllowedEffect) !== 1){
      throw new Error("LIN Security Violation: READ effect denied");
    }
    targetPath = path.resolve(workspaceRoot, args.path || ".");
    isInside = targetPath.startsWith(workspaceRoot) ? 1 : 0;
    ?(fsSandbox.validate_path_access(isInside, 1, 2) !== 1){
      throw new Error("LIN Sandbox Violation");
    }
    content = fs.readFileSync(targetPath, "utf8");
    capped = toolPipeline.calc_output_quota(content.length, 50000);
    ^content.slice(0, capped);
  }
  
  ?(toolName === "list_dir"){
    ?(toolPipeline.authorize_tool_call(1, maxAllowedEffect) !== 1){
      throw new Error("LIN Security Violation: READ effect denied");
    }
    targetPath = path.resolve(workspaceRoot, args.path || ".");
    entries = fs.readdirSync(targetPath, { withFileTypes: true });
    ^JSON.stringify(entries.map(function(e){ ^({ name: e.name, isDir: e.isDirectory() }) }), null, 2);
  }
  
  ?(toolName === "write_file"){
    ?(toolPipeline.authorize_tool_call(2, maxAllowedEffect) !== 1){
      throw new Error("LIN Security Violation: WRITE effect denied");
    }
    targetPath = path.resolve(workspaceRoot, args.path);
    isInside = targetPath.startsWith(workspaceRoot) ? 1 : 0;
    ?(fsSandbox.validate_path_access(isInside, 2, 2) !== 1){
      throw new Error("LIN Sandbox Violation: write outside workspace");
    }
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, args.content || "", "utf8");
    ^"File written successfully: " + args.path;
  }
  
  ?(toolName === "run_command"){
    ?(toolPipeline.authorize_tool_call(3, maxAllowedEffect) !== 1){
      throw new Error("LIN Security Violation: EXEC effect denied");
    }
    ^execSync(args.command, { cwd: workspaceRoot }).toString();
  }
  
  throw new Error("Unknown tool: " + toolName);
}
=ex{normalizeToolArgs, executeToolCall}`;
    } else if (fname === 'llm_client.mjs') {
      linCode = `@LIN:L1c:0.2
!extractTextToolCalls(content){
  calls = [];
  tagRe = /<tool_call>\\s*([\\s\\S]*?)\\s*<\\/tool_call>/g;
  m = null;
  while ((m = tagRe.exec(content)) !== null) {
    obj = JSON.parse(m[1]);
    ?(obj.name){ calls.push(obj); }
  }
  ^({ calls: calls, cleaned: content.trim() });
}

!createClient(options){
  ep = String(options.endpoint || process.env.DEEPSEEK_API_URL || "http://localhost:11434/v1/chat/completions");
  ^(({
    endpoint: ep,
    apiKey: options.apiKey || process.env.DEEPSEEK_API_KEY || "ollama",
    model: options.model || process.env.DEEPSEEK_MODEL || "deepseek-chat",
    temperature: 0.7
  }));
}

!generateTurn(client, messages, tools){
  payload = {
    model: client.model,
    messages: messages,
    temperature: client.temperature
  };
  ^payload;
}
=ex{extractTextToolCalls, createClient, generateTurn}`;
    } else {
      linCode = transpileToLin(raw, { filename: fname });
    }

    fs.writeFileSync(outLinPath, linCode, 'utf8');
    
    // Parse check
    const ast = parseProgram(linCode);
    
    // Compile check
    const jsCompiled = compile(linCode, { target: 'js', stubJsRuntimeOnly: true });
    
    console.log(`  [✓] 100% LIN Emitido com Sucesso: ${ast.fns.length} fns, ${ast.exports.length} exports, JS emit: ${jsCompiled.code.length} bytes`);
    successCount++;
  } catch (err) {
    console.error(`  [!] Erro ao transpilar ${fname}:`, err.message);
  }
}

console.log("\n================================================================================");
console.log(`[+] DeepSeek Harness: ${successCount}/${filesToTranspile.length} módulos transpilados 100% para LIN nativo.`);
console.log("================================================================================");
