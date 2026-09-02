# [Seguranca] Receipts 'cryptographically verified' são apenas autocoerencia de hash - e a decisão de 'verificado' acontece no navegador

**Labels sugeridas:** `security`, `security/high`, `c2`
**Categoria da auditoria:** C2 confianca no lado errado
**Severidade:** ALTA
**ID do achado:** F-03

## Problema e por que é explorável

input, output, steps e sp_at_ret vem do receipt; o verificador so recomputa SHA-256(leaf) e
compara. Não ha chave, assinatura, nem re-execução. PoC neste ambiente: receipt forjado com
`output=12345` (a função e `x*x`, entrada 9, saída correta 81) => `node verify_receipt.js`
imprime PASS e `lin receipt-verify --receipt` imprime 'PASS: Compute Receipt ...
cryptographically verified!'.

## Evidência (arquivo:linha)

`compiler/lin.zig (receipt-verify), benchmarks/verify_receipt.js:1-20 e 96-131, benchmarks/verify_receipt.html:19-27 e 100-140, tool/lin_c_receipt.c (so emissor, sem verificador na porta C11)`

```
// benchmarks/verify_receipt.html:100-140 (e o mesmo em verify_receipt.js)
const computed = await sha256(leaf);       // leaf = campos do proprio receipt
let ok = computed === claimed;
if (source) { ... }                        // checagem do artifact e OPCIONAL
out.textContent = ... + (ok ? "[PASS] Receipt validated by an independent open-source verifier"
                            : "[FAIL] Receipt forged or tampered!");
```

## Condições de explorabilidade

Sem condição: basta saber a formula aberta do formato, documentada na própria página ('Open
format: merkle_root = SHA-256(...)').

## Impacto

Falsa sensação de prova. Um verifier terceirizado (a página e distribuida como
'independent') aprova qualquer resultado. O rótulo 'cryptographically verified' e overclaim:
o receipt honestamente se declara `verification_level=0` / `INTEGRITY_RECEIPT_LOCAL`, mas a
saída do verificador não preserva esse nível.

## Sugestão de correção

Renomear o veredicto para o que ele e ('autoconsistente / nível 0') e imprimir o nível
declarado no receipt; para virar prova, vincular o receipt a execucão: re-executar na LinVM
(`lin_c0 vm` / `lin vm`) e comparar value+steps+sp_at_ret, ou entao exigir assinatura de um
emissor pinado (ver F-01). Manter a checagem do `artifact` obrigatória quando houver fonte.

## Critérios de aceite

- [ ] A página/CLI exibem `verification_level` e a frase do veredicto não usa 'cryptographic' para nível 0.
- [ ] Receipt com output alterado e `--source` informado => FAIL (hoje o source check e opcional).
- [ ] Um verificador de nível 1+ (re-execução na VM) existe e falha para receipt forjado.
- [ ] Nenhum caminho de CI apresenta nível 0 como prova de execução.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
