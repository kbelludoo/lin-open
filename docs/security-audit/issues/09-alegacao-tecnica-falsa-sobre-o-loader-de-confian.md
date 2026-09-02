# [Seguranca] Alegação tecnica falsa sobre o loader de confiança, duplicação da mesma lógica e comentario depreciativo no documento de fronteira

**Labels sugeridas:** `security`, `security/info`, `c3`
**Categoria da auditoria:** C3 referencia nao validada
**Severidade:** INFORMATIVA
**ID do achado:** F-10

## Problema e por que é explorável

O `strlen` do loader e aplicado no nome solicitado (argv), nunca na pool; a comparação já
usa `name_len[i]`. Medido: `lin_bc1_run` e `lin_c0 run` resolvem nomes em qualquer posição
(`lex_gate`, `lex_scan_embedded`, `lex_count_embedded` = 1 / 1371904279658369433 / 20) e
recusam nome inexistente. O par de nomes com prefixo comum (`gate`, `gate_x`) resolve
corretamente pelas duas rotas. Logo: não ha vulnerabilidade, mas a alegação publicada (doc
§7, HISTORY e comentario) afirma que o TCB tem um furo e duplica a função do loader 'por
segurança'.

## Evidência (arquivo:linha)

`transpile/c/tool/lin_c0.c:156-165, docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel (secao 7), compiler0_manifest.rulel, HISTORY.rulel (entrada C0-no-Zig cont.)`

```
/* transpile/c/tool/lin_c0.c:156-165
 * Busca exata pelo nome usando name_len[] do loader: o pool LINBC1 nao e
 * NUL-terminado, entao `strlen` (como faz lin_bc1_find_fn) so e seguro no
 * ultimo nome da secao. Aqui e comparacao por comprimento - correta sempre. */
static int bc1_find_fn_strict(const LinBc1Vm *m, const char *name) { ... }
// transpile/c/lin_c/lin_linbc1.c:195-202 (o loader JA compara por comprimento)
int lin_bc1_find_fn(const LinBc1Vm *m, const char *name) {
    size_t want = strlen(name);
    for (size_t i = 0; i < m->mod.fns_len; i++)
        if ((size_t)m->name_len[i] == want && memcmp(m->mod.fns[i].name, name, want) == 0)
            return (int)i;
    return -1; }
```

## Condições de explorabilidade

Não explorável. O custo e de confiança/revisao: quem audita confia menos no loader do que
deveria e mantem dois codigos identicos.


## Achados agrupados neste ticket

- **F-11 (informativa)** - Verificação de paridade/reportes com `steps=0` e status PASS; limites divergentes entre hosts
  - Evidencia: `compiler/lin.zig (integrity/certificate), transpile/c/tool/lin_c0_front.c (C0_LIMIT_*), SECURITY_AUDIT.md (prior art)`
  - Aceite: O veredito de `integrity` declara explicitamente que nenhuma execução ocorreu.; `docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel` traz a tabela de limites divergentes.; Nenhum gate compara cobertura sem mencionar os caps de cada host.

## Impacto

Documentação de fronteira incorreta + lógica redundante a `tool/` (manutencao).

## Sugestão de correção

Corrigir comentario e docs (remover a alegação), e ou chamar `lin_bc1_find_fn` diretamente
ou justificar a copia com o motivo real (independencia de host), não com um defeito
inexistente.

## Critérios de aceite

- [ ] grep 'so e seguro no último nome' não retorna nada no repo.
- [ ] Seção 7 do doc descreve `bc1_find_fn_strict` como comparação por comprimento equivalente a do loader.
- [ ] Um teste cobre resolução de nomes em primeira/meia/ultima posição (rota fonte e rota imagem).

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
