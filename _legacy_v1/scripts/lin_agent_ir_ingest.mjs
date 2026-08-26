/**
 * CLI host: JSON Agent IR → LIN validate → ACCEPT or causal REJECT/DENIED.
 * Source of truth: src/lin_agent_ir_ingest.lin
 */
import { ingestFile } from '../src/lin_agent_ir_ingest_load.mjs';

const file = process.argv[2];
if (!file) {
  console.error('usage: node scripts/lin_agent_ir_ingest.mjs <file.json>');
  process.exit(2);
}
const result = ingestFile(file);
console.log(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
