# Experimento real: Uniswap V2 getAmountOut em LIN

## Fonte executada

- Repositório: https://github.com/Uniswap/v2-periphery
- Commit clonado: ed24991304291297c3b4a52818d02f46a17aa9a2
- Arquivo: contracts/libraries/UniswapV2Library.sol
- Função: getAmountOut(uint amountIn, uint reserveIn, uint reserveOut)
- Compilador da referência: Solidity 0.6.6+commit.6c089d02
- Referência de execução: bytecode Solidity compilado e executado em EVM

O transpiler é intencionalmente limitado à forma exata da função. Ele verifica
as quatro operações do upstream (997, 1000, numerator e denominator) antes de
emitir LIN; se a forma mudar, ele falha em vez de gerar uma tradução
silenciosamente diferente.

## Comandos

    python3 experiments/uniswap_v2/transpile_get_amount_out.py \
      --repo ../uniswap-v2-periphery \
      --output experiments/uniswap_v2/get_amount_out.lin

    make -C transpile/c c0
    make -C transpile/c xver
    node evm-runner/compare_uniswap.js
    node evm-runner/run_u256_adapter.js

## Resultado observado

    VALID_VECTORS=132
    VALID_PARITY=PASS
    LIN_C0_PROFILE=vmfull (C11, zig=false)
    LIN_STEPS=34
    EVM_GAS_AVG=930.00
    INVALID_INPUT=solidity_REVERT,lin_sentinel=0
    PRODUCTION_SCALAR_SCALE=BLOCKED_UINT256
    PRODUCTION_SOLIDITY_VALUE=1662497915624478906
    PRODUCTION_LIN_VALUE=0
    PRODUCTION_U256_VALUE=1662497915624478906
    PRODUCTION_U256_PARITY=PASS
    PRODUCTION_U256_STEPS_PER_LIMB=234521
    RECEIPT=PASS
    RECEIPT_ROOT=sha256:a7b55851551ab3f97d6d0a8a379595ceeb99b8fec4442eb492cdb1f8fee36813
    RECEIPT_RESULT=16624
    RECEIPT_STEPS=14
    RECEIPT_SP=1

Os 132 vetores válidos incluem os casos do repositório (2,100,100 -> 1),
o vetor canônico (10000,50000,100000 -> 16624) e 128 vetores determinísticos
gerados pelo runner. Todos deram o mesmo resultado no bytecode Solidity, no
LIN executado pelo host C11 sem Zig e no oráculo inteiro independente.

O recibo demonstrado é do núcleo aritmético puro. A raiz foi recomputada
independentemente em JavaScript a partir de source, env, code_sha256, resultado,
passos e profundidade da pilha.

## Adaptação uint256 executada

O arquivo `u256_get_amount_out.lin` usa 16 limbs little-endian de 16 bits.
Cada entrada chega pela ABI de teste como quatro palavras `u64` brutas,
transportadas como `i64` com a mesma representação de bits; isso permite
transportar valores acima de `2^63-1` sem convertê-los para signed arithmetic.
O resultado é lido em 16 chamadas, uma por limb, e remontado em JavaScript.

Essa implementação usa multiplicação schoolbook e divisão binária longa, sem
depender de divisão escalar do VM. Ela detecta overflow antes de aceitar a
cotação. Os códigos de rejeição são `-1` para entrada zero e `-2` para
overflow; zero continua sendo um resultado válido e, portanto, não pode ser
usado como sentinela.

O runner `run_u256_adapter.js` passou estes casos: o vetor pequeno do upstream,
o vetor de produção de 18 casas decimais, um vetor com palavra alta não-zero,
entrada zero e overflow. O runner principal também comparou o vetor de
produção diretamente contra o bytecode Solidity na EVM:

    PRODUCTION_SOLIDITY_VALUE=1662497915624478906
    PRODUCTION_U256_VALUE=1662497915624478906
    PRODUCTION_U256_PARITY=PASS

## ABI C11 de execução única

O próximo bloqueador do adaptador foi removido no branch: o kernel
`examples/defi_settlement_proof/u256_settlement_engine.lin` recebe os três
`uint256` como 12 palavras brutas e devolve o status na pilha. O host C11
captura o primeiro array local de 16 limbs dentro da mesma chamada da LinVM e
reconstrói os 32 bytes big-endian. A imagem congelada fica em
`examples/defi_settlement_proof/u256_settlement_engine.linbc`.

O comando de reprodução é:

    make -C transpile/c u256
    python3 examples/defi_settlement_proof/test_u256_host.py

Resultado observado no seed `20260904`:

    U256_SINGLE_EXECUTION=PASS
    VECTORS=1000
    VALID=500
    INVALID_ZERO=3
    OVERFLOW=497

O vetor de produção também passou bit a bit no wrapper de execução única:

    status=0
    amount_out=1662497915624478906
    steps=236235
    receipt_sha256=sha256:ab99535ccc93e52cf689a5053f1985bc94d7ca9d540017ad920626afd7608a0a
    execution=single_vm_call

O host foi compilado com GCC ASan/UBSan e os mesmos 1.000 vetores passaram
sem erro de memória ou undefined behavior. Para cada vetor, o host também
emite `program_sha256`, `loader_digest`, `input_sha256` e `receipt_sha256`.
O harness recalcula esses campos independentemente a partir dos bytes da
imagem, dos 96 bytes de entrada, do status, da saída e dos passos. O receipt
existente do piloto escalar permanece compatível e separado dessa codificação
U256.

## Conclusão técnica

O LIN já mostra uma vantagem concreta para a fatia escalar: a mesma cotação
pode ser executada sem Zig, com contagem determinística de passos e uma prova
criptográfica reprodutível. Isso ainda não prova redução de gás, proteção contra
MEV, segurança do protocolo ou desempenho superior a Solidity/C/Rust.

O primeiro bloqueador foi resolvido no protótipo: a rota `u256` reproduz o
valor de produção bit a bit. A rota escalar original continua deliberadamente
marcada como `BLOCKED_UINT256` e retorna 0 nesse vetor. A semântica de erro do
adaptador já não confunde erro com resultado zero. A ABI C11 nova remove a
necessidade de 16 chamadas separadas; o resultado multiword é capturado em uma
única execução da LinVM.

## Próximo passo de implementação

O próximo trabalho para produção é medir o caminho completo contra o baseline
C/Rust e conectar o receipt a um verificador externo de serviço. O critério de
aceitação é preservar o resultado acima, os 132 vetores Solidity/EVM já
aprovados, os códigos de overflow, a execução única e a verificação
independente do receipt. O passo a passo está em `IMPLEMENTATION.md`.
