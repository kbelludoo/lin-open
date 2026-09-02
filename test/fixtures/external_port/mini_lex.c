// Harness sobre o stb_c_lexer.h CLONADO do GitHub (github.com/nothings/stb).
// O cabecalho de terceiro NAO esta no repositorio: compile com -I$STB_DIR.
// Mesma configuracao do tests/c_lexer_test.c upstream; so o main e meu.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define STB_C_LEX_C_DECIMAL_INTS    Y
#define STB_C_LEX_C_HEX_INTS        Y
#define STB_C_LEX_C_OCTAL_INTS      Y
#define STB_C_LEX_C_DECIMAL_FLOATS  Y
#define STB_C_LEX_C99_HEX_FLOATS    Y
#define STB_C_LEX_C_IDENTIFIERS     Y
#define STB_C_LEX_C_DQ_STRINGS      Y
#define STB_C_LEX_C_SQ_STRINGS      Y
#define STB_C_LEX_C_CHARS           Y
#define STB_C_LEX_C_COMMENTS        Y
#define STB_C_LEX_CPP_COMMENTS      Y
#define STB_C_LEX_C_COMPARISONS     Y
#define STB_C_LEX_C_LOGICAL         Y
#define STB_C_LEX_C_SHIFTS          Y
#define STB_C_LEX_C_INCREMENTS      Y
#define STB_C_LEX_C_ARROW           Y
#define STB_C_LEX_EQUAL_ARROW       Y
#define STB_C_LEX_C_BITWISEEQ       Y
#define STB_C_LEX_C_ARITHEQ         Y
#define STB_C_LEX_PARSE_SUFFIXES    Y
#define STB_C_LEX_DECIMAL_SUFFIXES  "uUlL"
#define STB_C_LEX_HEX_SUFFIXES      "lL"
#define STB_C_LEX_OCTAL_SUFFIXES    "lL"
#define STB_C_LEX_FLOAT_SUFFIXES    "uulL"
#define STB_C_LEX_0_IS_EOF             N
#define STB_C_LEX_INTEGERS_AS_DOUBLES  N
#define STB_C_LEX_MULTILINE_DSTRINGS   Y
#define STB_C_LEX_MULTILINE_SSTRINGS   Y
#define STB_C_LEX_USE_STDLIB           N
#define STB_C_LEX_DOLLAR_IDENTIFIER    Y
#define STB_C_LEX_FLOAT_NO_DECIMAL     Y
#define STB_C_LEX_DEFINE_ALL_TOKEN_NAMES  Y
#define STB_C_LEX_DISCARD_PREPROCESSOR    Y
#define STB_C_LEXER_DEFINITIONS
#define STB_C_LEXER_IMPLEMENTATION
#include "stb_c_lexer.h"   // cabecalho TERCEIRO: -I$STB_DIR (nao vendorizado no repo)

static unsigned long long H = 0, TH;
static int NKIND = 1, NNUM = 2, NSTR = 4, NOPER = 9;
static int n_tok = 0, n_id = 0, n_num = 0, n_str = 0, n_opr = 0;

static void fold(int kind, char *first, char *last) {
   long len = (long)(last - first) + 1;
   long i;
   H = H * 31 + (unsigned long long)kind;
   TH = 0;
   for (i = 0; i < len; ++i) TH = (TH + (unsigned char)first[i]) * 31;
   H = H * 31 + (unsigned long long)len;
   H = H * 31 + TH;
   ++n_tok;
}

int main(int argc, char **argv) {
   FILE *f = fopen(argc > 1 ? argv[1] : "corpus.c", "rb");
   static char text[1 << 20], store[1 << 16];
   long len;
   stb_lexer lex;
   int t;
   if (!f) { fprintf(stderr, "abre nao: corpus\n"); return 2; }
   len = (long)fread(text, 1, sizeof text, f);
   fclose(f);
   stb_c_lexer_init(&lex, text, text + len, store, sizeof store);
   while (stb_c_lexer_get_token(&lex)) {
      if (lex.token == CLEX_parse_error) { printf("PARSE_ERROR\n"); return 1; }
      if (lex.token == CLEX_id)      { fold(NKIND, lex.where_firstchar, lex.where_lastchar); ++n_id; }
      else if (lex.token == CLEX_intlit) { fold(NNUM, lex.where_firstchar, lex.where_lastchar); ++n_num; }
      else if (lex.token == CLEX_dqstring || lex.token == CLEX_sqstring || lex.token == CLEX_charlit) {
         fold(NSTR, lex.where_firstchar, lex.where_lastchar); ++n_str;
      } else if (lex.token >= 0 && lex.token < 256) {
         fold(100 + lex.token, lex.where_firstchar, lex.where_lastchar); ++n_opr;
      } else {
         fold(NOPER, lex.where_firstchar, lex.where_lastchar); ++n_opr;
      }
   }
   printf("tokens=%d id=%d num=%d str=%d op=%d\n", n_tok, n_id, n_num, n_str, n_opr);
   printf("fold=%lld\n", (long long) H);
   (void)t;
   return 0;
}
