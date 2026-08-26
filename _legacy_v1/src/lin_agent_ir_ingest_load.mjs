/**
 * Host loader: LIN source is src/lin_agent_ir_ingest.lin
 * Reads JSON Agent IR; LIN validates semantic structure.
 * Does not touch verifier / semantic_hash / behavior_eq nucleus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_agent_ir_ingest.lin');
let mod = null;

function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
  const tmp = path.join(os.tmpdir(), `lin_agent_ir_ingest_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

function parseFail() {
  return {
    ok: 0,
    status: 'REJECT',
    kind: 'agent_ir',
    field: 'json',
    missing: 'valid JSON',
    repairs: 'fix JSON syntax | pass an object',
    node: '',
    message: 'REJECTED AGENT_IR\nField: json\nMissing: valid JSON\nrepairs: fix JSON syntax | pass an object',
    sigil_required: 0,
    redefine: 0,
  };
}

export function validateAgentIr(ir) {
  return getMod().validateAgentIr(ir);
}

export function ingestJsonText(text) {
  try {
    return getMod().ingestJson(text);
  } catch {
    return parseFail();
  }
}

export function ingestFile(filePath) {
  const p = String(filePath || '');
  if (!p) return getMod().mkReject('json', 'path to JSON Agent IR', 'lin agent-ir <file.json> | pass a JSON file');
  let text;
  try {
    text = fs.readFileSync(p, 'utf8');
  } catch {
    return getMod().mkReject('json', 'readable JSON file', 'create the file | pass an existing path');
  }
  return ingestJsonText(text);
}

export function linPath() {
  return 'src/lin_agent_ir_ingest.lin';
}
