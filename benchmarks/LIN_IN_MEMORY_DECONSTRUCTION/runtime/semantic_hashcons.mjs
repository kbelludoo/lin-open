// LIN Alpha-Canonical Structural HashCons Engine with Integrated Capability Enforcement
import crypto from 'crypto';
import { AstCapabilityChecker } from './ast_capability_checker.mjs';

export class SemanticHashCons {
  constructor() {
    this.internTable = new Map(); // alphaCanonicalHash -> CanonicalNode
    this.symbolIndex = new Map(); // "module:name" -> alphaCanonicalHash
    this.telemetry = {
      totalInternRequests: 0,
      rejectedByCapabilityChecker: 0,
      uniqueCanonicalNodes: 0,
      structuralAlphaHits: 0
    };
  }

  reset() {
    this.internTable.clear();
    this.symbolIndex.clear();
    this.telemetry = {
      totalInternRequests: 0,
      rejectedByCapabilityChecker: 0,
      uniqueCanonicalNodes: 0,
      structuralAlphaHits: 0
    };
  }

  // Alpha-canonical normalization: normalizes parameter names & whitespace
  // Example: !foo(x, y){ return x + y; } and !bar(a, b){ return a + b; }
  // Both map to canonical: params=['$p0','$p1'], body="return $p0 + $p1;"
  computeAlphaCanonicalHash(astNode) {
    const rawParams = astNode.params || [];
    let alphaBody = String(astNode.body || '').replace(/\s+/g, ' ').trim();

    // Perform systematic alpha-renaming on parameter bindings
    for (let i = 0; i < rawParams.length; i++) {
      const p = rawParams[i].trim();
      if (p) {
        const paramRegex = new RegExp(`\\b${p}\\b`, 'g');
        alphaBody = alphaBody.replace(paramRegex, `$p${i}`);
      }
    }

    const canonicalTree = {
      kind: astNode.kind || 'FUNCTION',
      arity: rawParams.length,
      effect: astNode.effect || 'Pure',
      contracts: astNode.contracts || [],
      alphaBody
    };

    return crypto.createHash('sha256').update(JSON.stringify(canonicalTree)).digest('hex');
  }

  // Intern Node with Mandatory Pre-Execution Capability Enforcement
  internNode(moduleName, astNode) {
    this.telemetry.totalInternRequests++;

    // GATE 1: Statically enforce purity BEFORE creating any node or allocating memory
    try {
      AstCapabilityChecker.enforcePurityOrThrow(astNode);
    } catch (err) {
      this.telemetry.rejectedByCapabilityChecker++;
      throw err; // Rejection prevents any executable function construction!
    }

    // GATE 2: Compute Alpha-Canonical Structural Hash
    const alphaHash = this.computeAlphaCanonicalHash(astNode);
    let canonicalNode = this.internTable.get(alphaHash);

    if (!canonicalNode) {
      // First observation of this alpha-equivalent semantic structure
      canonicalNode = {
        alphaHash,
        primaryName: astNode.name,
        params: (astNode.params || []).map((_, i) => `$p${i}`),
        originalParams: astNode.params || [],
        effect: astNode.effect || 'Pure',
        contracts: astNode.contracts || [],
        body: astNode.body,
        compiledFn: null // Lazy compiled on first invocation
      };
      this.internTable.set(alphaHash, canonicalNode);
      this.telemetry.uniqueCanonicalNodes++;
    } else {
      // Structural Alpha-Equivalence Hit!
      this.telemetry.structuralAlphaHits++;
    }

    const symbolKey = `${moduleName}:${astNode.name}`;
    this.symbolIndex.set(symbolKey, alphaHash);
    return canonicalNode;
  }

  // D1: Pure Symbol Resolution / Pointer Lookup in Memory
  resolveSymbol(moduleName, symbolName) {
    const symbolKey = `${moduleName}:${symbolName}`;
    const hash = this.symbolIndex.get(symbolKey);
    if (!hash) return null;
    return this.internTable.get(hash) || null;
  }

  // D2: Pure Canonical Node Invocation (precompiled resident function)
  executeCanonicalNode(canonicalNode, ...args) {
    if (!canonicalNode) throw new Error("Null canonical node execution");
    if (!canonicalNode.compiledFn) {
      canonicalNode.compiledFn = new Function(...canonicalNode.originalParams, canonicalNode.body);
    }
    return canonicalNode.compiledFn(...args);
  }

  // D3: Integrated Resolve + Invocation
  resolveAndExecute(moduleName, symbolName, ...args) {
    const node = this.resolveSymbol(moduleName, symbolName);
    if (!node) throw new Error(`Symbol '${moduleName}:${symbolName}' not found in HashCons`);
    return this.executeCanonicalNode(node, ...args);
  }
}
