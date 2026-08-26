# LIN Large Repository Benchmark

**Data:** 2026-08-15
**Repositório:** [Chalarangelo/30-seconds-of-code](https://github.com/Chalarangelo/30-seconds-of-code)
**Objetivo:** Medir o estágio real do LIN em repositório de escala intermediária-grande.

---

## Resultados

### Nível 1 — Representação Compacta

| Métrica | Valor |
|---------|-------|
| Arquivos fonte | 90 |
| Bytes fonte | 215.174 |
| Tokens fonte (est.) | 53.794 |
| Tokens LIN | 10.642 |
| **Redução de tokens** | **80,2%** |
| Bytes LIN | 42.568 |
| Redução de disco | 80,2% |

**Status: PASS** — redução de ~80% supera a meta de 70%.

---

### Nível 2 — Roundtrip / Equivalência

| Métrica | Valor |
|---------|-------|
| Unidades testadas | 179 |
| Pass | 179 |
| Fail | 0 |
| Skip | 0 |
| **Suite rate** | **100%** |
| Hash semântico validado | Sim |
| Comportamento equivalente | Sim |

**Status: PASS** — supera a meta de 95%.

---

### Nível 3 — Compilação Multi-Target

7 linguagens do núcleo validadas por toolchain real:

| Linguagem | PASS | FAIL | SKIP |
|-----------|------|------|------|
| TypeScript | 119 | 0 | 0 |
| JavaScript | 119 | 0 | 0 |
| Python | 119 | 0 | 0 |
| Go | 119 | 0 | 0 |
| Rust | 119 | 0 | 0 |
| C | 119 | 0 | 0 |
| Java | 119 | 0 | 0 |

**Status: PASS** — 7/7 linguagens do núcleo passam, supera a meta de 5+.

---

### Nível 4 — Verificação Semântica

| Capacidade | Status |
|------------|--------|
| Refinement Types | Implementado e compilável do LIN |
| Effect Tracking | Implementado e compilável do LIN |
| Content-Addressed Hash | Implementado e compilável do LIN |
| Actor Supervision | Implementado e compilável do LIN |
| Integração no gate de clone | Em progresso |

**Status: EARLY_IMPLEMENTATION** — módulos existem como `.lin` e compilam, mas ainda não são aplicados automaticamente no pipeline de clone.

---

### Nível 5 — Runtime de Memória

**Status: NOT_PROVEN** — execução in-memory de LIN foi demonstrada para casos pequenos, mas não em benchmark estruturado com estado persistente.

---

### Nível 6 — IA Gerando LIN Diretamente

**Status: EXPERIMENTAL** — ainda não medido sistematicamente contra LLMs.

---

## Score Final

| Área | Score |
|------|-------|
| Representação compacta | ✅ PASS (80,2% redução) |
| Roundtrip / equivalência | ✅ PASS (100%) |
| Multi-target | ✅ PASS (7/7) |
| Verificação semântica | 🟡 EARLY_IMPLEMENTATION |
| Runtime de memória | ❌ NOT_PROVEN |
| IA nativa | 🟡 EXPERIMENTAL |

---

## Conclusão

O LIN demonstrou escala real em um repositório com **90 arquivos, 53k tokens e 179 funções**: **80% de redução de tokens, 100% de equivalência comportamental e 7 linguagens compilando**.

Isso comprova que o LIN funciona como **camada semântica de IA para repositórios grandes**, não apenas para exemplos pequenos.

Próximos marcos críticos:
1. Integrar verificador semântico no gate de clone.
2. Demonstrar runtime de memória com estado persistente.
3. Medir IA gerando LIN diretamente vs gerando Python/TS.
