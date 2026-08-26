/**
 * Generator for .linmeta/ 4-layer Cognitive Memory Structure according to spec/LIN_META_SCHEMA.rulel
 */
import fs from 'node:fs';
import path from 'node:path';
import { parseLia } from '../src/compiler.mjs';
import { contentHash } from '../src/content_hash_load.mjs';

function extractValue(text, name) {
  const match = text.match(new RegExp(`!${name}\\(\\)\\{\\^'([^']*)'\\}`));
  return match ? match[1] : '';
}

function extractList(text, name) {
  const val = extractValue(text, name);
  return val ? val.split(',').map((x) => x.trim()).filter(Boolean) : [];
}

export function buildLinmeta(targetDir, opts = {}) {
  const metaDir = path.join(targetDir, '.linmeta');
  const identityDir = path.join(metaDir, 'identity');
  const rulesDir = path.join(metaDir, 'rules');
  const historyDir = path.join(metaDir, 'history');
  const graphDir = path.join(metaDir, 'graph');

  fs.mkdirSync(identityDir, { recursive: true });
  fs.mkdirSync(rulesDir, { recursive: true });
  fs.mkdirSync(historyDir, { recursive: true });
  fs.mkdirSync(graphDir, { recursive: true });

  const files = fs.readdirSync(targetDir).filter((f) => f.endsWith('.lin'));
  const registry = [];
  const invariants = [];
  const decisionLog = [];
  const moduleRefs = [];

  for (const f of files) {
    const filePath = path.join(targetDir, f);
    const content = fs.readFileSync(filePath, 'utf8');
    let prog;
    try {
      prog = parseLia(content);
    } catch {
      continue;
    }
    const moduleRef = extractValue(content, 'moduleRef') || f.replace(/\.lin$/, '');
    const deps = extractList(content, 'dependencies');
    const declaredEffects = extractList(content, 'declaredEffects');
    const caps = extractList(content, 'caps');
    const contract = extractValue(content, 'contract');
    const fileHash = contentHash(f, [], content);

    // Identity
    for (const fn of prog.fns) {
      registry.push({
        symbol_id: `${moduleRef}.${fn.name}`,
        module_ref: moduleRef,
        signature: `!${fn.name}(${Array.isArray(fn.params) ? fn.params.join(',') : String(fn.params || '')})`,
        effects: declaredEffects.join(','),
        capabilities: caps.join(','),
        semantic_hash: contentHash(fn.name, fn.params, fn.body),
      });
    }

    // Rules / Invariants
    invariants.push({
      rule_id: `INV-${moduleRef.toUpperCase()}`,
      condition: `module=${moduleRef}; effects=[${declaredEffects.join(',')}]; caps=[${caps.join(',')}]`,
      severity: 'CRITICAL',
      repair_action: `verify_contract: ${contract || 'default'}`,
    });

    // History / Decision Log
    decisionLog.push({
      decision_id: `DEC-${moduleRef.toUpperCase()}-001`,
      reason: `Initial architecture for ${moduleRef}`,
      affected_modules: moduleRef,
      approval_state: 'APPROVED',
    });

    // Graph / Module Refs
    for (const d of deps) {
      moduleRefs.push({
        source: moduleRef,
        dependency: d,
        dependency_hash: fileHash,
      });
    }
  }

  // Write Layer 1: Identity
  const regLines = registry.map(
    (r) => `~SYM{.id="${r.symbol_id}" .m="${r.module_ref}" .sig="${r.signature}" .eff="${r.effects}" .cap="${r.capabilities}" .hash="${r.semantic_hash}"}`
  );
  fs.writeFileSync(
    path.join(identityDir, 'semantic_registry.dicel'),
    `@DICEL:semantic_registry:1.0.0\n${regLines.join('\n')}\n`,
    'utf8'
  );

  // Write Layer 2: Rules
  const invLines = invariants.map(
    (i) => `.r{id="${i.rule_id}" cond="${i.condition}" sev="${i.severity}" repair="${i.repair_action}"}`
  );
  fs.writeFileSync(
    path.join(rulesDir, 'invariants.rulel'),
    `@RULEL:invariants:1.0.0\n${invLines.join('\n')}\n`,
    'utf8'
  );

  // Write Layer 3: History
  const decLines = decisionLog.map(
    (d) => `[DECISION] id=${d.decision_id} status=${d.approval_state} modules=${d.affected_modules} reason="${d.reason}"`
  );
  fs.writeFileSync(
    path.join(historyDir, 'decision_log.ledger'),
    `@LEDGER:decision_log:1.0.0\n${decLines.join('\n')}\n`,
    'utf8'
  );

  // Write Layer 4: Graph
  const graphLines = moduleRefs.map(
    (g) => `$DEP{src="${g.source}" dep="${g.dependency}" hash="${g.dependency_hash}"}`
  );
  fs.writeFileSync(
    path.join(graphDir, 'module_refs.dicel'),
    `@DICEL:module_refs:1.0.0\n${graphLines.join('\n')}\n`,
    'utf8'
  );

  if (!opts.silent) {
    console.log(`[build_linmeta] Generated .linmeta/ for ${targetDir} (${registry.length} symbols, ${invariants.length} invariants)`);
  }
  return { registry, invariants, decisionLog, moduleRefs };
}

if (process.argv[1] && process.argv[1].endsWith('build_linmeta.mjs')) {
  const dir = process.argv[2] || '.';
  buildLinmeta(path.resolve(dir));
}
