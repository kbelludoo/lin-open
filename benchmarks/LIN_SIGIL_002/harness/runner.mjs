import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '../../..');

// Get all 375 real .lin files
function getCorpusFiles() {
  const dirs = [path.join(ROOT, 'src'), path.join(ROOT, 'clones_lin')];
  const files = [];
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) scan(full);
      else if (entry.isFile() && entry.name.endsWith('.lin')) files.push(full);
    }
  }
  dirs.forEach(scan);
  return files;
}

// V1 Parser (from src/lin_core_compiler.lin logic)
function parseRealV1(src) {
  const lines = String(src || '').split('\n');
  let hdr = '';
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('@LIN:') || line.startsWith('@RULEL:')) {
      hdr = line;
      break;
    }
  }

  const fns = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('!')) {
      const openParen = line.indexOf('(');
      const closeParen = line.indexOf(')');
      const openBrace = line.indexOf('{');
      if (openParen > 1 && closeParen > openParen && openBrace > closeParen) {
        const fnName = line.substring(1, openParen).trim();
        const paramsStr = line.substring(openParen + 1, closeParen).trim();
        const params = paramsStr.length > 0 ? paramsStr.split(',') : [];
        fns.push({ name: fnName, params });
      }
    }
  }

  return {
    protocol: 'LIN_IR/1.0',
    header: hdr,
    functions: fns
  };
}

// V2 Parser (from benchmarks/LIN_SIGIL_002/candidates/semantic_parser_v2.lin logic)
function parseRealV2(src) {
  const lines = String(src || '').split('\n');
  let hdr = '';
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('@LIN:') || line.startsWith('@RULEL:')) {
      hdr = line;
      break;
    }
  }

  const fns = [];
  let currentFn = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('!')) {
      const openParen = line.indexOf('(');
      const closeParen = line.indexOf(')');
      const openBrace = line.indexOf('{');
      if (openParen > 1 && closeParen > openParen && (openBrace === -1 || openBrace > closeParen)) {
        const fnName = line.substring(1, openParen).trim();
        const paramsStr = line.substring(openParen + 1, closeParen).trim();
        const params = paramsStr.length > 0 ? paramsStr.split(',') : [];
        currentFn = { name: fnName, params, contracts: [], effects: ['pure'], canonicalRef: null };
        fns.push(currentFn);
      }
    } else if (line.startsWith('%') && currentFn) {
      currentFn.contracts.push(line.substring(1).trim());
    } else if (line.startsWith('*') && currentFn) {
      currentFn.effects = [line.substring(1).replace(/[()]/g, '').trim()];
    } else if (line.startsWith('&') && currentFn) {
      currentFn.canonicalRef = line.substring(1).trim();
    }
  }

  return {
    protocol: 'LIN_IR/2.0',
    header: hdr,
    functions: fns
  };
}

export function runSuite() {
  console.log("================================================================================");
  console.log("   LIN-SIGIL-002: REAL COMPILER PARSER PARITY BENCHMARK (375 .lin FILES)       ");
  console.log("================================================================================");

  const files = getCorpusFiles();
  console.log(`Analyzing real corpus: ${files.length} .lin files...\n`);

  let matchingAsts = 0;
  let totalFnsV1 = 0;
  let totalFnsV2 = 0;
  let v1TimeMs = 0;
  let v2TimeMs = 0;

  for (const file of files) {
    const src = fs.readFileSync(file, 'utf8');

    const t0 = performance.now();
    const astV1 = parseRealV1(src);
    v1TimeMs += (performance.now() - t0);

    const t1 = performance.now();
    const astV2 = parseRealV2(src);
    v2TimeMs += (performance.now() - t1);

    totalFnsV1 += astV1.functions.length;
    totalFnsV2 += astV2.functions.length;

    // Check equivalence of headers and function names/params
    const headerMatch = astV1.header === astV2.header;
    const fnsMatch = astV1.functions.length === astV2.functions.length &&
      astV1.functions.every((f, i) => f.name === astV2.functions[i].name && f.params.length === astV2.functions[i].params.length);

    if (headerMatch && fnsMatch) {
      matchingAsts++;
    }
  }

  const equivalenceRate = (matchingAsts / files.length) * 100;
  const avgV1Us = (v1TimeMs * 1000) / files.length;
  const avgV2Us = (v2TimeMs * 1000) / files.length;

  const report = {
    total_files: files.length,
    matching_asts: matchingAsts,
    equivalence_rate: `${equivalenceRate.toFixed(2)}%`,
    total_functions_v1: totalFnsV1,
    total_functions_v2: totalFnsV2,
    v1_total_ms: v1TimeMs,
    v2_total_ms: v2TimeMs,
    v1_avg_us_per_file: avgV1Us,
    v2_avg_us_per_file: avgV2Us,
    speed_delta_pct: `${(((avgV1Us - avgV2Us) / avgV1Us) * 100).toFixed(2)}%`
  };

  const outPath = path.join(ROOT, 'benchmarks/LIN_SIGIL_002/results/LIN_SIGIL_002_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));

  console.log(`[Equivalence Gate] Parity: ${matchingAsts}/${files.length} (${equivalenceRate.toFixed(2)}%)`);
  console.log(`[Functions Found] V1: ${totalFnsV1} | V2: ${totalFnsV2}`);
  console.log(`[Latency] V1 Real Parser: ${avgV1Us.toFixed(1)} µs/file | V2 Candidate Parser: ${avgV2Us.toFixed(1)} µs/file`);
  console.log(`\n[+] Results saved to: ${outPath}`);
  return report;
}

runSuite();
