# Especificação Técnica — Nível Piloto do LIN

**Documento:** LIN-PILOT-VERIFIER-FUZZ-001  
**Status:** proposta implementável — não autoriza produção  
**Escopo:** settlement AMM determinístico em LINBC1, LinVM C11 e evidências verificáveis  
**Baseline:** commit `99130e89288ca1e3d847a887d2733f1e7cdee14d`

---

## 1. Objetivo

O Nível Piloto deve transformar o protótipo atual em um pacote reproduzível para testes com um cliente real, sem fazer alegações de segurança absoluta. O piloto precisa demonstrar quatro propriedades separadas: o bytecode emitido é reproduzível; a execução é determinística; os recibos são serializados e verificados independentemente; e entradas, imagens e recibos malformados são rejeitados de maneira fail-closed.

O piloto não deve alegar prova de correção universal, não-repúdio jurídico, zero-knowledge, imunidade total a falhas de memória ou equivalência de produção com uma blockchain. Essas propriedades exigiriam controles adicionais fora deste escopo.

> **Critério central:** nenhum resultado deve ser aceito porque o mesmo programa que o produziu também o declarou válido. O verificador independente deve possuir implementação, caminho de execução e testes próprios.

---

## 2. Critérios de entrada

O piloto só pode começar quando o repositório possuir uma imagem LINBC1 determinística, um loader fail-closed e uma função de settlement com contrato de entradas e saídas definido. A imagem deve ser emitida em checkout limpo e o hash deve estar registrado em um manifesto versionado.

| Pré-condição | Evidência obrigatória |
| --- | --- |
| C0 aceita o módulo | Saída `info` com todas as funções do piloto em `status=OK` |
| Emissão determinística | Duas emissões em ambientes limpos com `cmp` byte a byte |
| Loader funcional | Execução dos vetores dourados via `lin_bc1_run` |
| Sem dependência operacional de Zig | Build e execução com Zig fora do `PATH` |
| Hash de imagem | SHA-256 bruto do arquivo e digest interno do loader documentados separadamente |
| Oráculo independente | Implementação de referência em Python ou C, sem reutilizar o lowerer LIN |
| Estado do repositório | Commit, árvore de arquivos e manifesto registrados |

---

## 3. Modelo de ameaça

O piloto deve considerar um operador que tente alterar a imagem, os argumentos, a saída, os passos, o status, uma folha, um irmão Merkle ou a raiz. Também deve considerar truncamento, bytes extras, funções inexistentes, aridade incorreta, inteiros fora do intervalo, repetição de recibos e reuso de uma imagem antiga.

O piloto não pretende resolver, sem componentes adicionais, um operador que controla simultaneamente o executor e o verificador antes da publicação do compromisso, um atacante que forja a identidade do operador ou um comprometimento da chave de assinatura. Para esses casos, o sistema precisa de assinatura digital, rotação de chaves, controle de acesso e cadeia de custódia.

| Ativo | Ataque | Controles do piloto |
| --- | --- | --- |
| Imagem LINBC1 | substituição ou corrupção | SHA-256, manifesto e loader fail-closed |
| Registro de execução | alteração de entrada/saída/status | serialização canônica e hash da folha |
| Bloco Merkle | alteração de folha, irmão ou raiz | recomputação independente do caminho |
| Execução | função ou aridade incorreta | resolução explícita de função e contrato de argumentos |
| Disponibilidade | folha ausente ou lote incompleto | identificador de bloco, cardinalidade e política de fechamento |
| Repetição | replay de recibo antigo | `run_id`, `image_digest`, sequência e janela temporal do lote |
| Autoria | operador negar publicação | assinatura do manifesto e dos metadados, fora do hash puro |

---

## 4. Contrato do settlement

A função de negócio do piloto será:

```lin
settle_swap(amount_in, reserve_in, reserve_out, min_out) -> int64
```

Para entradas positivas e válidas, o resultado esperado é o cálculo exact-input com taxa de 0,3%, usando a representação inteira definida pelo módulo LIN. Se o resultado ficar abaixo de `min_out`, a função retorna `-1`. Entradas inválidas e denominadores não positivos devem ser tratados explicitamente e cobertos pelos vetores.

O oráculo independente deve implementar a mesma semântica de forma separada. Não deve importar ou chamar o parser, o lowerer, o executor ou a biblioteca de hashing do LIN. A comparação deve considerar valor, status e, quando aplicável, classe de erro.

---

## 5. Formato canônico do recibo (112 Bytes)

O registro de folha deve ser binário, de tamanho fixo e independente de padding de `struct`. A serialização deve escrever cada campo byte a byte em little-endian. O tamanho normativo corrigido é **112 bytes**.

| Offset | Tamanho | Campo | Codificação |
| --- | --- | --- | --- |
| 0 | 4 | `schema_id` | ASCII `LCR1` |
| 4 | 1 | `schema_version` | `u8`, valor `1` |
| 5 | 1 | `profile` | `u8`, valor `1` para LINVM-1 |
| 6 | 2 | `reserved` | zero obrigatório |
| 8 | 32 | `image_digest` | SHA-256 do arquivo LINBC1 ou domínio explicitamente definido |
| 40 | 8 | `run_id` | `u64` little-endian |
| 48 | 8 | `tx_id` | `u64` little-endian |
| 56 | 8 | `amount_in` | `i64` little-endian, intervalo validado |
| 64 | 8 | `reserve_in` | `i64` little-endian |
| 72 | 8 | `reserve_out` | `i64` little-endian |
| 80 | 8 | `min_out` | `i64` little-endian |
| 88 | 8 | `out_val` | `i64` little-endian |
| 96 | 8 | `steps` | `u64` little-endian |
| 104 | 8 | `status` | `i64`; `1` aprovado, `-1` rejeitado |

Total de bytes: **112 bytes**. Implementações não devem usar `sizeof(SettlementLeafRecord)` como serialização.

A folha será:
```
leaf_hash = SHA256("LIN:LEAF:1" || canonical_record_112_bytes)
```

O prefixo de domínio evita confusão entre uma folha de recibo e outros objetos hash. Cada nó pai será:
```
parent = SHA256("LIN:NODE:1" || left_hash_32_bytes || right_hash_32_bytes)
```

---

## 6. Verificador independente

O verificador independente deve ser um programa separado em Python 3 puro.
Saída estruturada:
```json
{
  "schema": "LIN_VERIFY_RESULT_1",
  "valid": true,
  "reason": "OK",
  "image_sha256": "sha256:<64 hex>",
  "leaf_sha256": "sha256:<64 hex>",
  "root_sha256": "sha256:<64 hex>",
  "block_id": "<id>",
  "leaf_index": 0,
  "checks": {
    "image_digest": true,
    "canonical_record": true,
    "leaf_digest": true,
    "merkle_path": true,
    "replay_policy": true
  }
}
```

Códigos de rejeição mínimos: `BAD_MAGIC`, `BAD_VERSION`, `BAD_LENGTH`, `BAD_IMAGE_DIGEST`, `BAD_RECORD_ENCODING`, `BAD_INTEGER_RANGE`, `BAD_STATUS`, `BAD_PATH_LENGTH`, `BAD_SIBLING_LENGTH`, `BAD_ROOT`, `REPLAY`, `BLOCK_POLICY` e `SIGNATURE_REQUIRED`.

---

## 7. Fuzzing e Gates

1. Fuzzing do Loader LINBC1: mutações de cabeçalho, tamanho, offsets, tabela de funções, instruções, strings e self-hash.
2. Fuzzing do Executor: 100.000 chamadas contra o oráculo independente.
3. Fuzzing do Verificador: 25.000 recibos/provas mutados com 100% de rejeição.
4. Fuzzing Diferencial: `oráculo Python ↔ lin_bc1_run ↔ host C11`.

---

## 8. CI e Manifesto de Release

Cada release do piloto gera `pilot_evidence_manifest.rulel` com hashes, métricas estatísticas (p50/p95/p99) e commit fixado.
