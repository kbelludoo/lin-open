/*
 * lin_parse.c — Pratt parser implementation.
 *
 * Faithful port of `Parser` (lin.zig:14346-14522). The left-associative
 * `prec <= min_prec` break condition is the load-bearing line: it is what
 * makes `100 - 20 - 10` group as `(100-20)-10` and `1 < 2 < 3` group as
 * `(1<2)<3`.
 */
#include "lin_parse.h"
#include "lin_token.h"

void parser_init(Parser *p, LinStr src) {
    p->src = src;
    p->pos = 0;
    ast_arena_init(&p->arena);
}

/* Zig `peekToken`: save pos, tokenize, restore pos (net: pos unchanged). */
static Token peek(Parser *p) {
    size_t saved = p->pos;
    Token tok;
    lin_next_token(p->src.p, p->src.len, &p->pos, &tok);
    p->pos = saved;
    return tok;
}

static uint8_t get_precedence(TokKind kind) {
    switch (kind) {
    case TOK_EQ: case TOK_NEQ: case TOK_LT: case TOK_LTE:
    case TOK_GT: case TOK_GTE:        return 1;
    case TOK_PLUS: case TOK_MINUS:    return 2;
    case TOK_MUL: case TOK_DIV: case TOK_MOD: return 3;
    default:                          return 0;
    }
}

static LinErr parse_primary(Parser *p, uint16_t *out_node) {
    Token tok;
    lin_next_token(p->src.p, p->src.len, &p->pos, &tok);
    uint16_t idx;

    switch (tok.kind) {
    case TOK_INT_LIT:
        return ast_arena_add(&p->arena, TAG_LIT, 0, 0, tok.val, lin_str_empty(), out_node);

    case TOK_IDENT: {
        Token next_p = peek(p);
        if (next_p.kind == TOK_LPAREN) {
            /* function call: consume '(' */
            Token consumed;
            lin_next_token(p->src.p, p->src.len, &p->pos, &consumed);

            uint16_t arg_nodes[LIN_MAX_ARGS];
            size_t arg_count = 0;

            if (peek(p).kind != TOK_RPAREN) {
                while (1) {
                    if (arg_count >= LIN_MAX_ARGS) return LIN_ERR_ARENA_OOM;
                    LinErr ae = parse_expression(p, 0, &arg_nodes[arg_count]);
                    if (ae) return ae;
                    arg_count += 1;
                    Token sep = peek(p);
                    if (sep.kind == TOK_COMMA) {
                        lin_next_token(p->src.p, p->src.len, &p->pos, &consumed);
                        continue;
                    }
                    if (sep.kind == TOK_RPAREN) {
                        lin_next_token(p->src.p, p->src.len, &p->pos, &consumed);
                        break;
                    }
                    return LIN_ERR_MISSING_CLOSE_PAREN;
                }
            } else {
                lin_next_token(p->src.p, p->src.len, &p->pos, &consumed); /* consume ')' */
            }

            /* call_arg linked list: lhs=arg expr, rhs=previous call_arg.
             * call_root = the last call_arg created (0 if no args). */
            uint16_t call_root = 0;
            uint16_t prev_arg_node = 0;
            for (size_t aidx = 0; aidx < arg_count; aidx++) {
                LinErr ce = ast_arena_add(&p->arena, TAG_CALL_ARG,
                                          arg_nodes[aidx], prev_arg_node,
                                          0, lin_str_empty(), &idx);
                if (ce) return ce;
                prev_arg_node = idx;
                if (aidx == arg_count - 1) {
                    call_root = idx;
                }
            }
            return ast_arena_add(&p->arena, TAG_CALL, call_root, 0,
                                 (int64_t)arg_count, tok.name, out_node);
        }
        return ast_arena_add(&p->arena, TAG_VAR_REF, 0, 0, 0, tok.name, out_node);
    }

    case TOK_PLUS: {
        uint16_t operand;
        LinErr pe = parse_primary(p, &operand);
        if (pe) return pe;
        return ast_arena_add(&p->arena, TAG_UNARY_POS, operand, 0, 0,
                             lin_str_empty(), out_node);
    }

    case TOK_MINUS: {
        uint16_t operand;
        LinErr pe = parse_primary(p, &operand);
        if (pe) return pe;
        return ast_arena_add(&p->arena, TAG_UNARY_NEG, operand, 0, 0,
                             lin_str_empty(), out_node);
    }

    case TOK_LPAREN: {
        uint16_t expr_node;
        LinErr ee = parse_expression(p, 0, &expr_node);
        if (ee) return ee;
        Token close_tok;
        lin_next_token(p->src.p, p->src.len, &p->pos, &close_tok);
        if (close_tok.kind != TOK_RPAREN) return LIN_ERR_MISSING_CLOSE_PAREN;
        *out_node = expr_node;
        return LIN_OK;
    }

    default:
        return LIN_ERR_UNEXPECTED_PRIMARY;
    }
}

LinErr parse_expression(Parser *p, uint8_t min_prec, uint16_t *out_root) {
    uint16_t left_node;
    LinErr e = parse_primary(p, &left_node);
    if (e) return e;

    while (1) {
        Token next_tok = peek(p);
        uint8_t prec = get_precedence(next_tok.kind);
        if (prec == 0 || prec <= min_prec) break;

        Token consumed;
        lin_next_token(p->src.p, p->src.len, &p->pos, &consumed);
        uint16_t right_node;
        e = parse_expression(p, prec, &right_node);
        if (e) return e;

        AstTag op_tag;
        switch (next_tok.kind) {
        case TOK_PLUS:  op_tag = TAG_ADD;  break;
        case TOK_MINUS: op_tag = TAG_SUB;  break;
        case TOK_MUL:   op_tag = TAG_MUL;  break;
        case TOK_DIV:   op_tag = TAG_DIV;  break;
        case TOK_MOD:   op_tag = TAG_MOD;  break;
        case TOK_EQ:    op_tag = TAG_EQ;   break;
        case TOK_NEQ:   op_tag = TAG_NEQ;  break;
        case TOK_LT:    op_tag = TAG_LT;   break;
        case TOK_LTE:   op_tag = TAG_LTE;  break;
        case TOK_GT:    op_tag = TAG_GT;   break;
        case TOK_GTE:   op_tag = TAG_GTE;  break;
        default:        return LIN_ERR_INVALID_BINARY_OP;
        }

        e = ast_arena_add(&p->arena, op_tag, left_node, right_node,
                          0, lin_str_empty(), &left_node);
        if (e) return e;
    }

    *out_root = left_node;
    return LIN_OK;
}

LinErr parse_full(Parser *p, uint16_t *out_root) {
    LinErr e = parse_expression(p, 0, out_root);
    if (e) return e;
    Token end_tok;
    lin_next_token(p->src.p, p->src.len, &p->pos, &end_tok);
    if (end_tok.kind != TOK_EOF) return LIN_ERR_TRAILING_TOKENS;
    return LIN_OK;
}
