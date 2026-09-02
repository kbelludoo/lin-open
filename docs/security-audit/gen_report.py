#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador do RELATÓRIO DE AUDITORIA DE SEGURANÇA do projeto LIN (lin-open).

Re-generar depois de mudar o código:
    /home/user/.venv-sec/bin/python docs/security-audit/gen_report.py
    (venv isolado: reportlab + matplotlib; nada instalado globalmente)

O conteúdo (achados, evidências com arquivo:linha, severidades e as issues do
GitHub) vive na lista FINDINGS abaixo -- é a única fonte de verdade do PDF e dos
blocos de issue. Os gráficos (rosca por severidade, barras por categoria) são
derivados dos mesmos dados, então corrigir uma severidade aqui atualiza tudo.

Saídas:
    docs/security-audit/relatorio-auditoria-seguranca.pdf
    docs/security-audit/issues/NN-<slug>.md      (mesmo texto, arquivo por issue)
"""
import argparse
import collections
import datetime
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

REPORT_TITLE = "Relatorio de Auditoria de Seguranca - LIN (lin-open)"
PROJECT = "LIN / lin-open (kbelludoo/lin-open)"
DATE = "1 de setembro de 2026"

SEV_COLORS = {
    "critica": "#B91C1C",
    "alta": "#EA580C",
    "media": "#D97706",
    "baixa": "#2563EB",
    "informativa": "#6B7280",
    "forte": "#059669",
}
SEV_LABEL = {"critica": "CRITICA", "alta": "ALTA", "media": "MEDIA",
             "baixa": "BAIXA", "informativa": "INFORMATIVA", "forte": "PONTO FORTE"}
CATS = [
    ("C1", "C1 - BANCO SEM TRANCA (isolamento/ancoragem)"),
    ("C2", "C2 - PERMISSAO/CONFIANCA DECIDIDA NO LADO ERRADO"),
    ("C3", "C3 - REFERENCIA NAO VALIDADA (IDOR analogo)"),
    ("C4", "C4 - CHAVES E SEGREDO EMBUTIDO"),
    ("C5", "C5 - TRATAMENTO DE INPUT (XSS/injecao)"),
    ("C0", "C0 - ESCOPO NAO APLICAVEL / HIGIENE"),
]
CAT_SHORT = {"C1": "C1 isolamento/ancoragem", "C2": "C2 confianca no lado errado",
             "C3": "C3 referencia nao validada", "C4": "C4 chaves/segredos",
             "C5": "C5 tratamento de input", "C0": "C0 escopo/higiene"}

# ----------------------------------------------------------------------------------
# ACHADOS
# ----------------------------------------------------------------------------------
FINDINGS = [
dict(id="F-01", cat="C1", sev="critica",
 title="Verificadores criptograficos confiam na chave publica embutida no proprio documento verificado",
 files="compiler/lin.zig:8607-8621 (attest-verify); compiler/lin.zig:9806-9832 (verify-004); compiler/lin.zig:10392-10420 e 10623 (bundle-pack/bundle verify); compiler/lin.zig:11223 (ref externa)",
 evidence='''// attest-verify - compiler/lin.zig:8607-8621
// 7. Decode Key & Signature DIRECTLY from Document & Cryptographically Verify
if (doc.pubkey_hex.len != 64 or doc.signature_hex.len != 128) {
    return error.InvalidKeyOrSignatureLength;
}
var pubkey_raw: [32]u8 = undefined;
_ = try std.fmt.hexToBytes(&pubkey_raw, doc.pubkey_hex);
...
const pubkey = try std.crypto.sign.Ed25519.PublicKey.fromBytes(pubkey_raw);
try sig.verify(canonical_msg, pubkey);   // <- a chave vem do documento assinado''',
 why=("A assinatura Ed25519 e valida contra a chave publica que o proprio documento "
      "declara. Qualquer pessoa gera um par de chaves, assina as proprias alegacoes e obtem "
      "um documento que passa em todas as rotas de verificacao. Nao ha roster pinado, "
      "nenhuma ancora externa e nenhuma checagem de revogacao nessas rotas. O resultado "
      "impresso e 'ATTESTATION VALID' / 'PROVENANCE ... Verified authentic git lineage'."),
 exp=("Sem condicao: qualquer `.rulel` produzido com `attest-issue --key <arquivo meu>` "
      "(ou com chave propria + edicao dos campos) e aceito. O `nversion`/`cert` seguem o "
      "mesmo padrao de ancoragem."),
 impact=("Provas de execucao/provenance deixam de ser provas. Um agente que queira publicar "
         "um resultado adulterado pode emitir atestado 'valido' e o verificador de terceiros "
         "confirma. Destroi a premissa central do projeto (receipt/attestation verificavel)."),
 fix=("Resolver a chave contra uma ancora fora do documento: roster/allowlist de authorities "
      "pinado em arquivo versionado e assinado (ou policy de transparencia tipo Sigstore), e "
      "recusar quando `pubkey_hex` nao pertence ao conjunto. Checar revogacao/epoch na mesma "
      "rota. O roster de notarios deve chegar por canal fora de faixa (out-of-band), nao do "
      "diretorio do artefato."),
 accept=["`attest-verify` de um documento assinado por chave fora do roster pinado sai BLOCKED com codigo nomeado.",
         "O roster usado na verificacao nao e lido do CWD nem do mesmo diretorio do documento.",
         "Teste adversario: `attest-issue --key <chave nova>` + `attest-verify` => REJEITADO (hoje PASSA).",
         "Documentacao deixa de dizer 'authenticated' sem ancora de confianca explicita."],
 issue=None),

dict(id="F-02", cat="C2", sev="critica",
 title="Quorum de testemunhas e auto-definido: roster de 1-de-1 com chave derivada de constante publica e aceito",
 files="compiler/lin.zig:7284-7338 (parse + politica de quorum), 7363-7380 (verifyOne), 12455-12615 (notary-sign, seed default), 12643-12700 (notary-verify le witness_roster.rulel do CWD)",
 evidence='''// compiler/lin.zig:7284-7292 - tudo vem do MESMO arquivo que se verifica
pub fn parse(alloc, bytes) !Parsed {
    if (!std.mem.startsWith(u8, bytes, "@RULEL:LIN_WITNESS_ROSTER:1.0.0")) ...
    .quorum_threshold = findIntField(bytes, "quorum_threshold") orelse ...,
}
// compiler/lin.zig:7337-7341 - politica aceita 1-de-1
if (parsed.head.quorum_threshold == 0) return error.QuorumThresholdZero;
if (parsed.head.quorum_threshold > n) return error.QuorumThresholdExceedsRoster;
if (parsed.head.quorum_threshold * 2 <= n) return error.QuorumThresholdNotMajority;
// compiler/lin.zig:12457 - material de chave publico por default
var seed_prefix: []const u8 = "lin-transparency-selftest";''',
 why=("O arquivo de roster contem simultaneously as identidades (pubkeys), as assinaturas e o "
      "limiar de quorum. Como `quorum_threshold=1` com `N=1` passa na checagem de maioria e as "
      "chaves podem ser regeradas de um prefixo publico, o verificador aceita o checkpoint que "
      "um atacante quiser. PoC executado neste ambiente: "
      "`lin notary-sign -o forged.rulel --witnesses 1 --threshold 1 --tree-size 999999 "
      "--epoch 7 --state-root sha256:aaaa...` seguido de `lin notary-verify` => "
      "'[QUORUM SATISFIED]' e 'TRANSPARENCY CHECKPOINT VERIFIED', com receipt escrito."),
 exp=("Exploravel por qualquer pessoa que consiga colocar `witness_roster.rulel` no diretorio "
      "de execucao (o caminho e fixo e relativo ao CWD: compiler/lin.zig:12643) - por exemplo "
      "no mesmo tree de um PR. `notary-verify <arquivo>` ignora o argumento posicional e le o "
      "default, entao nem o operador percebe a troca."),
 impact=("Log de transparencia forjavel de ponta a ponta: arvore, epoch e state root arbitrarios "
         "'notarizados'. Todo consumidor do receipt `notarization_status=QUORUM_VERIFIED_FROM_ROSTER` "
         "e enganado."),
 fix=("Pin set de pubkeys de notarios fora do espaco do artefato (arquivo assinado / config de "
      "deploy), exigir `N >= 3` e `M > 2N/3`, recusar rosters com testemunhas novas e exigir "
      "que `--roster` seja obrigatorio (sem modo 'sem testemunhas'). Rejeitar argumentos posicionais "
      "desconhecidos em rotas de verificacao."),
 accept=["`notary-verify` falha se `quorum_threshold`/`N` nao baterem com a politica pinada (N>=3).",
         "Um roster com testemunha desconhecida => 'QUORUM NOT SATISFIED' + exit != 0.",
         "`notary-verify <arquivo>` usa o arquivo informado ou erro de uso (nao le o CWD as escondidas).",
         "Nenhum default de seed prefix em rota que gera chaves; `--seed-prefix` passa a ser obrigatorio."],
 issue=None),

dict(id="F-03", cat="C2", sev="alta",
 title="Receipts 'cryptographically verified' sao apenas autocoerencia de hash - e a decisao de 'verificado' acontece no navegador",
 files="compiler/lin.zig (receipt-verify), benchmarks/verify_receipt.js:1-20 e 96-131, benchmarks/verify_receipt.html:19-27 e 100-140, tool/lin_c_receipt.c (so emissor, sem verificador na porta C11)",
 evidence='''// benchmarks/verify_receipt.html:100-140 (e o mesmo em verify_receipt.js)
const computed = await sha256(leaf);       // leaf = campos do proprio receipt
let ok = computed === claimed;
if (source) { ... }                        // checagem do artifact e OPCIONAL
out.textContent = ... + (ok ? "[PASS] Receipt validated by an independent open-source verifier"
                            : "[FAIL] Receipt forged or tampered!");''',
 why=("input, output, steps e sp_at_ret vem do receipt; o verificador so recomputa "
      "SHA-256(leaf) e compara. Nao ha chave, assinatura, nem re-execucao. PoC neste ambiente: "
      "receipt forjado com `output=12345` (a funcao e `x*x`, entrada 9, saida correta 81) => "
      "`node verify_receipt.js` imprime PASS e `lin receipt-verify --receipt` imprime "
      "'PASS: Compute Receipt ... cryptographically verified!'."),
 exp="Sem condicao: basta saber a formula aberta do formato, documentada na propria pagina ('Open format: merkle_root = SHA-256(...)').",
 impact=("Falsa sensacao de prova. Um verifier terceirizado (a pagina e distribuida como "
         "'independent') aprova qualquer resultado. O rotulo 'cryptographically verified' e "
         "overclaim: o receipt honestamente se declara `verification_level=0` / "
         "`INTEGRITY_RECEIPT_LOCAL`, mas a saida do verificador nao preserva esse nivel."),
 fix=("Renomear o veredicto para o que ele e ('autoconsistente / nivel 0') e imprimir o nivel "
      "declarado no receipt; para virar prova, vincular o receipt a execucão: re-executar na "
      "LinVM (`lin_c0 vm` / `lin vm`) e comparar value+steps+sp_at_ret, ou entao exigir assinatura "
      "de um emissor pinado (ver F-01). Manter a checagem do `artifact` obrigatoria quando houver fonte."),
 accept=["A pagina/CLI exibem `verification_level` e a frase do veredicto nao usa 'cryptographic' para nivel 0.",
         "Receipt com output alterado e `--source` informado => FAIL (hoje o source check e opcional).",
         "Um verificador de nivel 1+ (re-execucao na VM) existe e falha para receipt forjado.",
         "Nenhum caminho de CI apresenta nivel 0 como prova de execucao."],
 issue=None),

dict(id="F-04", cat="C4", sev="alta",
 title="Chave privada de autoridade gerada com permissao 0644 e nome de arquivo default no CWD",
 files="compiler/lin.zig:7643 e 8719 (default \"authority.key\"), 8038-8044 e 9170-9176 (geracao + createFile sem modo), contraste correto em compiler/lin.zig:15761 (gate-keygen usa .mode = 0o600)",
 evidence='''// compiler/lin.zig:7643 - default relativo ao CWD
var key_path: []const u8 = "authority.key";
// compiler/lin.zig:8038-8044 - gera e escreve sem fixar modo
std.crypto.random.bytes(&authority_seed);
_ = try std.fmt.bufPrint(&key_hex_buf, "{s}", .{std.fmt.fmtSliceHexLower(&authority_seed)});
const kfile = try std.fs.cwd().createFile(key_path, .{});
try kfile.writeAll(&key_hex_buf);
// compiler/lin.zig:15761 - a outra rota FAZ o certo
const kf = try std.fs.cwd().createFile(key_out, .{ .truncate = true, .mode = 0o600 });''',
 why=("`createFile(path, .{})` usa 0o666 & ~umask => 0644 com a umask padrao: o seed privado de "
      "256 bits fica legivel por qualquer usuario da maquina e por qualquer job/artefato que "
      "cole o diretorio (upload-artifact, `git add -A`, tarball de debug). O proprio repo ja "
      "sabe fazer certo (`gate-keygen` usa 0o600, medido: `lin_gate_key.seed` saiu 600), entao "
      "e uma inconsistencia na rota de attest - nao falta mecanica, falta aplica-la ali."),
 exp=("Local: qualquer processo do mesmo host le o seed. Em CI: um `upload-artifact` com caminho "
      "amplo (`**`) publica o arquivo; o .gitignore do repo e allowlist, entao `authority.key` nao "
      "seria commitado - mas um `git add -f` ou um bundle da arvore expoe."),
 impact="Roubo da identidade de assinatura de atestados: o atacante passa a emitir atestados validos (com F-01, sem nem precisar do verificador da vitima).",
 fix=("Usar `.mode = 0o600` em todo createFile de material sensivel (8041, 9173), recusar "
      "default `authority.key` se o arquivo ja existir e nao for modo 0600 (validacao de startup), "
      "e imprimir aviso quando o caminho estiver dentro de uma arvore de trabalho."),
 accept=["Apos `attest-issue`, `stat -c %a authority.key` == 600 (hJe nao roda porque o arquivo existe antes de mim).",
         "Rodar com `--key <arquivo existente 0644>` => erro nomeado 'key file is group/other readable'.",
         "grep por `createFile(` em rotas de chave nao deixa nenhum call sem `.mode`.",
         "Teste de CI: `upload-artifact` com `path: .` falha se houver chave no tree."],
 issue=None),

dict(id="F-05", cat="C1", sev="media",
 title="O LIN Gate e auto-atestavel por default: sem roster, quem adultera o compilador tambem limpa o gate",
 files="Makefile:170-186 (gate/gate-attest, GATE_ROSTER opcional), test/verify_gate_manifest.py:137-142 e 164-165 (sem suporte a roster/assinatura), compiler/lin.zig:15678-15692 (claim 'a gate that blocks a pull request - AI-authored or not'), .github/workflows/ci.yml (nenhum job chama o gate)",
 evidence='''# Makefile:176-186
gate: build-cpu
ifeq ($(GATE_ROSTER),)
	@$(BIN) gate-check
else
	@$(BIN) gate-check --roster $(GATE_ROSTER)
endif
# test/verify_gate_manifest.py:165
print("  manifesto escrito: %s (attested_by=%s - NAO assinado)" % (manifest, args.attested_by))''',
 why=("O gate detecta adulteracao, mas nao prova quem a re-atestou: `python3 "
      "test/verify_gate_manifest.py --attest` regrava a raiz e o `gate-check` volta a dizer OPEN. "
      "PoC neste ambiente: acrescentei uma linha em `compiler/lin.zig` => `error: GateBlocked` e "
      "'GATE BLOCKED' no python; rodei o `--attest` => 'GATE OPEN - a raiz do disco coincide com a "
      "atestada'. O modo assinado existe e e fail-closed (`gate-check --roster` sobre manifesto nao "
      "assinado => 'GATE BLOCKED - attestation signature not verified', medido), porem e opcional, "
      "o roster e lido de caminho arbitrario (logo editavel no mesmo PR) e a porta sem-Zig nem "
      "implementa assinatura."),
 exp=("Explorabilidade real = 'quem pode abrir PR contra a master': nao precisa de segredo, "
      "apenas do direito de editar o arquivo de manifesto (o mesmo direito ja da para editar o "
      "compilador). A mitigacao depende de branch protection + revisao humana, nao do gate."),
 impact=("Controle de integridade de supply chain descrito como bloqueante e, na pratica, "
         "advisory; em particular o job `compiler0-no-zig` proposto "
         "(docs/CI_COMPILER0_NO_ZIG_JOB_PATCH.rulel) usa apenas a porta python nao-assinada."),
 fix=("Tornar `--roster` obrigatorio no `make gate` (com roster pinado fora da arvore do PR ou assinado "
      "por maintainers), portar a checagem de assinatura para `test/verify_gate_manifest.py`, e "
      "registrar o gate num job de CI (bloqueando merge)."),
 accept=["`make gate` sem GATE_ROSTER falha (nao e mais modo padrao).",
         "`python3 test/verify_gate_manifest.py --roster <R>` reproduz o veredito assinado do Zig.",
         "O job de CI executa gate + roster e o merge exige check verde.",
         "Adulterar compiler/lin.zig + reatestar sem a chave do maintainer => CI vermelho (prova de PoC)."],
 issue=None),

dict(id="F-06", cat="C4", sev="media",
 title="Material de chave derivado de constante publica e sem validacao de startup (defaults que viram segredo real)",
 files="compiler/lin.zig:12457 (seed_prefix default), 7383-7395 (deriveKeypair), 12591-12601 (id da testemunha contem o prefixo), 12613-12615 (apenas um WARNING impresso)",
 evidence='''// compiler/lin.zig:12457 + 7386-7395
var seed_prefix: []const u8 = "lin-transparency-selftest";
pub fn deriveKeypair(seed_prefix: []const u8, index: usize) !KeyPair {
    h.update("lin:transparency:witness-key:v1:"); h.update(seed_prefix); ...
    return Ed25519.KeyPair.create(seed);   // deterministico a partir do prefixo
}''',
 why=("O comentario no codigo e honesto ('NOT a root of trust'), mas o default esta vivo em rota "
      "de linha de comando que gera chaves e publica roster; o ID da testemunha ainda carrega o "
      "prefixo, facilitando reuso. Nao ha flag que recuse produzir um roster 'de selftest' num "
      "contexto de release, nem checagem de que o prefixo veio de fora."),
 exp="Basta rodar `lin notary-sign` sem `--seed-prefix` (default) e usar o resultado como prova - e o que F-02 demonstra.",
 impact="Chaves de testemunha colestadas por qualquer pessoa => quorum sem valor (multiplica F-02).",
 fix=("Exigir `--seed-prefix`/`--key` explicito (sem default) e, em modo release, importar pubkeys "
      "de notarios de arquivo assinado; marcar o roster gerado com `selftest=true` e fazer o "
      "verificador recusar esse flag por default."),
 accept=["`notary-sign` sem seed prefix => erro de uso (hoje assume default).",
         "Roster autoassinado carrega `selftest=true` e `notary-verify` o recusa a menos de `--allow-selftest`.",
         "README/docs de deploy nao mostram mais o comando sem `--seed-prefix`."],
 issue=None),

dict(id="F-07", cat="C3", sev="media",
 title="Escritas em caminho fixo dentro da arvore de trabalho e execucao de binario escolhido por env/sonda de filesystem",
 files="compiler/lin.zig:7549 (lin rebuild escreve src/lin.zig), 7129-7137 (pick_target escreve .lin_ast_check.zig no CWD e prefere /home/k/.local/bin/zig se existir), 7018-7027 (LIN_ZIG decide o `zig run` do codigo gerado por `lin test`)",
 evidence='''// compiler/lin.zig:7549 - write em caminho fixo do source tree
const tf = try std.fs.cwd().createFile("src/lin.zig", .{});
// compiler/lin.zig:7129-7137 - alvo escolhido por presenca de arquivo no HOME de um dev
const tmp_file = ".lin_ast_check.zig";
if (std.fs.cwd().createFile(tmp_file, .{})) |f| { ... }
if (std.fs.openFileAbsolute("/home/k/.local/bin/zig", .{})) |zf| { zb = "/home/k/.local/bin/zig"; }
// compiler/lin.zig:7018-7027
var zb: []const u8 = "zig";
if (std.process.getEnvVarOwned(LIA_ALLOC, "LIN_ZIG")) |p| { zb = p; }
return std.process.Child.run(.{ .argv = &.{ zb, "run", "-O", "ReleaseFast", tmp_path }, ... });''',
 why=("Tres problemas no mesmo ponto: (i) `rebuild` sobrescreve `src/lin.zig` sem checagem de "
      "symlink nem confirmacao - arquivo pre-criado como link vira escrita fora da arvore; "
      "(ii) `pick_target` faz o resultado da verificacao depender de um caminho absoluto de um "
      "desenvolvedor (`/home/k/...`), entao 'zig' vs 'js' muda de maquina para maquina num "
      "projeto que vende reprodutibilidade bit a bit; (iii) o binario do compilador usado para "
      "compilar e EXECUTAR o codigo gerado vem de `LIN_ZIG`, sem validacao alguma."),
 exp=("Requer a vitima rodar `lin rebuild`/`lin test` num diretorio controlado por terceiro "
      "(compartilhado, CI com checkout de PR, workspace de review) ou com ambiente em que o "
      "atacante seta variaveis."),
 impact=("Escrita arbitraria/quebra de arquivo-fonte; resultado de verificacao nao reproduzivel; "
         "execucao de binario arbitrario com o codigo gerado a partir do input (RCE em fluxo de "
         "review/CI)."),
 fix=("Escrever em caminho explicito via flag (sem default no source tree), abrir com "
      "`O_NOFOLLOW`/verificar symlink, e exigir `--zig <caminho>` (ou resolver so pelo PATH, com "
      "hash esperado) para o compilador externo; substituir a sonda `/home/k/...` por config explicita."),
 accept=["`lin rebuild` recusa escrever fora do diretorio informado e nao toca em caminho fixo.",
         "Nenhum caminho absoluto de usuario aparece no codigo-fonte (grep `/home/` em compiler/*.zig => 0).",
         "`lin test` com `LIN_ZIG=/bin/false` falha com erro nomeado, sem executar o que foi gerado.",
         "O alvo escolhido (zig/js) sai impresso com a justificativa e e identico em duas maquinas limpas."],
 issue=None),

dict(id="F-08", cat="C5", sev="baixa",
 title="Documentacao afirma gates/publicacao em CI que o workflow nao contem (falsa garantia)",
 files=".github/workflows/ci.yml (92 linhas; nenhum job 'release' nem 'gate' nem 'compiler0-no-zig'), docs/LIN_SEM_ZIG_CAMINHOS.rulel:24-31, docs/CI_RELEASE_E_V1_GATES_PATCH.rulel, docs/CI_COMPILER0_NO_ZIG_JOB_PATCH.rulel, HISTORY.rulel:78 (nucleus.lock.json inexistente)",
 evidence='''docs/LIN_SEM_ZIG_CAMINHOS.rulel: "Este PR fecha essa divergencia: a CI agora sobe os
artifacts lin_native-cpu/lin_native-gpu em toda execucao e publica os dois como assets de
Release ao empurrar tag `v*` (job `release`, --verify-tag)."
$ grep -c "release" .github/workflows/ci.yml   ->  0
$ ls nucleus.lock.json                          ->  No such file or directory''',
 why=("O texto diz que a CI publica assets verificaveis; o workflow em arvore nao tem o job (o "
      "patch esta em `docs/CI_*_PATCH.rulel`, aguardando aplicacao por falta de escopo `workflows`). "
      "Quem seguir o doc para 'baixar e verificar' nao encontra o asset nem a verificacao. O "
      "arquivo `nucleus.lock.json`, citado como trava de integridade do verificador, nao existe."),
 exp="Sem condicao tecnica; e leitura de documentação. Materializa-se quando alguem confia na promessa em vez do manifesto.",
 impact="Expectativa de seguranga falsa sobre a cadeia de suprimento do binario; usuarios instalam asset inexistente/nao-verificado.",
 fix="Deixar o status explicito nos docs ('patch pronto, NAO aplicado' ja esta em LIN_SEM_ZIG_CAMINHOS:linhas de faixa 1, mas a frase do release nao) ou aplicar os jobs; remover a referencia a `nucleus.lock.json` ou reintroduzi-la.",
 accept=["Nenhum documento afirma que a CI publica assets enquanto o job nao existir.",
         "Referencias a arquivos de trava apontam para arquivos presentes no tree.",
         "README/docs listam quais gates rodam em CI hoje (nenhum) e quais rodam so locais."],
 issue=None),

dict(id="F-09", cat="C0", sev="baixa",
 title="CI sem bloco `permissions:` e com acao de terceiro referida por tag mutavel",
 files=".github/workflows/ci.yml:1-23 (sem `permissions:`), :27 (`goto-bus-stop/setup-zig@v2`), :88 (`upload-artifact@v4`)",
 evidence='''on:
  push: { branches: [master, main] }
  pull_request:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: goto-bus-stop/setup-zig@v2   # tag mutavel, nao fixada em SHA''',
 why=("Sem `permissions:` explicito, o `GITHUB_TOKEN` herda a politica padrao do repo (frequentemente "
      "escrita em contents/metadata); e a acao de terceiros e consumida por tag, que pode ser movida "
      "a monte. Num repositorio cuja superficie de seguranca e 'verifique os hashes voce mesmo', a "
      "cadeia de CI e o elo mais fraco."),
 exp="Requer que o padrao do repo conceda escrita ou que a tag upstream seja comprometida (ataque de supply chain classico).",
 impact="Superficie maior do que o necessario no runner; risco de troca do fornecedor da toolchain.",
 fix="Adicionar `permissions: { contents: read }` (e escrita so no job de release) e fixar `uses: ...@<sha>` com o numero da tag em comentario.",
 accept=["`gh api repos/kbelludoo/lin-open/actions/permissions` (ou inspecao do YAML) mostra escopo minimo por job.",
         "Toda `uses:` de terceiro apontando para SHA de 40 hex.",
         "O job de release (quando existir) declara escrita apenas nele."],
 issue=None),

dict(id="F-10", cat="C3", sev="informativa",
 title="Alegacao tecnica falsa sobre o loader de confianca, duplicacao da mesma logica e comentario depreciativo no documento de fronteira",
 files="transpile/c/tool/lin_c0.c:156-165, docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel (secao 7), compiler0_manifest.rulel, HISTORY.rulel (entrada C0-no-Zig cont.)",
 evidence='''/* transpile/c/tool/lin_c0.c:156-165
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
    return -1; }''',
 why=("O `strlen` do loader e aplicado no nome solicitado (argv), nunca na pool; a comparacao ja "
      "usa `name_len[i]`. Medido: `lin_bc1_run` e `lin_c0 run` resolvem nomes em qualquer posicao "
      "(`lex_gate`, `lex_scan_embedded`, `lex_count_embedded` = 1 / 1371904279658369433 / 20) e "
      "recusam nome inexistente. O par de nomes com prefixo comum (`gate`, `gate_x`) resolve "
      "corretamente pelas duas rotas. Logo: nao ha vulnerabilidade, mas a alegacao publicada "
      "(doc §7, HISTORY e comentario) afirma que o TCB tem um furo e duplica a funcao do loader "
      "'por seguranca'."),
 exp="Nao exploravel. O custo e de confianca/revisao: quem audita confia menos no loader do que deveria e mantem dois codigos identicos.",
 impact="Documentacao de fronteira incorreta + logica redundante a `tool/` (manutencao).",
 fix="Corrigir comentario e docs (remover a alegacao), e ou chamar `lin_bc1_find_fn` diretamente ou justificar a copia com o motivo real (independencia de host), nao com um defeito inexistente.",
 accept=["grep 'so e seguro no ultimo nome' nao retorna nada no repo.",
         "Secao 7 do doc descreve `bc1_find_fn_strict` como comparacao por comprimento equivalente a do loader.",
         "Um teste cobre resolucao de nomes em primeira/meia/ultima posicao (rota fonte e rota imagem)."],
 issue=None),

dict(id="F-11", cat="C5", sev="informativa",
 title="Verificacao de paridade/reportes com `steps=0` e status PASS; limites divergentes entre hosts",
 files="compiler/lin.zig (integrity/certificate), transpile/c/tool/lin_c0_front.c (C0_LIMIT_*), SECURITY_AUDIT.md (prior art)",
 evidence='''$ ./zig-out/bin/lin_native integrity | tail -7
.compiler_sha256="16272e2f..."  .corpus_sha256="28b64d74..."
.targets=20  .confirmed=20  .refuted=0  .steps=0  .status="PASS"
$ lin_c0 vm <fonte com 60000 parenteses aninhados> -> .fatal{ reason="C0_LIMIT_TOO_MANY_TOKENS" }
$ lin_native check <mesma fonte>                        -> OK (parser iterativo)''',
 why=("Dois pontos de higiene, nao falhas: (i) `integrity` declara PASS sem executar nenhum passo "
      "(e conformidade de hashes, como SECURITY_AUDIT.md ja concluiu - o status deveria dizer isso); "
      "(ii) o host C11 e mais estrito que o Stage0 em tokens, entao um fonte valido no Zig pode ser "
      "recusado na LinVM (fail-closed e correto, mas a divergencia de cobertura precisa estar "
      "documentada para quem compara as duas rotas)."),
 exp="Nao requer condicao; so nao se deve ler 'PASS' como prova de execucao.",
 impact="Leitura errada de vereditos; ruido em cross-checks entre implementacoes.",
 fix="Renomear/rotular o status (`CONFORMANCE_PASS`) e listar na tabela de fronteira os limites proprios de cada host (`C0_LIMIT_*`) ao lado dos do Stage0.",
 accept=["O veredito de `integrity` declara explicitamente que nenhuma execucao ocorreu.",
         "`docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel` traz a tabela de limites divergentes.",
         "Nenhum gate compara cobertura sem mencionar os caps de cada host."],
 issue=None),
]

STRENGTHS = [
 ("Loader LINBC1 fail-closed e com validacao de referencias (o 'IDOR' de bytecode)",
  "transpile/c/lin_c/lin_linbc1.c:114-170 valida name_idx, nparams<=nlocals, nlocals<=64, "
  "n_arrs<=8, alen em 1..256, duplicata de descritor, jump/call/local fora de alcance e "
  "contagem total de instrucoes; 184-189 confere o self-hash `linbc1:img:` nos 32 bytes finais. "
  "PoC: quatro imagens mutadas de 1 byte (contagem de strings, corpo, cauda, campo de tamanho) => "
  "todas `REJECTED` (`linbc1.selfhash` / `linbc1.flags`), sem crash, nos dois hosts "
  "(`lin_bc1_run` e `lin_c0 run`)."),
 ("Nenhuma API de risco no host C11",
  "grep de `strcpy|strcat|sprintf|gets|alloca|system|popen|execv|scanf` em transpile/c/ => zero "
  "ocorrencias fora de comentarios; o runtime e zero-allocation (arena fixa) e o loader nao alocada: "
  "tudo em armazenamento do chamador, com os big-objects declarados `static` "
  "(transpile/c/tool/lin_bc1_run.c:36-37 e tool/lin_c0.c:171-172) - nao estouram pilha."),
 ("Sem injecao no codigo Zig gerado por `lin test`",
  "compiler/lin.zig:6989-7001 injeta nomes de funcao no texto Zig compilado e executado, porem a "
  "lista vem de `lin_check`/`read_ident`, que corta no primeiro caractere fora de identificador. "
  "PoC medido (Zig e C11 concordam): `!test_a\";` vira `test_a`, `test.a` vira `test`, "
  "`test_x}{` vira `test_x` - aspas/parenteses/unicode nunca chegam ao gerador."),
 ("Verificadores auxiliares bem escritos (python/bash)",
  "`subprocess.run` sempre com lista de argumentos (sem `shell=True`) em "
  "test/verify_gate_manifest.py:86-91, test/verify_compiler0_manifest.py:72 e "
  "examples/*.py; bash com `set -euo pipefail` e `mktemp -d` + `trap` "
  "(test/verify_c0_selfhost.sh:19-22, test/verify_c0.sh, verify_linvm0.sh:21-27 falha se o binario "
  "nao existe em vez de passar)."),
 ("Pagina do verificador nao tem XSS",
  "benchmarks/verify_receipt.html escreve tudo com `textContent` (linhas 121-140) e valida o "
  "digest com regex `/^[0-9a-fA-F]{64}$/`; `BigInt` falha fechado para campos nao numericos. Nenhum "
  "uso de `innerHTML`, `insertAdjacentHTML`, `eval`, `new Function` no repo "
  "(grep em *.html/*.js/*.mjs => 0). O risco real da pagina e outro (F-03): o que ela verifica."),
 ("Modo assinado do gate e fail-closed quando acionado; gate-keygen protege a chave",
  "`gate-check --roster <R>` sobre manifesto nao assinado => 'GATE BLOCKED - attestation signature "
  "not verified: 0 valid signature(s), 1 required' (medido). `gate-keygen` cria `lin_gate_key.seed` "
  "com `.mode = 0o600` (medido: stat = 600), e o roster tem politica de maioria (`*2 <= n` rejeitado)."),
 ("GPU nao finge PASS sem OpenCL real",
  "`lin_native gpu-verify examples/map_kernels.lin` no build `-Dgpu=false` => 'no OpenCL platforms "
  "found' e saida nao-zero (medido). O PoC historico de runtime OpenCL falso "
  "(redteam/fake_ocl.c + SECURITY_AUDIT.md §1) permanece documentado e a conclusao 'paridade e "
  "conformidade, nao prova criptografica' continua valida - mas nao ha mais PASS falso por default."),
 ("Historico e arvore livres de segredos commitados",
  "Varredura completa: `git log --all -p` (7 commits) para padroes GitHub PAT/AWS/xox/PEM "
  "PRIVATE KEY/`SECRET_KEY=`/`PASSWORD=` => zero ocorrencias; nenhum `.env`, `*.key`, `*.pem` ou "
  "seed em `git ls-files`; .gitignore e allowlist (`*` ignorado por default), entao chaves geradas "
  "em `authority.key`/`*.seed`/`witness_roster.rulel` caem fora do commit. O repo usa `secrets.*` em "
  "nenhum ponto e nao tem `pull_request_target`."),
 ("Auto-digests recomputados por verificador independente",
  "test/verify_compiler0_manifest.py:44-52 recalcula em Python o hash do formato "
  "(`linbc1:img:` sobre os bytes do arquivo) em vez de confiar no emissor, e falha com rc=1 quando o "
  "pin e alterado (PoC negativo medido: rc=1; golden trocado no gate => FAIL). As imagens sao "
  "reproduziveis byte a byte (medido 3x)."),
]

WEAKNESSES = [
 ("As 'provas' do projeto nao tem ancora de confianca",
  "Attestados, certificados, rosters de testemunhas e receipts sao verificados contra dados que o "
  "proprio documento traz (F-01, F-02, F-03). Isso nao e um bug pontual: e a ausencia de um "
  "mecanismo de ancoragem (roster pinado, politica minima, re-execucao). E o equivalente, nesta "
  "stack, de 'query sem filtro de tenant' - a verificacao nao sabe a quem pertence a confianca."),
 ("Controles que so valem se o adversario nao puder escrever no mesmo lugar",
  "O gate lê a raiz de um manifesto versionado que o proprio PR pode regrava (F-05); o roster vem "
  "do CWD (F-02); a chave de autoridade vive no CWD com permissao ampla (F-04); o compilador externo "
  "vem de uma variavel de ambiente (F-07)."),
 ("Rotulos mais fortes do que a mecanica",
  "'cryptographically verified', 'ATTESTATION VALID', 'PROVENANCE ... Verified authentic', "
  "'a gate that blocks a pull request', 'CI publica assets' (F-03, F-05, F-08). Em projeto guiado "
  "pela regra R5 (sem overclaim), esses termos sao parte da superficie de seguranca."),
 ("Escritas e execucões com caminho implicito",
  "F-07: `src/lin.zig` sobrescrito, `.lin_ast_check.zig` no CWD, binario por `LIN_ZIG`, "
  "sonda `/home/k/...` - comportamento que depende do ambiente em rotas de verificacao."),
 ("Porta sem-Zig com garantias menores do que a porta com Zig",
  "A rota `python3 test/verify_gate_manifest.py` (usada pelo job `compiler0-no-zig` proposto) nao "
  "verifica assinatura nem implementa quorum; e nao existe verificador de receipt em C11 "
  "(`tool/lin_c_receipt.c` so emite) (F-03, F-05)."),
]

RECS = [
 ("P1", "Ancorar toda verificacao criptografica em confianca externa ao documento",
  "Roster/allowlist de authorities pinado (arquivo versionado + assinado por maintainers, fora do "
  "espaco do artefato), politica minima de quorum no verificador (N>=3, M>2N/3), checagem de "
  "revogacao/epoch. Elimina F-01 e F-02."),
 ("P1", "Reclassificar/retirar o rotulo 'cryptographically verified' dos receipts e publicar um verificador com re-execucao",
  "Veredicto deve dizer `verification_level` do receipt; o verificador de nivel 1 re-executa na VM "
  "(ou na LinVM `lin_c0`) e compara value+steps+sp_at_ret. Corrige F-03 e a leitura errada em F-11."),
 ("P1", "Permissoes de arquivo de chave e recusa de defaults em rotas de segredo",
  "`.mode = 0o600` em todo createFile de segredo (8041, 9173), sem default `authority.key`/seed "
  "prefix, erro explicito quando o arquivo existente e legivel por grupo/outros. Corrige F-04 e F-06."),
 ("P2", "Gate obrigatorio, assinado e em CI",
  "`make gate` com `--roster` default, portar a checagem de assinatura para a rota python, aplicar o "
  "job `compiler0-no-zig` + um job `gate` na CI e exigir o check para merge. Corrige F-05."),
 ("P2", "Nenhuma escrita/execucao com caminho implicito",
  "Flags obrigatorias para saida, `O_NOFOLLOW`/stat antes de escrever, `--zig` explicito (ou PATH + "
  "hash esperado), remover a sonda `/home/k/`. Corrige F-07."),
 ("P3", "Hardening de CI e higiene de docs",
  "`permissions:` por job, acoes fixadas por SHA, docs dizendo o que roda em CI hoje, remover/refazer "
  "a referencia a `nucleus.lock.json`. Corrige F-08 e F-09."),
 ("P3", "Corrigir a alegacao sobre o loader e deduplicar a busca de funcao",
  "Textos e comentario de F-10; manter uma unica implementacao (ou justificar a copia como "
  "independencia de host)."),
]

for _f in FINDINGS:
    _f["title_slug"] = _f["title"]


def esc(s):
    return html.escape(s, quote=False)


def wrap(text, width=95):
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return "\n".join(out)


def make_issue(f, n):
    # slug a partir do titulo SEM acentos (o PDF aplica as formas acentuadas na
    # renderizacao; o nome de arquivo tem de ficar ASCII)
    raw = f.get("title_slug") or f["title"]
    raw = raw.replace("\u00e7","c").replace("\u00e3","a").replace("\u00e1","a").replace("\u00e9","e")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")[:48]
    sev_map = {"critica": "security/critical", "alta": "security/high", "media": "security/medium",
               "baixa": "security/low", "informativa": "security/info"}
    labels = ["security", sev_map[f["sev"]], CATS[[c[0] for c in CATS].index(f["cat"])][0].lower()]
    body = []
    body.append("# [Seguranca] %s" % f["title"])
    body.append("")
    body.append("**Labels sugeridas:** %s" % ", ".join("`%s`" % l for l in labels))
    body.append("**Categoria da auditoria:** %s" % CAT_SHORT[f["cat"]])
    body.append("**Severidade:** %s" % f["sev"].upper())
    body.append("**ID do achado:** %s" % f["id"])
    body.append("")
    body.append("## Problema e por que é explorável")
    body.append("")
    body.append(wrap(f["why"], 92))
    body.append("")
    body.append("## Evidência (arquivo:linha)")
    body.append("")
    body.append("`%s`" % f["files"])
    body.append("")
    body.append("```")
    body.append(f["evidence"].rstrip())
    body.append("```")
    body.append("")
    body.append("## Condições de explorabilidade")
    body.append("")
    body.append(wrap(f["exp"], 92))
    body.append("")
    body.append("## Impacto")
    body.append("")
    body.append(wrap(f["impact"], 92))
    body.append("")
    body.append("## Sugestão de correção")
    body.append("")
    body.append(wrap(f["fix"], 92))
    body.append("")
    body.append("## Critérios de aceite")
    body.append("")
    for c in f["accept"]:
        body.append("- [ ] %s" % c)
    body.append("")
    body.append("---")
    body.append("_Gerado por `docs/security-audit/gen_report.py` (auditoria de %s)._" % DATE)
    return slug, "\n".join(body)


def charts(out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sev_order = ["critica", "alta", "media", "baixa", "informativa"]
    sev_count = collections.Counter(f["sev"] for f in FINDINGS)
    donut = os.path.join(out_dir, "_chart_sev.png")
    fig, ax = plt.subplots(figsize=(4.4, 2.9), dpi=220)
    vals = [sev_count.get(s, 0) for s in sev_order]
    cols = [SEV_COLORS[s] for s in sev_order]
    labs = ["%s (%d)" % (SEV_LABEL[s].title(), v) for s, v in zip(sev_order, vals) if v]
    w = [v for v in vals if v]
    ax.pie(w, colors=[c for c, v in zip(cols, vals) if v], labels=labs,
           wedgeprops=dict(width=0.42, edgecolor="white"), startangle=90,
           textprops=dict(fontsize=7.5))
    ax.text(0, 0, "%d\nachados" % sum(vals), ha="center", va="center", fontsize=11,
            fontweight="bold", color="#111827")
    ax.set_title("Achados por severidade", fontsize=9, color="#111827", pad=8)
    fig.tight_layout()
    fig.savefig(donut, transparent=False, facecolor="white")
    plt.close(fig)

    cat_count = collections.Counter(f["cat"] for f in FINDINGS)
    bars = os.path.join(out_dir, "_chart_cat.png")
    fig, ax = plt.subplots(figsize=(6.6, 2.7), dpi=220)
    keys = [c for c, _ in CATS]
    ys = [cat_count.get(k, 0) for k in keys]
    names = [CAT_SHORT[k] for k in keys]
    colors = []
    for k in keys:
        sevs = [f["sev"] for f in FINDINGS if f["cat"] == k]
        pick = "informativa"
        for s in ["critica", "alta", "media", "baixa"]:
            if s in sevs:
                pick = s
                break
        if sevs and all(s == "informativa" for s in sevs):
            pick = "informativa"
        colors.append(SEV_COLORS[pick])
    y = range(len(keys))[::-1]
    ax.barh(list(y), ys, color=colors, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=7.5)
    for yy, v in zip(y, ys):
        ax.text(v + 0.06, yy, str(v), va="center", fontsize=8, color="#374151")
    ax.set_xlim(0, max(ys + [1]) + 0.8)
    ax.set_xticks(range(0, max(ys + [1]) + 1))
    ax.tick_params(axis="x", labelsize=7)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title("Achados por categoria mapeada para esta stack", fontsize=9, color="#111827", pad=8)
    fig.tight_layout()
    fig.savefig(bars, facecolor="white")
    plt.close(fig)
    return donut, bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "relatorio-auditoria-seguranca.pdf"))
    a = ap.parse_args()
    os.makedirs(HERE, exist_ok=True)

    # build the story in a helper module-style sequence
    from build_pdf import build  # noqa: E402  (mesmo diretorio)
    build(a.out, HERE, FINDINGS, STRENGTHS, WEAKNESSES, RECS, CATS, CAT_SHORT,
          SEV_COLORS, SEV_LABEL, REPORT_TITLE, PROJECT, DATE, make_issue, charts, wrap, esc)


if __name__ == "__main__":
    main()
