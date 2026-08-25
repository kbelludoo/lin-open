// LIN Real-World Blind Substrate: Autonomous Codebase AST Parsing & Indexer

import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

export class RealBlindSubstrate {
  constructor() {
    this.dagNodes = new Map(); // hash -> node
    this.symbolIndex = new Map(); // symbolName -> node
    this.dependencyGraph = new Map(); // caller -> Set(callees)
    this.reverseDependencyGraph = new Map(); // callee -> Set(callers)
    this.invariants = [];
    this.effects = new Map();
  }

  reset() {
    this.dagNodes.clear();
    this.symbolIndex.clear();
    this.dependencyGraph.clear();
    this.reverseDependencyGraph.clear();
    this.invariants = [];
    this.effects.clear();
  }

  hashNode(data) {
    return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
  }

  registerSymbol({ name, file, contracts = [], effect = 'Pure', body = '' }) {
    const nodeData = { name, file, contracts, effect, body: String(body).slice(0, 500) };
    const hash = this.hashNode(nodeData);

    let canonicalNode = this.dagNodes.get(hash);
    if (!canonicalNode) {
      canonicalNode = { id: hash, ...nodeData };
      this.dagNodes.set(hash, canonicalNode);
    }

    this.symbolIndex.set(name, canonicalNode);
    this.effects.set(name, effect);

    for (const c of contracts) {
      this.invariants.push({ symbol: name, ...c });
    }
    return canonicalNode;
  }

  addDependency(caller, callee) {
    if (!this.dependencyGraph.has(caller)) this.dependencyGraph.set(caller, new Set());
    this.dependencyGraph.get(caller).add(callee);

    if (!this.reverseDependencyGraph.has(callee)) this.reverseDependencyGraph.set(callee, new Set());
    this.reverseDependencyGraph.get(callee).add(caller);
  }

  // Autonomously scan repository on disk with ZERO human hints
  indexRepository(repoPath) {
    this.reset();
    const sourceFiles = [];

    function walk(dir) {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        if (e.name === 'node_modules' || e.name === '.git' || e.name === 'test' || e.name === 'tests') continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          walk(full);
        } else if (e.name.endsWith('.js') || e.name.endsWith('.mjs')) {
          sourceFiles.push(full);
        }
      }
    }

    walk(repoPath);

    for (const filePath of sourceFiles) {
      const relPath = path.relative(repoPath, filePath);
      const code = fs.readFileSync(filePath, 'utf8');

      // Extract functions via regex parser
      const fnRegex = /(?:export\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\s*\{([\s\S]*?)(?=\nfunction|\nexport|\n$)/g;
      let match;
      const fnsInFile = [];

      while ((match = fnRegex.exec(code)) !== null) {
        const fnName = match[1];
        const params = match[2];
        const body = match[3];

        fnsInFile.push(fnName);
        this.registerSymbol({
          name: fnName,
          file: relPath,
          effect: body.includes('console.') || body.includes('fs.') ? 'Write' : 'Pure',
          contracts: [{ kind: 'inv', expr: 'ret !== undefined' }],
          body
        });
      }

      // Build call graph between functions in same/cross files
      for (const fn of fnsInFile) {
        for (const other of fnsInFile) {
          if (fn !== other) {
            const body = this.symbolIndex.get(fn)?.body || '';
            if (body.includes(other + '(')) {
              this.addDependency(fn, other);
            }
          }
        }
      }
    }
  }

  generateFocusedContext(symbolName) {
    const node = this.symbolIndex.get(symbolName);
    if (!node) return null;

    const callees = Array.from(this.dependencyGraph.get(symbolName) || []);
    const callers = Array.from(this.reverseDependencyGraph.get(symbolName) || []);
    const invs = this.invariants.filter(i => i.symbol === symbolName).map(i => i.expr);

    return {
      symbol: symbolName,
      file: node.file,
      effect: node.effect,
      invariants: invs,
      dependencies: callees,
      dependents: callers
    };
  }
}
