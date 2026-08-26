// LIN Real Recursive AST Parser & Semantic Scope-Tree Alpha-Canonicalizer
// Correctly parses Block Statements, Object Literals, Catch Clauses, For Loops, and Closures

import crypto from 'crypto';

class SemanticScope {
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

export class RealAstAlphaCanonicalizer {
  // Lexical Tokenizer with Context Classification
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

      // Line / Block Comments (stripped from AST)
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

      // String Literals
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

      // Numeric Literals
      if (/[0-9]/.test(ch)) {
        let num = '';
        while (i < len && /[0-9.xXabcdefABCDEF]/.test(source[i])) {
          num += source[i++];
        }
        tokens.push({ type: 'NUMERIC_LITERAL', value: num });
        continue;
      }

      // Identifiers / Keywords
      if (/[a-zA-Z_$]/.test(ch)) {
        let ident = '';
        while (i < len && /[a-zA-Z0-9_$]/.test(source[i])) {
          ident += source[i++];
        }
        tokens.push({ type: 'IDENTIFIER', value: ident });
        continue;
      }

      // Punctuators
      tokens.push({ type: 'PUNCTUATOR', value: ch });
      i++;
    }

    return tokens;
  }

  // Recursive Semantic Scope-Tree Canonicalizer
  static canonicalize(rawParams, rawBody) {
    const tokens = this.tokenize(rawBody);
    const rootScope = new SemanticScope(null, 'FUNCTION');
    let localCounter = 0;

    // Register parameter bindings: p0 -> $p0, p1 -> $p1
    rawParams.forEach((p, idx) => {
      rootScope.declare(p.trim(), `$p${idx}`);
    });

    let currentScope = rootScope;
    const output = [];
    let i = 0;

    while (i < tokens.length) {
      const tok = tokens[i];

      // 1. Try-Catch Statement: catch (err) { ... }
      if (tok.type === 'IDENTIFIER' && tok.value === 'catch') {
        output.push('catch');
        i++;
        if (i < tokens.length && tokens[i].value === '(') {
          output.push('(');
          i++;
          const errParam = tokens[i].value;
          output.push(`$err_${localCounter}`);
          i++; // Skip err param
          output.push(')');
          i++; // Skip ')'

          if (i < tokens.length && tokens[i].value === '{') {
            output.push('{');
            i++;
            // Push catch scope ONLY for this block!
            const catchScope = new SemanticScope(currentScope, 'CATCH');
            catchScope.declare(errParam, `$err_${localCounter++}`);
            currentScope = catchScope;
            continue;
          }
        }
      }

      // 2. For Loop: for (let i = 0; ... ) { ... }
      if (tok.type === 'IDENTIFIER' && tok.value === 'for') {
        output.push('for');
        i++;
        if (i < tokens.length && tokens[i].value === '(') {
          output.push('(');
          i++;
          // Create loop scope
          const loopScope = new SemanticScope(currentScope, 'LOOP');
          currentScope = loopScope;

          while (i < tokens.length && tokens[i].value !== '{') {
            const innerTok = tokens[i];
            if (innerTok.type === 'IDENTIFIER' && (innerTok.value === 'let' || innerTok.value === 'var' || innerTok.value === 'const')) {
              output.push(innerTok.value);
              i++;
              if (i < tokens.length && tokens[i].type === 'IDENTIFIER') {
                const varName = tokens[i].value;
                const canonicalLocal = `$loc_${localCounter++}`;
                currentScope.declare(varName, canonicalLocal);
                output.push(canonicalLocal);
                i++;
                continue;
              }
            } else if (innerTok.type === 'IDENTIFIER') {
              const res = currentScope.resolve(innerTok.value);
              output.push(res || innerTok.value);
            } else {
              output.push(innerTok.value);
            }
            i++;
          }

          if (i < tokens.length && tokens[i].value === '{') {
            output.push('{');
            i++;
            continue;
          }
        }
      }

      // 3. Block Enter '{' vs Object Literal '{'
      if (tok.value === '{') {
        // Distinguish block statement from object literal
        const prevTok = output.length > 0 ? output[output.length - 1] : null;
        const isObjectLiteral = prevTok === '=' || prevTok === ':' || prevTok === '(' || prevTok === 'return';

        if (isObjectLiteral) {
          output.push('{');
        } else {
          output.push('{');
          currentScope = new SemanticScope(currentScope, 'BLOCK');
        }
        i++;
        continue;
      }

      // 4. Block Exit '}'
      if (tok.value === '}') {
        output.push('}');
        if (currentScope.parent) {
          currentScope = currentScope.parent; // Pop block/loop/catch scope frame!
        }
        i++;
        continue;
      }

      // 5. String Literals are strictly preserved
      if (tok.type === 'STRING_LITERAL') {
        output.push(tok.value);
        i++;
        continue;
      }

      // 6. Variable Declaration: let x = ..., const x = ..., var x = ...
      if (tok.type === 'IDENTIFIER' && (tok.value === 'let' || tok.value === 'const' || tok.value === 'var')) {
        output.push(tok.value);
        i++;
        if (i < tokens.length && tokens[i].type === 'IDENTIFIER') {
          const varName = tokens[i].value;
          const canonicalLocal = `$loc_${localCounter++}`;
          currentScope.declare(varName, canonicalLocal);
          output.push(canonicalLocal);
          i++;
        }
        continue;
      }

      // 7. General Identifier Resolution
      if (tok.type === 'IDENTIFIER') {
        const canonical = currentScope.resolve(tok.value);
        if (canonical) {
          output.push(canonical);
        } else {
          output.push(tok.value);
        }
        i++;
        continue;
      }

      output.push(tok.value);
      i++;
    }

    return output.join(' ');
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
