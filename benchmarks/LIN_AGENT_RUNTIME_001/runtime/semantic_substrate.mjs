// LIN Semantic Substrate: Canonical Memory + Transitive Dependency Graph + HashCons

import crypto from 'crypto';

export class SemanticSubstrate {
  constructor() {
    this.dagNodes = new Map(); // hash -> node
    this.symbolIndex = new Map(); // symbolName -> node
    this.dependencyGraph = new Map(); // caller -> Set(callees)
    this.reverseDependencyGraph = new Map(); // callee -> Set(callers)
    this.invariants = [];
    this.effects = new Map(); // symbol -> effect
  }

  hashNode(data) {
    return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
  }

  // 1. Full Semantic HashCons (incorporates normalized body in identity)
  registerSymbol({ name, module, params = [], returnType = 'any', contracts = [], effect = 'Pure', body = '' }) {
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

  // 2. Full Transitive Traversal (BFS with cycle detection)
  getAffectedSubtree(symbolName) {
    const affected = new Set();
    const queue = [symbolName];
    const visited = new Set([symbolName]);

    while (queue.length > 0) {
      const current = queue.shift();
      const callers = this.reverseDependencyGraph.get(current);
      if (callers) {
        for (const caller of callers) {
          if (!visited.has(caller)) {
            visited.add(caller);
            affected.add(caller);
            queue.push(caller);
          }
        }
      }
    }

    return Array.from(affected);
  }

  generateFocusedContext(targetSymbol) {
    const node = this.symbolIndex.get(targetSymbol);
    const dependents = this.getAffectedSubtree(targetSymbol);
    const activeInvariants = this.invariants.filter(inv => dependents.includes(inv.symbol) || inv.symbol === targetSymbol);

    return {
      symbol: node ? node.name : targetSymbol,
      module: node ? node.module : 'unknown',
      effect: node ? node.effect : 'Pure',
      contracts: node ? node.contracts : [],
      dependents,
      activeInvariants
    };
  }
}
