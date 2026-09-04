# Como transformar esta prova em um executor de liquidação

Este é o procedimento exato para continuar o experimento até uma API
auditável. O ponto de partida já está no workspace:

- upstream: `../uniswap-v2-periphery`
- snapshot LIN: `.`
- comparação Solidity/EVM: `evm-runner/compare_uniswap.js`
- adaptador `uint256`: `u256_get_amount_out.lin`

## 1. Reproduzir o resultado atual

```bash
cd /workspace/scratch/ef3df4f50f2b/lin-open
git clone https://github.com/Uniswap/v2-periphery ../uniswap-v2-periphery
python3 experiments/uniswap_v2/transpile_get_amount_out.py \
  --repo ../uniswap-v2-periphery \
  --output experiments/uniswap_v2/get_amount_out.lin
make -C transpile/c c0
make -C transpile/c xver
cd evm-runner && npm install && cd ..
node evm-runner/compare_uniswap.js
node evm-runner/run_u256_adapter.js
```

O teste de aceitação imediato é:

```text
PRODUCTION_SOLIDITY_VALUE=1662497915624478906
PRODUCTION_U256_VALUE=1662497915624478906
PRODUCTION_U256_PARITY=PASS
```

## 2. Fixar a semântica Solidity

A tradução deve conservar esta ordem e estes erros:

```text
require(amountIn > 0)
require(reserveIn > 0 && reserveOut > 0)
amountInWithFee = amountIn * 997
numerator = amountInWithFee * reserveOut
denominator = reserveIn * 1000 + amountInWithFee
amountOut = numerator / denominator
```

Em cada operação `u256`, retornar `(ok, value)` e nunca usar zero como erro:

```text
OK = 0
ERR_INPUT = 1
ERR_OVERFLOW = 2
ERR_DIV_ZERO = 3
```

Zero pode ser uma cotação legítima. Portanto o resultado externo precisa conter
`status` separado do valor.

## 3. Implementar o kernel `u256`

O protótipo usa 16 limbs little-endian de 16 bits porque o host C0 atual tem
apenas oito slots de array e o produto de dois limbs cabe com folga em `i64`:

```text
u256 = limb[0] + limb[1] * 2^16 + ... + limb[15] * 2^240
```

Implemente estes cinco blocos, nesta ordem:

1. `from_words`: quatro palavras brutas de 64 bits para 16 limbs.
2. `mul_small`: multiplicação por `997` ou `1000`, carregando base `2^16` e
   rejeitando carry após o limb 15.
3. `add`: soma limb a limb e rejeita carry final.
4. `mul`: multiplicação schoolbook de 16x16 para 32 limbs; rejeitar qualquer
   limb 16..31 não-zero quando o Solidity exigiria overflow.
5. `div`: divisão binária longa de 256 bits; em cada bit, deslocar o resto,
   comparar sem sinal e subtrair o denominador quando necessário.

O arquivo `u256_get_amount_out.lin` já contém uma implementação executável
desses blocos e serve como golden funcional. A função atual é um adaptador de
teste:

```text
get_amount_out_u256_limb(
  amount[4], reserveIn[4], reserveOut[4], outLimb
) -> limb_or_negative_status
```

Ela deve ser substituída por uma chamada nativa que devolva status e os 32
bytes do resultado em uma única execução.

## 4. Trocar a ABI de experimento por ABI de produção

Hoje o runner chama o LIN 16 vezes para recuperar os 16 limbs. Para produção,
adicione uma destas duas interfaces ao host:

```text
settle_u256(amount32, reserveIn32, reserveOut32)
  -> { status: u8, amountOut32: bytes32 }
```

ou uma função LIN que escreva o resultado em uma região de saída fixa. A
primeira opção é menor e mais simples para o C0 atual. O host deve:

- decodificar exatamente 96 bytes de entrada;
- rejeitar comprimento diferente de 96;
- executar o mesmo código LIN uma vez;
- devolver exatamente 1 byte de status + 32 bytes de `amountOut`;
- codificar todos os inteiros como unsigned big-endian na fronteira da API;
- manter a representação interna little-endian somente dentro do kernel.

Não converta `uint256` para `double`, `Number` ou `int64` em nenhum ponto do
caminho de liquidação.

## 5. Gerar receipt verificável

O receipt de produção precisa incluir, no domínio hash, pelo menos:

```text
domain = "lin:settlement:v1"
program_sha256
input_sha256(amount32 || reserveIn32 || reserveOut32)
status
amountOut32
steps
```

Serialize os campos com comprimentos fixos antes de aplicar SHA-256. Depois
recalcule a raiz em um verificador independente em JavaScript, Rust ou Go. O
verificador deve rejeitar:

- código do programa diferente;
- qualquer byte de entrada alterado;
- status alterado;
- output alterado;
- contagem de passos alterada.

O receipt atual de `lin_c_receipt` prova apenas a expressão escalar de teste;
ele não deve ser apresentado como prova da execução `uint256` até receber a
codificação acima.

## 6. Testes obrigatórios antes de chamar de produção

Execute sempre contra o bytecode Solidity e um oráculo BigInt independente:

| Caso | Resultado esperado |
|---|---:|
| `(2, 100, 100)` | `1` |
| `(10000, 50000, 100000)` | `16624` |
| `(1e18, 5e18, 10e18)` | `1662497915624478906` |
| `amountIn = 0` | `ERR_INPUT` e revert Solidity |
| produto acima de `2^256-1` | `ERR_OVERFLOW` e revert Solidity |
| resultado matemático zero | `status=OK`, `amountOut=0` |

Também rode pelo menos 1.000 vetores aleatórios `uint256` com classificação
separada entre casos válidos, overflow e divisão inválida. Só aceite parity
quando o status e os 32 bytes do output forem iguais.

## 7. Critério comercial realista

Depois dos testes, medir custo e latência do caminho completo: decodificação,
execução, receipt e verificação. A vantagem demonstrada hoje é determinismo,
reprodutibilidade e execução sem Zig no host C11. Ainda não foi demonstrada
redução de gás on-chain, resistência a MEV, segurança econômica ou throughput
superior a Rust/C. Essas alegações só podem entrar na oferta após benchmarks e
auditoria independentes.
