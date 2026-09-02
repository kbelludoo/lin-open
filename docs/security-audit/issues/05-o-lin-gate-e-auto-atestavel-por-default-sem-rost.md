# [Seguranca] O LIN Gate e auto-atestavel por default: sem roster, quem adultera o compilador também limpa o gate

**Labels sugeridas:** `security`, `security/medium`, `c1`
**Categoria da auditoria:** C1 isolamento/ancoragem
**Severidade:** MEDIA
**ID do achado:** F-05

## Problema e por que é explorável

O gate detecta adulteração, mas não prova quem a re-atestou: `python3
test/verify_gate_manifest.py --attest` regrava a raiz e o `gate-check` volta a dizer OPEN.
PoC neste ambiente: acrescentei uma linha em `compiler/lin.zig` => `error: GateBlocked` e
'GATE BLOCKED' no python; rodei o `--attest` => 'GATE OPEN - a raiz do disco coincide com a
atestada'. O modo assinado existe e e fail-closed (`gate-check --roster` sobre manifesto não
assinado => 'GATE BLOCKED - attestation signature not verified', medido), porem e opcional,
o roster e lido de caminho arbitrario (logo editavel no mesmo PR) e a porta sem-Zig nem
implementa assinatura.

## Evidência (arquivo:linha)

`Makefile:170-186 (gate/gate-attest, GATE_ROSTER opcional), test/verify_gate_manifest.py:137-142 e 164-165 (sem suporte a roster/assinatura), compiler/lin.zig:15678-15692 (claim 'a gate that blocks a pull request - AI-authored or not'), .github/workflows/ci.yml (nenhum job chama o gate)`

```
# Makefile:176-186
gate: build-cpu
ifeq ($(GATE_ROSTER),)
	@$(BIN) gate-check
else
	@$(BIN) gate-check --roster $(GATE_ROSTER)
endif
# test/verify_gate_manifest.py:165
print("  manifesto escrito: %s (attested_by=%s - NAO assinado)" % (manifest, args.attested_by))
```

## Condições de explorabilidade

Explorabilidade real = 'quem pode abrir PR contra a master': não precisa de segredo, apenas
do direito de editar o arquivo de manifesto (o mesmo direito já da para editar o
compilador). A mitigação depende de branch protection + revisão humana, não do gate.

## Impacto

Controle de integridade de supply chain descrito como bloqueante e, na prática, advisory; em
particular o job `compiler0-no-zig` proposto (docs/CI_COMPILER0_NO_ZIG_JOB_PATCH.rulel) usa
apenas a porta python não-assinada.

## Sugestão de correção

Tornar `--roster` obrigatório no `make gate` (com roster pinado fora da arvore do PR ou
assinado por maintainers), portar a checagem de assinatura para
`test/verify_gate_manifest.py`, e registrar o gate num job de CI (bloqueando merge).

## Critérios de aceite

- [ ] `make gate` sem GATE_ROSTER falha (não e mais modo padrão).
- [ ] `python3 test/verify_gate_manifest.py --roster <R>` reproduz o veredito assinado do Zig.
- [ ] O job de CI executa gate + roster e o merge exige check verde.
- [ ] Adulterar compiler/lin.zig + reatestar sem a chave do maintainer => CI vermelho (prova de PoC).

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
