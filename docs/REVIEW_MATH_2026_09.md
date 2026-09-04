# Revisão Matemática do LIN — fundamentos, invariantes e melhorias (2026-09-03)

> Escopo: leitura integral dos núcleos numéricos — semântica da VM
> (`lin_vm.c`, `lin_common.h`, `docs/LINVM_ISA_V1.rulel`), engine `uint256`
> (`u256_settlement_engine.lin`), receipts (`lin_c_receipt.c`,
> `merkle_sha256_*.c`), biblioteca Uniswap, módulos de cripto e os hashes
> "Merkle" legados. Cada achado vem com a matemática explícita. Prioridades:
> P0 = correção/segurança, P1 = performance, P2 = formalização/evidência.

---

## 0. Sumário executivo (o que importa primeiro)

| # | Achado | Severidade | Tipo |
|---|---|---|---|
| 1 | "Merkle" em `src/lin_binary_merkle_provenance.lin` é **afim e forjável em O(1)** | 🔴 P0 | segurança |
| 2 | `hash_pair`/`verify_merkle_branch_2` (audit_v2) é **hash de 32 bits** (aniversário em ~2¹⁶) | 🔴 P0 | segurança |
| 3 | Referência Uniswap (`src/lin_uniswap_v2_library.lin`) **sem guardas**: wrap silencioso fora do domínio testado | 🟠 P0 | correção |
| 4 | Engine u256 re-executa a divisão **5× por swap** (status + 4 palavras) | 🟠 P1 | performance |
| 5 | Divisão bit-a-bit é **O(bits·limbs)**; Knuth D reduz ~16× | 🟢 P1 | performance |
| 6 | Guardas i64 de `settlement_engine.lin` têm **margem de ~2,5%** até o overflow | 🟠 P2 | correção latente |
| 7 | Semântica `INT64_MIN op -1` quebra a estrutura de anel de Z/2⁶⁴ | 🟡 P2 | semântica |
| 8 | Receipt é **commitment**, não prova de corretude (formalizado) | 🟡 P2 | clareza |
| 9 | `build_merkle_root` com padding por duplicação é ambíguo sem comprometer o nº de folhas | 🟡 P2 | segurança |
| 10 | 34 vetores N-version têm poder estatístico fraco (29% p/ bug de 1%); fuzz 400k é o que sustenta | 🟢 P2 | evidência |

---

## 1. A aritmética é o anel Z/2⁶⁴ — com duas exceções que quebram o anel

A LIN define a semântica numérica como **wrap em i64** (dois complementos). Modelo
matemático correto: o conjunto de valores é o anel comutativo

$$\mathbb{Z}/2^{64}\mathbb{Z},$$

com representantes escolhidos em $[-2^{63},\,2^{63})$. `add`, `sub`, `mul`, `neg`,
`shl` são **homomorfismos de anel** (operações modulares puras). `neg` é
$0 - x \bmod 2^{64}$, logo $\operatorname{neg}(-2^{63}) = -2^{63}$ (fix-point
esperado, pois $-2^{63} \equiv 2^{63} \pmod{2^{64}}$).

**Exceção 1 — `INT64_MIN op -1`.** O quociente matemático $(-2^{63})/(-1) = 2^{63}$
não tem representante em $[-2^{63}, 2^{63})$; a tabela do ISA pinou

$$\texttt{div}(-2^{63},-1) = -2^{63},\qquad \texttt{rem}(-2^{63},-1) = 0.$$

Isto **não é** uma operação do anel (em nenhuma álgebra a divisão de $-2^{63}$ por
$-1$ vale $-2^{63}$); é uma função total escolhida para eliminar UB de C. Consequência
matemática: um auditor que raciocine em Z/2⁶⁴ (ou em Z) é enganado exatamente nesse
ponto. **Sugestão (P2):** transformar `INT64_MIN / -1` em rejeição fail-closed
(`VmDivisionByZero`-like, novo status), ou pelo menos emitir um aviso de spec — a
propriedade "div trunca para zero" passa a ter um contraexemplo explícito que hoje
só aparece escondido em `lin_common.h`.

**Exceção 2 — shifts fora de [0,64).** `vmShift`/`_lia_shl`/`_lia_shr`/`_lia_ushr`
**saturam para 0** quando $b \notin [0,64)$ (confirmado idêntico no Zig `lin.zig:6418`
e no C11 `lin_vm.c`). Matemática: `shr` não é monótono no expoente — `x >> 63` é a
extensão de sinal e `x >> 64 = 0` (descontinuidade). A lei de composição
$(x\ll a)\ll b = x\ll(a+b)$ **falha** na fronteira. É uma escolha definida e
documentada (ISA §4.3), portanto aceitável — mas a recomendação é: os kernels que
usam shift **devem provar** $b \in [0,64)$ (o engine u256 o faz, pois usa
`_lia_ushr(t,16)` e `_lia_shl(1,pos)` com `pos∈[0,15]`).

---

## 2. Engine uint256: correção por construção (invariante de limite)

O engine representa um inteiro de 256 bits em **16 limbs de 16 bits** (base
$b=2^{16}$). O invariante que o torna correto sem tipos de 128 bits é:

> Para toda operação `t = a·k + carry` (ou `t = acc + a·b + carry`) com
> $a,b,\text{acc}\in[0,b-1]$ e $\text{carry}\in[0,b-1]$:
> $$t \le (b-1)^2 + 2(b-1) = b^2 - 1 = 2^{32}-1 < 2^{63}.$$

Ou seja, **todos os intermediários cabem em 32 bits**, com folga de $\approx 2^{31}$
sobre o teto i64. Verificação nos três pontos quentes:

1. **×997:** $65535\cdot 997 + 996 = 65\,339\,391 < 2^{32}$ (o carry máximo é 996,
   ponto fixo de $\lfloor(65535\cdot997+c)/2^{16}\rfloor = c$).
2. **×1000 + fee:** $\le 65535\cdot1000 + 999 + 65535 \approx 6{,}56\times10^{7}$.
3. **schoolbook 16×16→32:** $65535^2 + 65535 + 65535 = 2^{32}-1$, exato no limite.

Detecção de overflow: o produto $P = \text{fee} \times \text{reserve\_out}$ tem até
512 bits (32 limbs). O engine escreve $P$ em `numerator[0..31]` e rejeita com
sentinela `-2` sse $\exists i\in[16,31]:\ \text{numerator}[i]\neq0$, i.e. sse
$P \ge 2^{256}$. Correto (o limite é exato). Um refinamento barato (defesa em
profundidade): a propagação de carry `while (k<32 && carry!=0)` **não asserta** que
`carry==0` ao sair — matematicamente é sempre 0 (pois $P<2^{512}$), mas um `?(carry!=0){^-2;}` torna o contrato explícito e audível.

### 2.1 Complexidade da divisão — e por que Knuth D vale ~16×

A divisão longa binária é: para cada bit de 255 até 0, (a) shift de `remainder`
por 1 (16 limbs), (b) comparação com o denominador (16 limbs), (c) subtração
condicional (16 limbs). Custo por bit $O(\ell)$ com $\ell=16$; total

$$T_{\text{div}} = 256 \times O(\ell) = O(b \cdot \ell) = 4096\ \text{operações-limite}.$$

A divisão domina o kernel (≈95% dos 234.561 passos de um settle; a multiplicação
schoolbook custa só $16\times16=256$ acumuladores). **Knuth, *TAOCP* §4.3.1,
Algoritmo D** (radix $2^{16}$): normalização $O(\ell)$, depois $\ell=16$ iterações de
dígito-quociente, cada uma com multiply–subtract de $O(\ell)$:

$$T_{\text{Knuth-D}} = O(\ell^2) = 256\ \text{operações-limite},$$

redução teórica de **~16×** no corpo da divisão. Projeção nos passos medidos
(234.561 → ~24.000–40.000, ganho ~6–10×, limitado pela normalização e pelo restante
fixo). O único obstáculo: a estimativa do dígito-quociente em Knuth D precisa de uma
divisão 32÷16 por iteração — pode ser substituída por **recíproco de 1 limb
pré-computado** (mantendo o engine livre de `/` nativo) ou por um
**restoring division em radix 2¹⁶** com correção por comparação (sem divisão).

### 2.2 A redundância 5× (o "single-shot" já é correto, só não é usado)

`run_lin_u256` (e `lin_settle_u256_single_shot` no host C) chamam `settle_u256_word`
**5 vezes por swap**: `out_word_idx=-1` (status) + `0..3` (palavras). Cada chamada
**re-executa a divisão inteira** (o `?(out_word_idx==-1){^1;}` vem *depois* do laço
de divisão). Verificação pelos passos medidos: status = 234.525 passos, cada palavra
= 234.561 → **234.525 + 4×234.561 ≈ 1.172.769 passos/swap** (coerente com os
58.118.630/50 ≈ 1.162.373 passos/swap do lote mainnet; a diferença ~1% vem da
dependência de dados no laço de carry). Conclusão quantitativa:

| Interface | passos/swap | tempo/10k (projeção linear) |
|---|---|---|
| atual (5×) | 1,17M | ~93 s (medido) |
| single-shot (1×) | ~0,23M | ~19–23 s |
| single-shot + Knuth D | ~0,04M | ~3–4 s |

**O host C já expõe `lin_settle_u256_single_shot`**; falta expor no harness (ler as 4
palavras de UMA execução, não re-executar 4×).

---

## 3. Receipts e Merkle: o que é prova e o que é forjável

### 3.1 Commitment vs. prova — formalização

O receipt canônico é

$$\texttt{root}=\operatorname{node}(\operatorname{node}(L_s,L_e),\operatorname{node}(L_c,L_x))$$

com folhas $L_s=\mathrm{SHA256}(\text{"lin:xver:source:"}\|src)$ etc., e
$L_x=\mathrm{SHA256}(\text{"lin:xver:exec:"}\|\text{result}{:}\text{steps}{:}sp)$.
Isto é um **esquema de comprometimento** (binding = resistência a colisão de SHA-256),
**não** um sistema de prova de conhecimento. Formalmente:

- **Integridade (vale):** qualquer alteração em um dos 6 campos
  $(src,env,code,result,steps,sp)$ exige colisão/2ª-pré-imagem de SHA-256 para
  manter a raiz.
- **Corretude (NÃO vale pelo receipt sozinho):** um produtor malicioso pode
  comprometer $(code',env',result')$ com $result'\neq V(code',env')$; a raiz é
  auto-consistente. A corretude vem **só** da re-execução independente (que o repo
  faz via N-version Zig×C11 e oráculos Python).

**Resultado positivo (determinismo ⇒ comprometimento agregado = comprometimento do
traço):** como $V:(code,env)\to(result,steps,sp)$ é determinística, o traço completo
$\tau$ é função de $(code,env)$; comprometer $(code,env)$ já fixa $\tau$, e a
inclusão de $(result,steps,sp)$ é redundância que permite **verificar sem reter o
traço**. Não há perda de segurança por não comprometer o traço inteiro (a menos de
colisão de SHA-256). Este argumento merece entrar na spec formal.

### 3.2 Separação de domínio — correta

Folhas usam prefixo `lin:xver:source:` / `...env:` / `...code:` / `...exec:` e nós
usam `node:` (ou `LIN:LEAF:1`/`LIN:NODE:1` no LCR2/LCR4). Como os conjuntos de
pré-imagens válidas de folha e de nó são **disjuntos** (prefixos distintos), uma
folha não pode ser reinterpretada como nó interno — elimina a ambiguidade clássica
de Merkle–Damgård. ✓ Não há o que corrigir; há o que **provar na spec**.

### 3.3 `build_merkle_root` com padding por duplicação — ambíguo

`build_merkle_root` (usado no lote de 50) faz `right = curr[i+1] if exists else
curr[i]` (duplica o último). A raiz de uma árvore de $n$ folhas fica **igual** à de
uma árvore de $2n$ folhas (cada folha duplicada): $H(H(L_1,L_2))$ ambíguo entre
"2 folhas" e "4 folhas $(L_1,L_1,L_2,L_2)$". Sem comprometer o **tamanho** $n$, o
verificador não distingue árvores de cardinalidades diferentes. **Correção (P2):**
comprometer $(\text{leaf\_count},\text{height})$ no root, ou usar o esquema
"0/1-é-nó-terminal" (RFC 6962). O caminho LCR2 (B=4 fixo) está isento.

### 3.4 Os dois "Merkle/hash" que NÃO são criptográficos (P0)

**(a)** `src/lin_binary_merkle_provenance.lin`:

$$\text{parent}(l,r)=65537\,l + 1009\,r + 42 \pmod{2^{64}}.$$

É um mapa **afim** $(\mathbb{Z}/2^{64})^2 \to \mathbb{Z}/2^{64}$ (128→64 bits).
Forjável em tempo constante: dado $(l,r)$, para qualquer $\Delta$,

$$l'=l+1009\,\Delta,\qquad r'=r-65537\,\Delta \implies \text{parent}(l',r')=\text{parent}(l,r).$$

A folha $\text{leaf}=104729\,t + 31\,c + 17$ tem o mesmo defeito. Chamar isto de
"Merkle" é incorreto no sentido criptográfico (é uma **fingerprint linear**). Ou
renomear, ou trocar por SHA-256 (o host C já tem `lin_sha256`).

**(b)** `hash_pair` / `verify_merkle_branch_2` (`settlement_engine*.lin`, audit_v2):

$$v = (l\cdot 2146129197)\oplus(r\cdot 2221712011),\quad v=(v\oplus(v\gg16))\cdot 16843009,\quad
\text{retorna } v \& 0xFFFFFFFF.$$

Constantes 2146129197 e 2221712011 são **compostas** (fatoradas); 16843009 =
$0x01010101$. A máscara final `& 0xFFFFFFFF` limita o domínio a **32 bits**:
colisão de aniversário em $n\approx\sqrt{2\ln 2}\cdot2^{16}\approx 7{,}7\times10^4$
entradas; 2ª-pré-imagem em $2^{32}$ tentativas (GPU: segundos). Inadequado para
qualquer alegação de "prova criptográfica". **Ação:** migrar `verify_merkle_branch_2`
para o SHA-256 com domínios (`LIN:LEAF:1`/`LIN:NODE:1`) já usado no caminho novo,
ou renomear explicitamente para `checksum`.

---

## 4. Uniswap: domínios seguros vs. wrap silencioso

### 4.1 Os guardas i64 de `settlement_engine.lin` têm margem de ~2,5%

Guardas: `amount_in ≤ 10⁶`, `reserve_in ≤ 9×10¹⁵`, `reserve_out ≤ 9×10⁹`.
Limites exatos dos intermediários:

$$\text{num} = (a\cdot997)\,r_o \le (10^6\cdot997)(9\cdot10^9)=8{,}973\times10^{18} < 2^{63}=9{,}223\times10^{18}\ (\text{folga }2{,}7\%)$$
$$\text{den} = r_i\cdot1000 + a\cdot997 \le 9\times10^{18}+9{,}97\times10^8 < 2^{63}\ (\text{folga }2{,}4\%).$$

Ou seja: a prova de não-overflow depende de uma margem de **~2,5%**. Qualquer bump
futuro em `reserve_out` (ex.: 10¹⁰) estoura silenciosamente. **Sugestão:** derivar os
tectos como função das desigualdades (documentar a fator de segurança) ou — melhor —
usar **detecção de carry** (como o u256) em vez de guardas *a priori*.

### 4.2 A referência "oficial" não tem guarda nenhuma (P0)

`src/lin_uniswap_v2_library.lin::get_amount_out` faz
`amount_in*997*reserve_out/(reserve_in*1000+amount_in*997)` **sem validação**; com
wrap i64, qualquer entrada fora do domínio testado produz **resultado corrompido
silenciosamente** (sem sentinela). O harness racionalista só testa
$amount\_in\le10^6$, $reserve\le10^9$ — então o bug vive exatamente fora do que é
provado. O engine u256 (exato, com sentinelas) é o caminho correto; a referência i64
deveria ou importar os guardas de `settlement_engine.lin` ou delegar ao u256.

### 4.3 Fórmulas — conferidas

`get_amount_in` usa $\lfloor num/den \rfloor + 1$ (teto via floor+1), idêntico ao
`UniswapV2Library.sol`. `quote` = $\lfloor a_A r_B / r_A\rfloor$. ✓. A taxa 0,3% é
exata em racionais (997/1000), sem float em lugar nenhum — propriedade a preservar.

---

## 5. Detecção de escala decimal: limiar 2³⁰ vs. rótulo "10¹²"

`reconciler_engine.lin` usa

$$\text{flag} \iff x>10^9 \land \lfloor x/2^{30}\rfloor > y,$$

ou seja, dispara quando $x \gtrsim 2^{30}\,y \approx 1{,}07\times10^9\,y$. Um erro de
decimais 6↔18 ($10^{12}=2^{39{,}86}$) é capturado, mas **também** qualquer razão
$>2^{30}$. É conservador (direção fail-closed, seguro), porém o rótulo "fator 10¹²"
é impreciso: o limiar real é $2^{30}$. **Melhoria matemática:** usar $\lfloor\log_2
x\rfloor = 255-\operatorname{clz}(x)$ (computável em LIN via deslocamentos repetidos
ou um laço de 256 passos) e flag $\left|\lfloor\log_2 x\rfloor-\lfloor\log_2
y\rfloor\right| > \theta$ com $\theta$ documentado — invariante à escala e provável.

---

## 6. Poder estatístico da evidência (por que fuzz >> vetores fixos)

Modelo: se as duas implementações divergem numa fração $p$ das entradas, a
probabilidade de **não** detectar em $n$ amostras iid é $(1-p)^n$. Poder $=1-(1-p)^n$:

| n | p = 10% | p = 1% | p = 0,1% | p = 10⁻⁵ |
|---|---|---|---|---|
| 34 (N-version) | 97,2% | **29,0%** | 3,3% | 0,03% |
| 1.000 (u256) | ~100% | 99,996% | 63,2% | 1,0% |
| 400.003 (fuzz) | ~100% | ~100% | ~100% | **98,2%** |

Conclusão: os 34 vetores N-version **não** estabelecem ausência de divergência (um
bug que afeta 1% das entradas tem 71% de chance de passar despercebido); o fuzz de
400k sim. **Melhoria (P2):** além do aleatório com seed fixa, adicionar **teste
exaustivo estruturado** do núcleo do u256 — ex.: todas as $2^{16}\times2^{16}$ entradas
de limbs de 16 bits para a multiplicação/carry (é a região onde vive a lógica de
overflow), e exaustão das bordas de shift `{-1,0,1,62,63,64,65,2^{32}-1}` para travar
a semântica §4.3.

---

## 7. Módulos de cripto — números conferidos e limites

- **ML-KEM/Kyber NTT:** $q=3329=13\cdot2^8+1$, raiz primitiva 256-ésima $\zeta=17$.
  Verificado: $17^{128}\equiv 3328 \equiv -1 \pmod{3329}$ e $17^{256}\equiv1$. ✓
  (constantes corretas; o NTT é real).
- **A5/1 (`gsm_a51_cryptanalysis.lin`):** taps $x^{19}+x^{18}+x^{17}+x^{14}+1$,
  $x^{22}+x^{21}+1$, $x^{23}+x^{22}+x^{21}+x^8+1$ ✓ (polinômios GSM). É um **subconjunto
  pedagógico** (a maioria usa o MSB como saída e o bit de clock simplificado); não
  reivindicar "break completo" do A5/1 — o repo já rotula como demo, manter.
- **ECDSA nonce-reuse (`ecdsa_nonce_reuse_crack.lin`):** a álgebra
  $k=(z_1-z_2)(s_1-s_2)^{-1}$, $d=(s_1k-z_1)r^{-1}\bmod n$ ✓. **Limite:** roda em i64,
  então $n \ll 2^{63}$ — é demonstração em inteiros pequenos, não um crack de
  secp256k1 ($n\approx2^{256}$). O rótulo `attack=sony_ps3_fail0verflow` é aspiracional;
  documentar como toy para não overclaim.
- **`lin_crypto_max_256.lin::aggregate_worker_digest`** usa a mesma mistura 32-bit
  (`& 0xFFFFFFFF`) do item 3.4(b) — mesmo defeito de colisão.

---

## 8. Roteiro priorizado (o que fazer e em que ordem)

**P0 (segurança/correção — antes de qualquer alegação pública):**
1. Renomear/substituir `lin_binary_merkle_provenance.lin` (afim) e `hash_pair`/`aggregate_worker_digest` (32-bit) — migrar para SHA-256 com domínios, ou rotular explicitamente como *checksum não-criptográfico*.
2. Adicionar guardas (ou delegar ao u256) em `src/lin_uniswap_v2_library.lin` para o domínio não testado.
3. Comprometer `leaf_count` no `build_merkle_root` (ou exigir potência de 2).

**P1 (performance — destrava a escala):**
4. Expor `lin_settle_u256_single_shot` no harness Python (corta 5×→1× execução): 10k swaps de ~93s → ~20s, **medir de verdade**.
5. Implementar divisão radix-2¹⁶ (Knuth D com recíproco de 1 limb, sem `/` nativo): projeção ~3–4s/10k.

**P2 (formalização/evidência — o que o grant pede):**
6. Congelar as semânticas §1 (anéis + exceções) e §3.1 (determinismo ⇒ commitment agregado) no spec.
7. Teste exaustivo estruturado do núcleo u256 (limbs 16-bit) + bordas de shift.
8. Documentar os tectos de `settlement_engine.lin` como função das desigualdades (fator de segurança explícito) ou trocar por carry-detection.
9. Rotular módulos de cripto como demonstração (toy) onde a precisão é limitada (ECDSA i64, A5/1 subset).
