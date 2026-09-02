# [Seguranca] Material de chave derivado de constante pública e sem validação de startup (defaults que viram segredo real)

**Labels sugeridas:** `security`, `security/medium`, `c4`
**Categoria da auditoria:** C4 chaves/segredos
**Severidade:** MEDIA
**ID do achado:** F-06

## Problema e por que é explorável

O comentario no código e honesto ('NOT a root of trust'), mas o default esta vivo em rota de
linha de comando que gera chaves e pública roster; o ID da testemunha ainda carrega o
prefixo, facilitando reuso. Não ha flag que recuse produzir um roster 'de selftest' num
contexto de release, nem checagem de que o prefixo veio de fora.

## Evidência (arquivo:linha)

`compiler/lin.zig:12457 (seed_prefix default), 7383-7395 (deriveKeypair), 12591-12601 (id da testemunha contem o prefixo), 12613-12615 (apenas um WARNING impresso)`

```
// compiler/lin.zig:12457 + 7386-7395
var seed_prefix: []const u8 = "lin-transparency-selftest";
pub fn deriveKeypair(seed_prefix: []const u8, index: usize) !KeyPair {
    h.update("lin:transparency:witness-key:v1:"); h.update(seed_prefix); ...
    return Ed25519.KeyPair.create(seed);   // deterministico a partir do prefixo
}
```

## Condições de explorabilidade

Basta rodar `lin notary-sign` sem `--seed-prefix` (default) e usar o resultado como prova -
e o que F-02 demonstra.

## Impacto

Chaves de testemunha colestadas por qualquer pessoa => quorum sem valor (multiplica F-02).

## Sugestão de correção

Exigir `--seed-prefix`/`--key` explicito (sem default) e, em modo release, importar pubkeys
de notarios de arquivo assinado; marcar o roster gerado com `selftest=true` e fazer o
verificador recusar esse flag por default.

## Critérios de aceite

- [ ] `notary-sign` sem seed prefix => erro de uso (hoje assume default).
- [ ] Roster autoassinado carrega `selftest=true` e `notary-verify` o recusa a menos de `--allow-selftest`.
- [ ] README/docs de deploy não mostram mais o comando sem `--seed-prefix`.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
