# Implementação de Keccak-256 na LinVM

**Projeto:** Lin-Audit Ethereum  
**Perfil:** `LIN-ETH-1`  
**Objetivo:** Calcular `Keccak-256` de forma determinística dentro da LinVM sem confundir o algoritmo com `SHA3-256`  
**Status:** Especificação de implementação canônica  

---

## 1. Decisão principal

O Ethereum usa **Keccak-256**, e não o SHA3-256 padronizado pelo NIST. Os dois algoritmos compartilham a permutação Keccak-f[1600], mas usam sufixos de domínio diferentes no padding:

| Algoritmo | Sufixo de domínio | Taxa | Capacidade |
| --- | --- | --- | --- |
| Keccak-256 | `0x01` | 1088 bits / 136 bytes | 512 bits |
| SHA3-256 | `0x06` | 1088 bits / 136 bytes | 512 bits |

Essa diferença de um único sufixo produz digests completamente diferentes. O código deve usar nomes explícitos como `keccak256` e `KECCAK_SUFFIX = 0x01`. O nome `sha3` não deve aparecer na interface pública do verificador.

A documentação oficial do JSON-RPC do Ethereum chama atenção para essa distinção ao descrever `web3_sha3` como Keccak-256, “não o SHA3-256 padronizado”.[1]

---

## 2. Relação com o transaction hash

Para uma transação Ethereum já serializada e assinada, o cálculo do hash é:

```
transaction_hash = Keccak256(raw_signed_transaction_bytes)
```

Para uma transação legacy, `raw_signed_transaction_bytes` é uma lista RLP contendo os campos assinados. Para uma transação tipada, o byte de tipo faz parte da entrada:

```
transaction_hash = Keccak256(transaction_type || rlp(transaction_payload))
```

O byte de tipo não pode ser removido antes do hash. O EIP-2718 define essa composição como um envelope `TransactionType || TransactionPayload`.[2]

A função de Keccak não interpreta campos Ethereum: ela recebe bytes e calcula um digest. A validação RLP e o dispatcher de tipos residem em camadas separadas.

---

## 3. Estado interno

Keccak-f[1600] usa 25 lanes de 64 bits, organizadas em uma matriz de cinco por cinco. O layout recomendado é linearizar a coordenada `(x, y)` com:

```
index(x, y) = x + 5*y
```

O estado é representado como:

```
A[25] : u64
```

Como a LinVM atual trabalha com palavras `i64`, cada lane pode ser armazenada em um slot de 64 bits e tratada como representação binária não assinada. As operações de adição não são necessárias para Keccak; as operações centrais são XOR, rotação circular, AND e complemento bit a bit.

O perfil `LIN-ETH-1` define as seguintes operações primitivas:

```
xor64(a, b)        -> u64
and64(a, b)        -> u64
not64(a)           -> u64
rotl64(a, n)       -> u64
load_u64_le(buf,i) -> u64
store_u64_le(buf,i,v)
```

Nenhuma dessas funções depende de conversão decimal ou de comparação signed para determinar o resultado dos bits.

---

## 4. Constantes fixas

A implementação congela uma única tabela de deslocamentos de Rho e uma única tabela de constantes Iota.

Com o layout linearizado `index(x,y) = x + 5*y`, a lista plana de Rho é:

```
rho[25] = {
   0,  1, 62, 28, 27,
  36, 44,  6, 55, 20,
   3, 10, 43, 25, 39,
  41, 45, 15, 21,  8,
  18,  2, 61, 56, 14
}
```

As constantes Iota para as 24 rodadas são:

```
RC[24] = {
  0x0000000000000001,
  0x0000000000008082,
  0x800000000000808A,
  0x8000000080008000,
  0x000000000000808B,
  0x0000000080000001,
  0x8000000080008081,
  0x8000000000008009,
  0x000000000000008A,
  0x0000000000000088,
  0x0000000080008009,
  0x000000008000000A,
  0x000000008000808B,
  0x800000000000008B,
  0x8000000000008089,
  0x8000000000008003,
  0x8000000000008002,
  0x8000000000000080,
  0x000000000000800A,
  0x800000008000000A,
  0x8000000080008081,
  0x8000000000008080,
  0x0000000080000001,
  0x8000000080008008
}
```

Essas constantes devem ser armazenadas como dados imutáveis da imagem Lin, entrando no digest da imagem LINBC1.

---

## 5. Rotação circular de 64 bits

A rotação para a esquerda é:

```
rotl64(x, n) = (x << n) XOR (x >> (64-n))
```

Pseudocódigo semântico com tratamento explícito de `n = 0`:

```
function rotl64(x, n):
    n = n & 63
    if n == 0:
        return x
    return (x << n) | (x >> (64 - n))
```

Na LinVM, o operador de combinação é o OR bit a bit (ou derivado: `or64(a, b) = a XOR b XOR (a AND b)`).

Casos de teste obrigatórios para `rotl64`:

| Entrada | Rotação | Verificação |
| --- | --- | --- |
| `0` | `0` | `0` |
| `1` | `0` | `1` |
| `1` | `1` | `2` |
| `0x8000000000000000` | `1` | `1` |
| `1` | `63` | `0x8000000000000000` |
| qualquer valor | `64` | igual à rotação `0` |
| qualquer valor | `65` | igual à rotação `1` |

---

## 6. Permutação Keccak-f[1600]

A permutação consiste em 24 rodadas sequenciais aplicando Theta, Rho, Pi, Chi e Iota:

```
function keccak_f1600(A[25]):
    for round in 0..23:
        # Theta: paridade e correção de coluna
        for x in 0..4:
            C[x] = A[x] XOR A[x+5] XOR A[x+10] XOR A[x+15] XOR A[x+20]

        for x in 0..4:
            D[x] = C[(x+4) mod 5] XOR rotl64(C[(x+1) mod 5], 1)

        for y in 0..4:
            for x in 0..4:
                A[x+5*y] = A[x+5*y] XOR D[x]

        # Rho e Pi: rotação e transposição
        for y in 0..4:
            for x in 0..4:
                B[y + 5*((2*x + 3*y) mod 5)] = rotl64(A[x+5*y], rho[x+5*y])

        # Chi: combinação não-linear por linha
        for y in 0..4:
            for x in 0..4:
                A[x+5*y] = B[x+5*y] XOR ((NOT B[((x+1) mod 5)+5*y]) AND B[((x+2) mod 5)+5*y])

        # Iota: constante de rodada
        A[0] = A[0] XOR RC[round]
```

---

## 7. Absorção e Padding Keccak

Keccak-256 usa taxa $r = 136$ bytes. O estado inicia zerado. A mensagem é dividida em blocos de até 136 bytes.

Para cada bloco completo de 136 bytes:
1. Carregar 17 lanes little-endian;
2. Fazer XOR dessas lanes nas primeiras 17 lanes do estado;
3. Aplicar `keccak_f1600`.

Para o bloco final, aplica-se o padding `pad10*1` com o sufixo `0x01`:
```
padded = message || 0x01 || zeroes || 0x80
```
Se restar exatamente 1 byte, o último byte combina os dois marcadores: `0x81`. O algoritmo nunca deve usar `0x06` (reservado para SHA3-256).

---

## 8. Absorção Little-Endian

Cada lane de 64 bits é lida a partir de 8 bytes em ordem little-endian:

```
load_u64_le(b, i):
    return b[i+0]       |
           b[i+1] << 8  |
           b[i+2] << 16 |
           b[i+3] << 24 |
           b[i+4] << 32 |
           b[i+5] << 40 |
           b[i+6] << 48 |
           b[i+7] << 56
```

Cada índice `i` deve ser checado antes do acesso para garantir comportamento fail-closed.

---

## 9. Squeeze e Digest Final

Após a absorção e permutação do último bloco, os primeiros 32 bytes das primeiras 4 lanes formam o digest de 256 bits:

```
for i in 0..31:
    digest[i] = byte_little_endian(state[i / 8], i mod 8)
```

---

## 10. Interface Lin e Status Codes

Assinatura conceitual no perfil `LIN-ETH-1`:

```
!rotl64(x: int, n: int) -> int
!keccak_round(state_slot: int, round: int) -> int
!keccak_permute(state_slot: int) -> int
!keccak_absorb_block(state_slot: int, input_slot: int, offset: int) -> int
!keccak256(input_slot: int, input_len: int, output_slot: int) -> int
!verify_tx_hash(input_slot: int, input_len: int, claimed_slot: int) -> int
```

Tabela de status determinístico:

| Status | Significado |
| --- | --- |
| `0` | Hash calculado e igual ao declarado |
| `1` | Hash calculado, mas divergente |
| `2` | Entrada truncada ou acesso fora dos limites |
| `3` | Tamanho acima do limite do perfil |
| `4` | Tipo ou envelope inválido |
| `5` | Erro interno de execução |

---

## 11. Prevenção de SHA3-256 por Construção

1. **Nomenclatura**: Uso restrito de `keccak256`, `KECCAK_RATE_BYTES = 136`, `KECCAK_SUFFIX = 0x01`.
2. **Constante Imutável**: O sufixo `0x01` é congelado na imagem LINBC1, sem aceitar parâmetro de domínio do host.
3. **Vetor de Regressão Obrigatório**:
   - `Keccak-256("") == 0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470`
   - `SHA3-256("") == 0xa7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a` (assegurando `Keccak != SHA3`).

---

## 12. Estrutura em Duas Camadas do Marco 1

| Camada | Escopo | Status |
| :--- | :--- | :--- |
| **M1-A (Entregue)** | Protótipo de referência independente em Python puro, parser RLP, envelopes 0/1/2/3, CLI (`lin_audit_tx.py`), suíte de mutações e CI. | **Concluído e Versionado** |
| **M1-B (A Financiar)** | Portar o núcleo Keccak-256/RLP para LinVM sob o perfil `LIN-ETH-1`, comparação cruzada (LinVM vs. Python vs. C11 vs. Geth/Reth) e expansão do corpus para 10.000 transações públicas da Mainnet. | **Escopo do Grant (Meses 1–2)** |

---

## References

[1]: https://ethereum.org/developers/docs/apis/json-rpc/ "Ethereum JSON-RPC API"  
[2]: https://eips.ethereum.org/EIPS/eip-2718 "EIP-2718: Typed Transaction Envelope"  
[3]: https://keccak.team/keccak_specs_summary.html "The Keccak Function"  
[4]: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf "FIPS 202: SHA-3 Standard"  
[5]: https://ethereum.org/developers/docs/transactions/ "Ethereum Transactions"  
