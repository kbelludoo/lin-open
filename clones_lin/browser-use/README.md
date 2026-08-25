# Browser-Use em LIN (L1c / L2w)

Reescrita da arquitetura do **Browser-Use** em **LIN** (AI-Native compact language & unified workflow IR).

---

## 📁 Estrutura dos Módulos

| Arquivo | Descrição |
| :--- | :--- |
| [`types.lin`](types.lin) | Construtores e modelos de dados (`TabInfo`, `PageInfo`, `BrowserState`, `ActionResult`, `Action`). |
| [`security.lin`](security.lin) | Validador de domínio (`allowed_domains`, `prohibited_domains`) e sanitização de URLs. |
| [`cdp.lin`](cdp.lin) | Mensagens JSON-RPC e builders de comandos do Chrome DevTools Protocol. |
| [`session.lin`](session.lin) | Gerenciador de ciclo de vida do browser, tracking de abas ativas e sessões. |
| [`dom.lin`](dom.lin) | Serializador da árvore DOM e extrator de elementos interagíveis. |
| [`actions.lin`](actions.lin) | Construtores e despachantes de ações (`click`, `input`, `scroll`, `send_keys`, `extract`). |
| [`workflow.lin`](workflow.lin) | DAG em `~workflow` declarando o fluxo autônomo do agente de navegação. |
| [`browser.lin`](browser.lin) | Ponto de entrada unificado com a API pública do browser. |

---

## ⚡ Compilação Multi-Target

Utilizando o compilador nativo LIN (`/home/k/Downloads/lin-master/`):

```bash
# Compilar para TypeScript
node /home/k/Downloads/lin-master/bin/lin.mjs compile lin/browser.lin --target ts -o dist/browser.ts

# Compilar para Python
node /home/k/Downloads/lin-master/bin/lin.mjs compile lin/browser.lin --target py -o dist/browser.py

# Compilar para Rust
node /home/k/Downloads/lin-master/bin/lin.mjs compile lin/browser.lin --target rust -o dist/browser.rs

# Compilar para Go
node /home/k/Downloads/lin-master/bin/lin.mjs compile lin/browser.lin --target go -o dist/browser.go
```
