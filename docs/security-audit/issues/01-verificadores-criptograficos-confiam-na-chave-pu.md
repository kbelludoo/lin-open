# [Seguranca] Verificadores criptograficos confiam na chave pública embutida no próprio documento verificado

**Labels sugeridas:** `security`, `security/critical`, `c1`
**Categoria da auditoria:** C1 isolamento/ancoragem
**Severidade:** CRITICA
**ID do achado:** F-01

## Problema e por que é explorável

A assinatura Ed25519 e valida contra a chave pública que o próprio documento declara.
Qualquer pessoa gera um par de chaves, assina as proprias alegacoes e obtem um documento que
passa em todas as rotas de verificação. Não ha roster pinado, nenhuma âncora externa e
nenhuma checagem de revogação nessas rotas. O resultado impresso e 'ATTESTATION VALID' /
'PROVENANCE ... Verified authentic git lineage'.

## Evidência (arquivo:linha)

`compiler/lin.zig:8607-8621 (attest-verify); compiler/lin.zig:9806-9832 (verify-004); compiler/lin.zig:10392-10420 e 10623 (bundle-pack/bundle verify); compiler/lin.zig:11223 (ref externa)`

```
// attest-verify - compiler/lin.zig:8607-8621
// 7. Decode Key & Signature DIRECTLY from Document & Cryptographically Verify
if (doc.pubkey_hex.len != 64 or doc.signature_hex.len != 128) {
    return error.InvalidKeyOrSignatureLength;
}
var pubkey_raw: [32]u8 = undefined;
_ = try std.fmt.hexToBytes(&pubkey_raw, doc.pubkey_hex);
...
const pubkey = try std.crypto.sign.Ed25519.PublicKey.fromBytes(pubkey_raw);
try sig.verify(canonical_msg, pubkey);   // <- a chave vem do documento assinado
```

## Condições de explorabilidade

Sem condição: qualquer `.rulel` produzido com `attest-issue --key <arquivo meu>` (ou com
chave própria + edição dos campos) e aceito. O `nversion`/`cert` seguem o mesmo padrão de
ancoragem.

## Impacto

Provas de execução/provenance deixam de ser provas. Um agente que queira publicar um
resultado adulterado pode emitir atestado 'valido' e o verificador de terceiros confirma.
Destroi a premissa central do projeto (receipt/attestation verificavel).

## Sugestão de correção

Resolver a chave contra uma âncora fora do documento: roster/allowlist de authorities pinado
em arquivo versionado e assinado (ou policy de transparencia tipo Sigstore), e recusar
quando `pubkey_hex` não pertence ao conjunto. Checar revogação/epoch na mesma rota. O roster
de notarios deve chegar por canal fora de faixa (out-of-band), não do diretorio do artefato.

## Critérios de aceite

- [ ] `attest-verify` de um documento assinado por chave fora do roster pinado sai BLOCKED com código nomeado.
- [ ] O roster usado na verificação não e lido do CWD nem do mesmo diretorio do documento.
- [ ] Teste adversario: `attest-issue --key <chave nova>` + `attest-verify` => REJEITADO (hoje PASSA).
- [ ] Documentação deixa de dizer 'authenticated' sem âncora de confiança explicita.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
