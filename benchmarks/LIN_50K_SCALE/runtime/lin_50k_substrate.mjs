// LIN 50K Semantic Substrate: HashCons + Invariant Table + Transitive DAG

import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

export class LIN50kSubstrate {
  constructor() {
    this.dagNodes = new Map(); // hash -> node
    this.symbolIndex = new Map(); // symbolName -> node
    this.moduleIndex = new Map(); // modName -> list of symbols
    this.dependencyGraph = new Map(); // caller -> Set(callees)
    this.reverseDependencyGraph = new Map(); // callee -> Set(callers)
    this.invariants = [];
    this.effects = new Map();
  }

  hashNode(data) {
    return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
  }

  registerSymbol({ name, module, params = [], returnType = 'number', contracts = [], effect = 'Pure', body = '' }) {
    const normalizedBody = String(body).replace(/\s+/g, ' ').trim();
    const nodeData = { name, module, params, returnType, contracts, effect, body: normalizedBody };
    const hash = this.hashNode(nodeData);

    let canonicalNode = this.dagNodes.get(hash);
    if (!canonicalNode) {
      canonicalNode = { id: hash, ...nodeData };
      this.dagNodes.set(hash, canonicalNode);
    }

    this.symbolIndex.set(name, canonicalNode);
    this.effects.set(name, effect);

    if (!this.moduleIndex.has(module)) {
      this.moduleIndex.set(module, []);
    }
    this.moduleIndex.get(module).push(name);

    for (const c of contracts) {
      if (c.kind === 'inv') {
        this.invariants.push({ symbol: name, ...c });
      }
    }

    return canonicalNode;
  }

  addDependency(callerSymbol, calleeSymbol) {
    if (!this.dependencyGraph.has(callerSymbol)) {
      this.dependencyGraph.set(callerSymbol, new Set());
    }
    this.dependencyGraph.get(callerSymbol).add(calleeSymbol);

    if (!this.reverseDependencyGraph.has(calleeSymbol)) {
      this.reverseDependencyGraph.set(calleeSymbol, new Set());
    }
    this.reverseDependencyGraph.get(calleeSymbol).add(callerSymbol);
  }

  getAffectedSubtree(symbolName) {
    const affected = new Set();
    const queue = [symbolName];
    const visited = new Set([symbolName]);

    while (queue.length > 0) {
      const current = queue.shift();
      const callers = this.reverseDependencyGraph.get(current) || new Set();
      for (const caller of callers) {
        if (!visited.has(caller)) {
          visited.add(caller);
          affected.add(caller);
          queue.push(caller);
        }
      }
    }
    return affected;
  }

  // Focus slice for LLM (< 500 tokens) even inside 50k LOC codebase!
  generateFocusedContext(symbolName) {
    const node = this.symbolIndex.get(symbolName);
    if (!node) return null;

    const callees = Array.from(this.dependencyGraph.get(symbolName) || []);
    const callers = Array.from(this.reverseDependencyGraph.get(symbolName) || []);
    const invs = this.invariants.filter(i => i.symbol === symbolName).map(i => i.expr);

    return {
      symbol: symbolName,
      module: node.module,
      effect: node.effect,
      returnType: node.returnType,
      invariants: invs,
      dependencies: callees,
      dependents: callers
    };
  }

  // Load and index the entire 50k codebase from manifest
  index50kManifest(manifestPath) {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    console.log(`[+] Indexing 50k LOC codebase (${manifest.num_modules} modules, ${manifest.total_functions} functions) into LIN HashCons Substrate...`);
    const t0 = performance.now();

    for (let m = 0; m < manifest.modules.length; m++) {
      const mod = manifest.modules[m];
      for (const fn of mod.functions) {
        this.registerSymbol({
          name: fn.name,
          module: mod.jsPath,
          effect: fn.effect,
          contracts: fn.invariants.map(inv => ({ kind: 'inv', expr: inv }))
        });
      }

      if (m > 0) {
        const prevMod = manifest.modules[m - 1];
        this.addDependency(mod.functions[0].name, prevMod.functions[0].name);
      }
    }

    const durationMs = performance.now() - t0;
    console.log(`[+] Substrate Indexed in ${durationMs.toFixed(2)}ms! Total DAG Nodes: ${this.dagNodes.size}, Total Invariants: ${this.invariants.length}`);
  }
}
