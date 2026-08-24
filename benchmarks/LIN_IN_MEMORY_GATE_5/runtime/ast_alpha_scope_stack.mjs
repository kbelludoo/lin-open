// LIN Scope-Stack AST Alpha-Canonicalizer
// Implements hierarchical lexical scope frames for block scopes, loops, closures, and catch clauses

import crypto from 'crypto';

class ScopeFrame {
  constructor(parent = null, kind = 'BLOCK') {
    this.parent = parent;
    this.kind = kind;
    this.bindings = new Map(); // originalName -> canonicalName
  }

  declare(name, canonicalName) {
    this.bindings.set(name, canonicalName);
  }

  resolve(name) {
    if (this.bindings.has(name)) {
      return this.bindings.get(name);
    }
    if (this.parent) {
      return this.parent.resolve(name);
    }
    return null;
  }
}

export class AstAlphaScopeStack {
  static tokenize(source) {
    const tokens = [];
    let i = 0;
    const len = source.length;

    while (i < len) {
      const ch = source[i];

      if (/\s/.test(ch)) {
        i++;
        continue;
      }

      if (ch === '/' && source[i + 1] === '/') {
        while (i < len && source[i] !== '\n') i++;
        continue;
      }
      if (ch === '/' && source[i + 1] === '*') {
        i += 2;
        while (i < len && !(source[i] === '*' && source[i + 1] === '/')) i++;
        i += 2;
        continue;
      }

      if (ch === '"' || ch === "'" || ch === '`') {
        const quote = ch;
        let str = quote;
        i++;
        while (i < len) {
          const c = source[i];
          str += c;
          if (c === '\\') {
            str += source[++i];
          } else if (c === quote) {
            i++;
            break;
          }
          i++;
        }
        tokens.push({ type: 'STRING_LITERAL', value: str });
        continue;
      }

      if (/[0-9]/.test(ch)) {
        let num = '';
        while (i < len && /[0-9.xXabcdefABCDEF]/.test(source[i])) {
          num += source[i++];
        }
        tokens.push({ type: 'NUMERIC_LITERAL', value: num });
        continue;
      }

      if (/[a-zA-Z_$]/.test(ch)) {
        let ident = '';
        while (i < len && /[a-zA-Z0-9_$]/.test(source[i])) {
          ident += source[i++];
        }
        tokens.push({ type: 'IDENTIFIER', value: ident });
        continue;
      }

      tokens.push({ type: 'PUNCTUATOR', value: ch });
      i++;
    }

    return tokens;
  }

  // Canonicalize with true Hierarchical Scope Stack
  static canonicalize(rawParams, rawBody) {
    const tokens = this.tokenize(rawBody);
    
    // Root function scope
    let currentScope = new ScopeFrame(null, 'FUNCTION');
    let localCounter = 0;

    // Register parameters as positional de Bruijn bindings $p0, $p1, ...
    rawParams.forEach((p, idx) => {
      currentScope.declare(p.trim(), `$p${idx}`);
    });

    const canonicalTokens = [];

    for (let k = 0; k < tokens.length; k++) {
      const tok = tokens[k];

      // 1. Enter block scope '{'
      if (tok.value === '{') {
        currentScope = new ScopeFrame(currentScope, 'BLOCK');
        canonicalTokens.push('{');
        continue;
      }

      // 2. Exit block scope '}'
      if (tok.value === '}') {
        if (currentScope.parent) {
          currentScope = currentScope.parent; // Pop scope!
        }
        canonicalTokens.push('}');
        continue;
      }

      // 3. String literals are preserved untouched
      if (tok.type === 'STRING_LITERAL') {
        canonicalTokens.push(tok.value);
        continue;
      }

      // 4. Local declarations: let x = ..., var x = ..., const x = ..., catch(x)
      if (tok.type === 'IDENTIFIER' && (tok.value === 'let' || tok.value === 'const' || tok.value === 'var')) {
        canonicalTokens.push(tok.value);
        if (k + 1 < tokens.length && tokens[k + 1].type === 'IDENTIFIER') {
          const varName = tokens[k + 1].value;
          const canonicalLocal = `$loc_${localCounter++}`;
          currentScope.declare(varName, canonicalLocal);
        }
        continue;
      }

      // 5. Catch clause scope: catch (e) { ... }
      if (tok.type === 'IDENTIFIER' && tok.value === 'catch') {
        canonicalTokens.push('catch');
        if (k + 2 < tokens.length && tokens[k + 1].value === '(' && tokens[k + 2].type === 'IDENTIFIER') {
          const errVar = tokens[k + 2].value;
          const canonicalLocal = `$err_${localCounter++}`;
          // The catch parameter will be bound when entering the block
          currentScope.declare(errVar, canonicalLocal);
        }
        continue;
      }

      // 6. Identifier Resolution via Scope Stack
      if (tok.type === 'IDENTIFIER') {
        const canonical = currentScope.resolve(tok.value);
        if (canonical) {
          canonicalTokens.push(canonical);
        } else {
          canonicalTokens.push(tok.value);
        }
        continue;
      }

      canonicalTokens.push(tok.value);
    }

    return canonicalTokens.join(' ');
  }

  static computeSemanticHash(fnNode) {
    const rawParams = fnNode.params || [];
    const canonicalBody = this.canonicalize(rawParams, fnNode.body || '');

    const structuralDigest = {
      kind: 'FUNCTION',
      arity: rawParams.length,
      effect: fnNode.effect || 'Pure',
      contracts: fnNode.contracts || [],
      canonicalBody
    };

    return crypto.createHash('sha256').update(JSON.stringify(structuralDigest)).digest('hex');
  }
}
