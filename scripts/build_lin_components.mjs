// LIN Dogfooding Pipeline Builder
// Compiles all src/*.lin components to src/*.compiled.cjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { compile } = await import(path.join(root, 'src', 'compiler.mjs'));

const COMPONENTS = [
  { lin: 'src/lexer_slices.lin', cjs: 'src/lexer_slices.compiled.cjs', exports: ['identLenAt', 'wsRunAt', 'numLenAt'] },
  { lin: 'src/semantic_hash_core.lin', cjs: 'src/semantic_hash_core.compiled.cjs', exports: ['escapeRe', 'canonicalize'] },
  { lin: 'src/effects_core.lin', cjs: 'src/effects_core.compiled.cjs', exports: ['firstUseIsRead', 'collectAssignedIds'] },
  { lin: 'src/rulel_core.lin', cjs: 'src/rulel_core.compiled.cjs', exports: ['splitTopEntries', 'parseValuePairs', 'parseRulel', 'validateComms'] },
  { lin: 'src/vm_core.lin', cjs: 'src/vm_core.compiled.cjs', exports: ['assertJsSyntaxCore', 'validateSandboxSpec'] },
  { lin: 'src/verifier_core.lin', cjs: 'src/verifier_core.compiled.cjs', exports: ['deepEq', 'findMissingExports'] }
];

console.log("================================================================================");
console.log("   COMPILING NATIVE LIN COMPONENTS -> PRODUCTION PIPELINE (.COMPILED.CJS)      ");
console.log("================================================================================");

for (const comp of COMPONENTS) {
  const linPath = path.join(root, comp.lin);
  const cjsPath = path.join(root, comp.cjs);
  const src = fs.readFileSync(linPath, 'utf8');
  const compiled = compile(src, { target: 'js' });
  const out = `${compiled.code}\nmodule.exports={${comp.exports.join(',')}};\n`;
  fs.writeFileSync(cjsPath, out, 'utf8');
  console.log(`  [✓] COMPILED ${comp.lin.padEnd(30)} -> ${comp.cjs} (${out.length} bytes)`);
}

console.log("================================================================================");
console.log(`[+] All ${COMPONENTS.length} LIN components successfully compiled into production.`);
console.log("================================================================================");
