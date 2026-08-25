/**
 * LIN Semantic Merkle Hasher
 * Spec: spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 *
 * Implements bottom-up Merkle hashing over Canonical Semantic IR nodes.
 */

import { createHash } from 'node:crypto';
import { CanonicalIrSerializer } from './canonical_ir_serializer.mjs';
import { TrueAstParser } from './semantic_closure_engine.mjs';

export const CANONICALIZATION_VERSION = '1.0';

/**
 * Computes the Merkle hash of a Canonical IR node recursively.
 */
export function hashCanonicalNode(irNode) {
  if (!irNode) return hashString('Null');

  switch (irNode.kind) {
    case 'Literal':
      return hashString(`Lit:${irNode.type}:${JSON.stringify(irNode.value)}`);

    case 'LocalRef':
      return hashString(`Local:${irNode.ref}`);

    case 'CaptureRef':
      return hashString(`Cap:${irNode.ref}`);

    case 'GlobalRef':
      return hashString(`Global:${irNode.name}`);

    case 'Binary': {
      const leftH = hashCanonicalNode(irNode.left);
      const rightH = hashCanonicalNode(irNode.right);
      return hashString(`Bin:${irNode.operator}:${leftH}:${rightH}`);
    }

    case 'Unary': {
      const argH = hashCanonicalNode(irNode.argument);
      return hashString(`Un:${irNode.operator}:${irNode.prefix}:${argH}`);
    }

    case 'Update': {
      const argH = hashCanonicalNode(irNode.argument);
      return hashString(`Upd:${irNode.operator}:${irNode.prefix}:${argH}`);
    }

    case 'Assign': {
      const leftH = hashCanonicalNode(irNode.left);
      const rightH = hashCanonicalNode(irNode.right);
      return hashString(`Assign:${irNode.operator}:${leftH}:${rightH}`);
    }

    case 'Call': {
      const calleeH = hashCanonicalNode(irNode.callee);
      const argsH = (irNode.args || []).map(hashCanonicalNode).join(',');
      return hashString(`Call:${calleeH}:[${argsH}]`);
    }

    case 'Member': {
      const objH = hashCanonicalNode(irNode.object);
      const propH = typeof irNode.property === 'object'
        ? hashCanonicalNode(irNode.property)
        : `lit:${irNode.property}`;
      return hashString(`Member:${objH}:${propH}:${irNode.computed}:${irNode.optional}`);
    }

    case 'Array': {
      const elemH = (irNode.elements || []).map(hashCanonicalNode).join(',');
      return hashString(`Arr:[${elemH}]`);
    }

    case 'Object': {
      const propsH = (irNode.properties || [])
        .map(p => `${p.key}=${hashCanonicalNode(p.value)}`)
        .join(';');
      return hashString(`Obj:{${propsH}}`);
    }

    case 'If': {
      const testH = hashCanonicalNode(irNode.test);
      const consH = hashCanonicalNode(irNode.consequent);
      const altH = irNode.alternate ? hashCanonicalNode(irNode.alternate) : 'none';
      return hashString(`If:${testH}:${consH}:${altH}`);
    }

    case 'Conditional': {
      const testH = hashCanonicalNode(irNode.test);
      const consH = hashCanonicalNode(irNode.consequent);
      const altH = hashCanonicalNode(irNode.alternate);
      return hashString(`Cond:${testH}:${consH}:${altH}`);
    }

    case 'While': {
      const testH = hashCanonicalNode(irNode.test);
      const bodyH = hashCanonicalNode(irNode.body);
      return hashString(`While:${testH}:${bodyH}`);
    }

    case 'For': {
      const initH = irNode.init ? hashCanonicalNode(irNode.init) : 'none';
      const testH = irNode.test ? hashCanonicalNode(irNode.test) : 'none';
      const updH = irNode.update ? hashCanonicalNode(irNode.update) : 'none';
      const bodyH = hashCanonicalNode(irNode.body);
      return hashString(`For:${initH}:${testH}:${updH}:${bodyH}`);
    }

    case 'Return': {
      const argH = irNode.argument ? hashCanonicalNode(irNode.argument) : 'void';
      return hashString(`Ret:${argH}`);
    }

    case 'Block': {
      const stmtsH = (irNode.statements || []).map(hashCanonicalNode).join(';');
      return hashString(`Block:[${stmtsH}]`);
    }

    case 'VariableDeclaration': {
      const declsH = (irNode.declarations || []).map(d => {
        if (d.kind === 'Destructure') {
          const initH = d.init ? hashCanonicalNode(d.init) : 'none';
          return `Destruct:[${d.indexes.join(',')}]=${initH}`;
        }
        const initH = d.init ? hashCanonicalNode(d.init) : 'none';
        return `Var:${d.index}=${initH}`;
      }).join(';');
      return hashString(`VarDecl:[${declsH}]`);
    }

    case 'Function': {
      const bodyH = hashCanonicalNode(irNode.body);
      const capsH = (irNode.captures || []).map(c => `${c.name}->${c.ref}`).join(',');
      return hashString(`Fn:v${CANONICALIZATION_VERSION}:${irNode.effect}:p${irNode.paramCount}:[${capsH}]:${bodyH}`);
    }

    default:
      return hashString(`Unknown:${JSON.stringify(irNode)}`);
  }
}

/**
 * Computes the Merkle Root Hash for an entire application / module export set.
 */
export function hashAppMerkleRoot(exportHashMap) {
  const sortedEntries = Object.entries(exportHashMap).sort(([a], [b]) => a.localeCompare(b));
  const entriesStr = sortedEntries.map(([name, hash]) => `${name}:${hash}`).join('|');
  return hashString(`AppRoot:v${CANONICALIZATION_VERSION}:{${entriesStr}}`);
}

/**
 * High-level helper to hash JavaScript function source code directly.
 */
export function hashJsFunctionSource(fnSource) {
  const ast = TrueAstParser.parse(fnSource);
  const fnNode = ast.body.find(s => s.type === 'FunctionDeclaration' || s.type === 'VariableDeclaration' || s.type === 'ExpressionStatement');
  const target = fnNode && fnNode.type === 'VariableDeclaration'
    ? fnNode.declarations[0].init
    : (fnNode && fnNode.type === 'ExpressionStatement' ? fnNode.expression : fnNode);

  if (!target) {
    throw new Error(`No function definition found in source: ${fnSource.slice(0, 50)}`);
  }

  const ir = CanonicalIrSerializer.serializeFunction(target);
  return {
    hash: hashCanonicalNode(ir),
    ir,
    effect: ir.effect
  };
}

function hashString(content) {
  return createHash('sha256').update(content, 'utf8').digest('hex').slice(0, 16);
}
