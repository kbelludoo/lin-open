# [Seguranca] Escritas em caminho fixo dentro da arvore de trabalho e execução de binario escolhido por env/sonda de filesystem

**Labels sugeridas:** `security`, `security/medium`, `c3`
**Categoria da auditoria:** C3 referencia nao validada
**Severidade:** MEDIA
**ID do achado:** F-07

## Problema e por que é explorável

Tres problemas no mesmo ponto: (i) `rebuild` sobrescreve `src/lin.zig` sem checagem de
symlink nem confirmação - arquivo pre-criado como link vira escrita fora da arvore; (ii)
`pick_target` faz o resultado da verificação depender de um caminho absoluto de um
desenvolvedor (`/home/k/...`), entao 'zig' vs 'js' muda de maquina para maquina num projeto
que vende reprodutibilidade bit a bit; (iii) o binario do compilador usado para compilar e
EXECUTAR o código gerado vem de `LIN_ZIG`, sem validação alguma.

## Evidência (arquivo:linha)

`compiler/lin.zig:7549 (lin rebuild escreve src/lin.zig), 7129-7137 (pick_target escreve .lin_ast_check.zig no CWD e prefere /home/k/.local/bin/zig se existir), 7018-7027 (LIN_ZIG decide o `zig run` do codigo gerado por `lin test`)`

```
// compiler/lin.zig:7549 - write em caminho fixo do source tree
const tf = try std.fs.cwd().createFile("src/lin.zig", .{});
// compiler/lin.zig:7129-7137 - alvo escolhido por presenca de arquivo no HOME de um dev
const tmp_file = ".lin_ast_check.zig";
if (std.fs.cwd().createFile(tmp_file, .{})) |f| { ... }
if (std.fs.openFileAbsolute("/home/k/.local/bin/zig", .{})) |zf| { zb = "/home/k/.local/bin/zig"; }
// compiler/lin.zig:7018-7027
var zb: []const u8 = "zig";
if (std.process.getEnvVarOwned(LIA_ALLOC, "LIN_ZIG")) |p| { zb = p; }
return std.process.Child.run(.{ .argv = &.{ zb, "run", "-O", "ReleaseFast", tmp_path }, ... });
```

## Condições de explorabilidade

Requer a vitima rodar `lin rebuild`/`lin test` num diretorio controlado por terceiro
(compartilhado, CI com checkout de PR, workspace de review) ou com ambiente em que o
atacante seta variaveis.

## Impacto

Escrita arbitraria/quebra de arquivo-fonte; resultado de verificação não reproduzivel;
execução de binario arbitrario com o código gerado a partir do input (RCE em fluxo de
review/CI).

## Sugestão de correção

Escrever em caminho explicito via flag (sem default no source tree), abrir com
`O_NOFOLLOW`/verificar symlink, e exigir `--zig <caminho>` (ou resolver so pelo PATH, com
hash esperado) para o compilador externo; substituir a sonda `/home/k/...` por config
explicita.

## Critérios de aceite

- [ ] `lin rebuild` recusa escrever fora do diretorio informado e não toca em caminho fixo.
- [ ] Nenhum caminho absoluto de usuario aparece no código-fonte (grep `/home/` em compiler/*.zig => 0).
- [ ] `lin test` com `LIN_ZIG=/bin/false` falha com erro nomeado, sem executar o que foi gerado.
- [ ] O alvo escolhido (zig/js) sai impresso com a justificativa e e identico em duas maquinas limpas.

---
_Gerado por `docs/security-audit/gen_report.py` (auditoria de 1 de setembro de 2026)._
