/*
 * lin_parse.h — port of the `Parser` struct (compiler/lin.zig:14346-14522):
 * the deterministic C-subset Pratt parser.
 *
 * Precedence (mirrors `getPrecedence`):
 *   3: * / %
 *   2: + -
 *   1: == != < <= > >=
 * Associativity: left (loop breaks when prec <= min_prec — so `a - b - c`
 * groups as `(a - b) - c`, and `1 < 2 < 3` as `(1 < 2) < 3`).
 */
#ifndef LIN_C_PARSE_H
#define LIN_C_PARSE_H

#include "lin_ast.h"

typedef struct {
    LinStr src;
    size_t pos;
    AstArena arena;
    uint16_t depth;
} Parser;

/* Zig `Parser.init(source)` */
void parser_init(Parser *p, LinStr src);

/* Zig `parseExpression(min_prec) ParseError!u16` */
LinErr parse_expression(Parser *p, uint8_t min_prec, uint16_t *out_root);

/* Zig `parseFull() ParseError!u16` — parse one expression, require EOF. */
LinErr parse_full(Parser *p, uint16_t *out_root);

#endif /* LIN_C_PARSE_H */
