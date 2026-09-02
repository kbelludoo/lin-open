# [Seguranca] Documentação afirma gates/publicacao em CI que o workflow não contem (falsa garantia)

**Labels sugeridas:** `security`, `security/low`, `c5`
**Categoria da auditoria:** C5 tratamento de input
**Severidade:** BAIXA
**ID do achado:** F-08

## Problema e por que é explorável

O texto diz que a CI pública assets verificaveis; o workflow em arvore não tem o job (o
patch esta em `docs/CI_*_PATCH.rulel`, aguardando aplicação por falta de escopo
`workflows`). Quem seguir o doc para 'baixar e verificar' não encontra o asset nem a
verificação. O arquivo `nucleus.lock.json`, citado como trava de integridade do verificador,
não existe.

## Evidência (arquivo:linha)

`.github/workflows/ci.yml (92 linhas; nenhum job 'release' nem 'gate' nem 'compiler0-no-zig'), docs/LIN_SEM_ZIG_CAMINHOS.rulel:24-31, docs/CI_RELEASE_E_V1_GATES_PATCH.rulel, docs/CI_COMPILER0_NO_ZIG_JOB_PATCH.rulel, HISTORY.rulel:78 (nucleus.lock.json inexistente)`

```
docs/LIN_SEM_ZIG_CAMINHOS.rulel: "Este PR fecha essa divergencia: a CI agora sobe os
artifacts lin_native-cpu/lin_native-gpu em toda execucao e publica os dois como assets de
Release ao empurrar tag `v*` (job `release`, --verify-tag)."
$ grep -c "release" .github/workflows/ci.yml   ->  0
$ ls nucleus.lock.json                          ->  No such file or directory
```

## Condições de explorabilidade

Sem condição tecnica; e leitura de documentação. Materializa-se quando alguem confia na
promessa em vez do manifesto.


## Achados agrupados neste ticket

- **F-09 (baixa)** - CI sem bloco `permissions:` e com ação de terceiro referida por tag mutavel
  - Evidencia: `.github/workflows/ci.yml:1-23 (sem `permissions:`), :27 (`goto-bus-stop/setup-zig@v2`), :88 (`upload-artifact@v4`)`
  - Aceite: `gh api repos/kbelludoo/lin-open/actions/permissions` (ou inspeção do YAML) mostra escopo minimo por job.; Toda `uses:` de terceiro apontando para SHA de 40 hex.; O job de release (quando existir) declara escrita apenas nele.
- **F-11 (informativa)** - Verificação de paridade/reportes com `steps=0` e status PASS; limites divergentes entre hosts
  - Evidencia: `compiler/lin.zig (integrity/certificate), transpile/c/tool/lin_c0_front.c (C0_LIMIT_*), SECURITY_AUDIT.md (prior art)`
  - Aceite: O veredito de `integrity` declara explicitamente que nenhuma execução ocorreu.; `docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel` traz a tabela de limites divergentes.; Nenhum gate compara cobertura sem mencionar os caps de cada host.

## Impacto

Expectativa de seguranga falsa sobre a cadeia de suprimento do binario; usuarios instalam
asset inexistente/nao-verificado.

## Sugestão de correção

Deixar o status explicito nos docs ('patch pronto, NAO aplicado' já esta em
LIN_SEM_ZIG_CAMINHOS:linhas de faixa 1, mas a frase do release não) ou aplicar os jobs;
remover a referencia a `nucleus.lock.json` ou reintroduzi-la.

## Critérios de aceite

- [ ] Nenhum documento afirma que a CI pública assets enquanto o job não existir.
- [ ] Referencias a arquivos de trava apontam para arquivos presentes no tree.
- [ ] README/docs listam quais gates rodam em CI hoje (nenhum) e quais rodam so locais.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
