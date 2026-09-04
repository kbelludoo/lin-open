# LIN Settlement SDK & Validador Independente

Este subdiretório contém o protótipo de engenharia do SDK para o **Caminho 1** (Liquidação LINBC1 + Árvore Merkle SHA-256 de 256 bits).

---

## 1. O que o SDK Faz

- **Execução Confinada:** Dispara swaps diretamente na imagem compilada `settlement_engine.linbc` via `lin_bc1_run`.
- **Serialização Canônica:** Empacota cada resultado em um registro binário imutável de 72 bytes vinculado ao digest do bytecode executado.
- **Agrupamento em Blocos:** Constrói a árvore Merkle SHA-256 (256 bits) sobre blocos de 4 transações e gera as provas de inclusão para cada participante.
- **Auditoria Zero-Trust:** Fornece o script `verify_client.py`, que audita o arquivo exportado em qualquer máquina com Python 3 padrão (sem precisar de Zig, C0, LinVM ou compiladores).

---

## 2. Como Usar

### Exportar um lote de liquidação
```python
from sdk.lin_settlement_sdk import LINSettlementSDK
import json

sdk = LINSettlementSDK()
txs = [
    sdk.execute_swap(2001, 1000, 100000, 200000, 1970),
    sdk.execute_swap(2002, 2500, 100000, 200000, 4800),
    sdk.execute_swap(2003, 5000, 100000, 200000, 9900), # Rejeição de slippage
    sdk.execute_swap(2004, 1200, 150000, 300000, 2300)
]
bundle = sdk.build_block_bundle(block_id=1, swaps=txs)
with open("bundle_block_1.json", "w") as f:
    json.dump(bundle, f, indent=2)
```

### Auditar independentemente (Auditor / Cliente)
```bash
python3 sdk/verify_client.py bundle_block_1.json --expected-image d41fbfe856155828301e0d91248980b25e9b6cf2f9390676f510b46761e55a6f
```
