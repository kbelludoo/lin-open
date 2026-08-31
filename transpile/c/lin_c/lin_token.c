/*
 * lin_token.c — tokenizer implementation.
 */
#include "lin_token.h"

static int is_digit(uint8_t c) { return c >= '0' && c <= '9'; }
static int is_alpha(uint8_t c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static int is_ident_start(uint8_t c) { return is_alpha(c) || c == '_'; }
static int is_ident(uint8_t c) { return is_alpha(c) || is_digit(c) || c == '_'; }

void lin_next_token(const uint8_t *src, size_t srclen, size_t *pos, Token *out) {
    size_t p = *pos;

    /* skip whitespace */
    while (p < srclen &&
           (src[p] == ' ' || src[p] == '\t' || src[p] == '\r' || src[p] == '\n')) {
        p += 1;
    }

    if (p >= srclen) {
        out->kind = TOK_EOF;
        out->val = 0;
        out->name = lin_str_empty();
        out->pos = p;
        *pos = p;
        return;
    }

    size_t start = p;
    uint8_t c = src[p];

    /* integer literal */
    if (is_digit(c)) {
        uint64_t num = 0;
        while (p < srclen && is_digit(src[p])) {
            /* Zig: num = num*10 + d with defined i64 wrapping.
             * uint64_t here gives the identical bit pattern on wrap. */
            num = num * 10 + (uint64_t)(src[p] - '0');
            p += 1;
        }
        /* "1x" style: digit run immediately followed by ident char -> invalid */
        if (p < srclen && (is_alpha(src[p]) || src[p] == '_')) {
            out->kind = TOK_INVALID;
            out->val = 0;
            out->name = lin_str_empty();
            out->pos = start;
            *pos = p;
            return;
        }
        out->kind = TOK_INT_LIT;
        out->val = (int64_t)num;
        out->name = lin_str_empty();
        out->pos = start;
        *pos = p;
        return;
    }

    /* identifier */
    if (is_ident_start(c)) {
        size_t ident_start = p;
        while (p < srclen && is_ident(src[p])) {
            p += 1;
        }
        out->kind = TOK_IDENT;
        out->val = 0;
        out->name = (LinStr){src + ident_start, p - ident_start};
        out->pos = start;
        *pos = p;
        return;
    }

    /* two-char operators */
    if (c == '=' && p + 1 < srclen && src[p + 1] == '=') {
        p += 2;
        out->kind = TOK_EQ;
        out->val = 0;
        out->name = lin_str_empty();
        out->pos = start;
        *pos = p;
        return;
    }
    if (c == '!' && p + 1 < srclen && src[p + 1] == '=') {
        p += 2;
        out->kind = TOK_NEQ;
        out->val = 0;
        out->name = lin_str_empty();
        out->pos = start;
        *pos = p;
        return;
    }
    if (c == '<' && p + 1 < srclen && src[p + 1] == '=') {
        p += 2;
        out->kind = TOK_LTE;
        out->val = 0;
        out->name = lin_str_empty();
        out->pos = start;
        *pos = p;
        return;
    }
    if (c == '>' && p + 1 < srclen && src[p + 1] == '=') {
        p += 2;
        out->kind = TOK_GTE;
        out->val = 0;
        out->name = lin_str_empty();
        out->pos = start;
        *pos = p;
        return;
    }

    /* single-char operators */
    switch (c) {
    case '+': out->kind = TOK_PLUS; break;
    case '-': out->kind = TOK_MINUS; break;
    case '*': out->kind = TOK_MUL; break;
    case '/': out->kind = TOK_DIV; break;
    case '%': out->kind = TOK_MOD; break;
    case '<': out->kind = TOK_LT; break;
    case '>': out->kind = TOK_GT; break;
    case '(': out->kind = TOK_LPAREN; break;
    case ')': out->kind = TOK_RPAREN; break;
    case ',': out->kind = TOK_COMMA; break;
    default:  out->kind = TOK_INVALID; break;
    }
    p += 1;
    out->val = 0;
    out->name = lin_str_empty();
    out->pos = start;
    *pos = p;
}

Token lin_peek_token(const uint8_t *src, size_t srclen, size_t pos) {
    size_t saved = pos;
    Token tok;
    lin_next_token(src, srclen, &pos, &tok);
    pos = saved; /* restore — pos is a local copy, caller's value untouched */
    return tok;
}
