# [Seguranca] Chave privada de autoridade gerada com permissão 0644 e nome de arquivo default no CWD

**Labels sugeridas:** `security`, `security/high`, `c4`
**Categoria da auditoria:** C4 chaves/segredos
**Severidade:** ALTA
**ID do achado:** F-04

## Problema e por que é explorável

`createFile(path, .{})` usa 0o666 & ~umask => 0644 com a umask padrão: o seed privado de 256
bits fica legivel por qualquer usuario da maquina e por qualquer job/artefato que cole o
diretorio (upload-artifact, `git add -A`, tarball de debug). O próprio repo já sabe fazer
certo (`gate-keygen` usa 0o600, medido: `lin_gate_key.seed` saiu 600), entao e uma
inconsistencia na rota de attest - não falta mecânica, falta aplica-la ali.

## Evidência (arquivo:linha)

`compiler/lin.zig:7643 e 8719 (default "authority.key"), 8038-8044 e 9170-9176 (geracao + createFile sem modo), contraste correto em compiler/lin.zig:15761 (gate-keygen usa .mode = 0o600)`

```
// compiler/lin.zig:7643 - default relativo ao CWD
var key_path: []const u8 = "authority.key";
// compiler/lin.zig:8038-8044 - gera e escreve sem fixar modo
std.crypto.random.bytes(&authority_seed);
_ = try std.fmt.bufPrint(&key_hex_buf, "{s}", .{std.fmt.fmtSliceHexLower(&authority_seed)});
const kfile = try std.fs.cwd().createFile(key_path, .{});
try kfile.writeAll(&key_hex_buf);
// compiler/lin.zig:15761 - a outra rota FAZ o certo
const kf = try std.fs.cwd().createFile(key_out, .{ .truncate = true, .mode = 0o600 });
```

## Condições de explorabilidade

Local: qualquer processo do mesmo host le o seed. Em CI: um `upload-artifact` com caminho
amplo (`**`) pública o arquivo; o .gitignore do repo e allowlist, entao `authority.key` não
seria commitado - mas um `git add -f` ou um bundle da arvore expoe.

## Impacto

Roubo da identidade de assinatura de atestados: o atacante passa a emitir atestados validos
(com F-01, sem nem precisar do verificador da vitima).

## Sugestão de correção

Usar `.mode = 0o600` em todo createFile de material sensivel (8041, 9173), recusar default
`authority.key` se o arquivo já existir e não for modo 0600 (validação de startup), e
imprimir aviso quando o caminho estiver dentro de uma arvore de trabalho.

## Critérios de aceite

- [ ] Apos `attest-issue`, `stat -c %a authority.key` == 600 (hJe não roda porque o arquivo existe antes de mim).
- [ ] Rodar com `--key <arquivo existente 0644>` => erro nomeado 'key file is group/other readable'.
- [ ] grep por `createFile(` em rotas de chave não deixa nenhum call sem `.mode`.
- [ ] Teste de CI: `upload-artifact` com `path: .` falha se houver chave no tree.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
