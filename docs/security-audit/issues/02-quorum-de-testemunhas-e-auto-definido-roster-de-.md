# [Seguranca] Quorum de testemunhas e auto-definido: roster de 1-de-1 com chave derivada de constante pública e aceito

**Labels sugeridas:** `security`, `security/critical`, `c2`
**Categoria da auditoria:** C2 confianca no lado errado
**Severidade:** CRITICA
**ID do achado:** F-02

## Problema e por que é explorável

O arquivo de roster contem simultaneously as identidades (pubkeys), as assinaturas e o
limiar de quorum. Como `quorum_threshold=1` com `N=1` passa na checagem de maioria e as
chaves podem ser regeradas de um prefixo público, o verificador aceita o checkpoint que um
atacante quiser. PoC executado neste ambiente: `lin notary-sign -o forged.rulel --witnesses
1 --threshold 1 --tree-size 999999 --epoch 7 --state-root sha256:aaaa...` seguido de `lin
notary-verify` => '[QUORUM SATISFIED]' e 'TRANSPARENCY CHECKPOINT VERIFIED', com receipt
escrito.

## Evidência (arquivo:linha)

`compiler/lin.zig:7284-7338 (parse + politica de quorum), 7363-7380 (verifyOne), 12455-12615 (notary-sign, seed default), 12643-12700 (notary-verify le witness_roster.rulel do CWD)`

```
// compiler/lin.zig:7284-7292 - tudo vem do MESMO arquivo que se verifica
pub fn parse(alloc, bytes) !Parsed {
    if (!std.mem.startsWith(u8, bytes, "@RULEL:LIN_WITNESS_ROSTER:1.0.0")) ...
    .quorum_threshold = findIntField(bytes, "quorum_threshold") orelse ...,
}
// compiler/lin.zig:7337-7341 - politica aceita 1-de-1
if (parsed.head.quorum_threshold == 0) return error.QuorumThresholdZero;
if (parsed.head.quorum_threshold > n) return error.QuorumThresholdExceedsRoster;
if (parsed.head.quorum_threshold * 2 <= n) return error.QuorumThresholdNotMajority;
// compiler/lin.zig:12457 - material de chave publico por default
var seed_prefix: []const u8 = "lin-transparency-selftest";
```

## Condições de explorabilidade

Explorável por qualquer pessoa que consiga colocar `witness_roster.rulel` no diretorio de
execução (o caminho e fixo e relativo ao CWD: compiler/lin.zig:12643) - por exemplo no mesmo
tree de um PR. `notary-verify <arquivo>` ignora o argumento posicional e le o default, entao
nem o operador percebe a troca.

## Impacto

Log de transparencia forjavel de ponta a ponta: arvore, epoch e state root arbitrarios
'notarizados'. Todo consumidor do receipt `notarization_status=QUORUM_VERIFIED_FROM_ROSTER`
e enganado.

## Sugestão de correção

Pin set de pubkeys de notarios fora do espaco do artefato (arquivo assinado / config de
deploy), exigir `N >= 3` e `M > 2N/3`, recusar rosters com testemunhas novas e exigir que
`--roster` seja obrigatório (sem modo 'sem testemunhas'). Rejeitar argumentos posicionais
desconhecidos em rotas de verificação.

## Critérios de aceite

- [ ] `notary-verify` falha se `quorum_threshold`/`N` não baterem com a politica pinada (N>=3).
- [ ] Um roster com testemunha desconhecida => 'QUORUM NOT SATISFIED' + exit != 0.
- [ ] `notary-verify <arquivo>` usa o arquivo informado ou erro de uso (não le o CWD as escondidas).
- [ ] Nenhum default de seed prefix em rota que gera chaves; `--seed-prefix` passa a ser obrigatório.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
