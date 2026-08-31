/*
 * lin_token.h — port of `Parser.nextToken` / `Parser.peekToken`
 * (compiler/lin.zig:14309-14344) and the `Token`/`TokenType` declarations
 * (lin.zig:14137-14158).
 */
#ifndef LIN_C_TOKEN_H
#define LIN_C_TOKEN_H

#include "lin_common.h"

/* Enumeral order mirrors the Zig `TokenType` exactly (int_lit=0 ... invalid=17). */
typedef enum {
    TOK_INT_LIT = 0,
    TOK_IDENT,
    TOK_PLUS,
    TOK_MINUS,
    TOK_MUL,
    TOK_DIV,
    TOK_MOD,
    TOK_EQ,
    TOK_NEQ,
    TOK_LT,
    TOK_LTE,
    TOK_GT,
    TOK_GTE,
    TOK_LPAREN,
    TOK_RPAREN,
    TOK_COMMA,
    TOK_EOF,
    TOK_INVALID,
} TokKind;

/* Zig `Token { kind, val: i64, name: []const u8, pos: usize } */
typedef struct {
    TokKind kind;
    int64_t val;   /* int_lit only */
    LinStr name;   /* ident only — aliases the input buffer */
    size_t pos;
} Token;

/* nextToken: consumes from *pos (advanced on return). Mirrors Zig exactly:
 *  - skips ' ', '\t', '\r', '\n'
 *  - digit run: `num = num*10 + d` in i64 with Zig's defined wrapping ->
 *    here accumulated in uint64_t (C-guaranteed wrap) then bit-cast
 *  - digit run followed by a letter or '_' => TOK_INVALID (e.g. "1x")
 *  - two-char ops (==, !=, <=, >=) beat the single char
 *  - anything else non-operator => TOK_INVALID
 */
void lin_next_token(const uint8_t *src, size_t srclen, size_t *pos, Token *out);

/* peekToken: snapshot/restore (Zig saves pos, tokenizes, restores pos). */
Token lin_peek_token(const uint8_t *src, size_t srclen, size_t pos);

#endif /* LIN_C_TOKEN_H */
