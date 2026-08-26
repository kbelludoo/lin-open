// LIN Semantic HashCons Engine v5.3 with True Recursive AST Alpha-Canonicalization
import { TrueAstAlphaCanonicalizer } from './true_ast_alpha_canonicalizer.mjs';
import { AstCapabilityFuzzer } from './ast_capability_fuzzer.mjs';

export class CompileCapabilityError extends Error {
  constructor(fnName, effect, violations) {
    super(`[CAPABILITY_VIOLATION] Function '${fnName}' *(Pure) violated effect boundaries: ${violations.map(v => v.detail).join('; ')}`);
    this.name = 'CompileCapabilityError';
    this.fnName = fnName;
    this.effect = effect;
    this.violations = violations;
  }
}

export class SemanticHashConsV5 {
  constructor() {
    this.internTable = new Map(); // trueAstCanonicalHash -> CanonicalNode
    this.symbolIndex = new Map(); // "module:name" -> trueAstCanonicalHash
    this.telemetry = {
      totalInternRequests: 0,
      rejectedByCapabilityFuzzer: 0,
      uniqueCanonicalNodes: 0,
      structuralAlphaHits: 0
    };
  }

  reset() {
    this.internTable.clear();
    this.symbolIndex.clear();
    this.telemetry = {
      totalInternRequests: 0,
      rejectedByCapabilityFuzzer: 0,
      uniqueCanonicalNodes: 0,
      structuralAlphaHits: 0
    };
  }

  internNode(moduleName, fnNode) {
    this.telemetry.totalInternRequests++;

    // 1. Mandatory Pre-Execution Capability Enforcement Gate
    const audit = AstCapabilityFuzzer.auditFunction(fnNode);
    if (!audit.valid) {
      this.telemetry.rejectedByCapabilityFuzzer++;
      throw new CompileCapabilityError(fnNode.name, fnNode.effect || 'Pure', audit.violations);
    }

    // 2. True Recursive AST Alpha-Canonical Content Hashing
    const fnSource = `function ${fnNode.name}(${(fnNode.params || []).join(', ')}) { ${fnNode.body} }`;
    const alphaHash = TrueAstAlphaCanonicalizer.computeCanonicalHash(fnSource);
    let canonicalNode = this.internTable.get(alphaHash);

    if (!canonicalNode) {
      canonicalNode = {
        alphaHash,
        primaryName: fnNode.name,
        params: fnNode.params || [],
        effect: fnNode.effect || 'Pure',
        contracts: fnNode.contracts || [],
        body: fnNode.body,
        compiledFn: null
      };
      this.internTable.set(alphaHash, canonicalNode);
      this.telemetry.uniqueCanonicalNodes++;
    } else {
      this.telemetry.structuralAlphaHits++;
    }

    const symbolKey = `${moduleName}:${fnNode.name}`;
    this.symbolIndex.set(symbolKey, alphaHash);
    return canonicalNode;
  }

  // Symbol Resolution: 2 Map Lookups (symbolIndex -> internTable)
  resolveSymbol(moduleName, symbolName) {
    const symbolKey = `${moduleName}:${symbolName}`;
    const hash = this.symbolIndex.get(symbolKey);
    if (!hash) return null;
    return this.internTable.get(hash) || null;
  }

  // Canonical Resident Invocation
  executeCanonicalNode(canonicalNode, ...args) {
    if (!canonicalNode) throw new Error("Null canonical node execution");
    if (!canonicalNode.compiledFn) {
      canonicalNode.compiledFn = new Function(...canonicalNode.params, canonicalNode.body);
    }
    return canonicalNode.compiledFn(...args);
  }

  // Integrated Resolve + Execution
  resolveAndExecute(moduleName, symbolName, ...args) {
    const node = this.resolveSymbol(moduleName, symbolName);
    if (!node) throw new Error(`Symbol '${moduleName}:${symbolName}' not found`);
    return this.executeCanonicalNode(node, ...args);
  }
}
