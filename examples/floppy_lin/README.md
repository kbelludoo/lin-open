# FloppyURL x LIN // Suíte de Computação Determinística Zero-Byte

Este subsistema combina a tecnologia do **FloppyURL** (hospedagem e distribuição sem servidor através do `#hash` da URL, WebCrypto e RAID-0 de disquetes virtuais) com o motor determinístico do **LIN** (máquina virtual sem heap, bytecode enxuto e atestação Merkle SHA-256).

---

## 1. O Problema que Resolve

1. **Disputas Otimistas sem Instalação (1-Click Fraud Proofs):**
   Em redes L2 / Rollups, quando um sequenciador envia uma transação fraudulenta, provar a fraude exige que os validadores baixem repositórios, compilem código nativo e configurem ambientes locais.
   * **Com FloppyURL + LIN:** O desafiante gera um link único (`#v1;[1/1]...`). Ao clicar, o navegador do usuário carrega o interpretador LinVM em JavaScript/WebCrypto, executa a transação em **microssegundos** e comprova a fraude matematicamente na tela sem depender de nenhum servidor backend.

2. **dApps DeFi Anti-Censura e Imutáveis:**
   Frontends de corretoras descentralizadas (DEX) sofrem com apreensão de domínios (DNS hijacking) e bloqueios de nuvem (AWS/Cloudflare).
   * **Com FloppyURL + LIN:** Toda a lógica de liquidação ($x \cdot y = k$, taxas e slippage) roda localmente no navegador dentro da LinVM, empacotada em uma URL de ~3 KB.

3. **Playground / REPL do LIN 100% Serverless:**
   Permite escrever, depurar e compartilhar sessões completas de código `.lin` simplesmente copiando o endereço do navegador.

---

## 2. Arquitetura Técnica

```text
┌────────────────────────────────────────────────────────┐
│ URL DO NAVEGADOR: #v1;[1/1]<BROTLI_OR_DEFLATE_BASE64>  │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ CAMADA DE TRANSPORTE E ARMAZENAMENTO                   │
│ - Raw DEFLATE (wbits=-15) + Base64URL (RFC 4648 §5)    │
│ - Descompressão nativa: DecompressionStream (zero libs)│
│ - Suporte a RAID-0 multi-setor (v1;[1/N] ... v1;[N/N]) │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ MOTOR DE EXECUÇÃO DETERMINÍSTICO (LinVM WebEngine)     │
│ - Aritmética pura de 64 bits com BigInt (zero heap)    │
│ - Verificação criptográfica FIPS 180-4 via WebCrypto   │
│ - Registro de folha canônico de 72 bytes               │
│ - Detecção instantânea de fraude por desvio Merkle     │
└────────────────────────────────────────────────────────┘
```

---

## 3. Ferramentas Disponíveis

* **`tools/floppy_lin_pack.py`:** Utilitário CLI em Python (stdlib pura) para empacotar código `.lin`, bytecodes `.linbc1` e registros de disputa em URLs FloppyURL.
* **`examples/floppy_lin/floppy_bootloader.html`:** Bootloader de arquivo único, auto-contido, com tema de terminal retro (phosphor green CRT) e áudio de busca de trilha de disquete sintetizado via Web Audio API.
* **`test/test_floppy_lin.py`:** Suíte automatizada de testes cobrindo compressão, descompressão, RAID-0 e compatibilidade com Node.js/navegadores.

---

## 4. Como Executar

### Empacotar uma Prova de Disputa de Fraude em URL
```bash
python3 tools/floppy_lin_pack.py pack \
  --mode dispute \
  --tx-id 1042 \
  --amount-in 10000 \
  --reserve-in 1000000 \
  --reserve-out 2000000 \
  --min-out 19000 \
  --claimed-out 150000
```

### Empacotar um Script LIN para o Playground Web
```bash
python3 tools/floppy_lin_pack.py pack \
  --mode playground \
  --source src/lin_siphash_real.lin
```

### Rodar a Suíte de Testes
```bash
python3 test/test_floppy_lin.py
```
