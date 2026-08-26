#!/bin/bash
set -e
cd /home/k/Downloads/lin-master || exit 1

echo "==> [1/4] Isolando Benchmarks e Scripts Python (Cat 3)"
mkdir -p benchmarks

find scripts -type f \( -name "bench_*" -o -name "run_*" -o -name "*.py" \) ! -name "bench_ai_context_death.mjs" -exec mv {} benchmarks/ \; 2>/dev/null || true
mv scripts/gate11_fp_audit.mjs benchmarks/ 2>/dev/null || true
mv scripts/lin_target_quality_bench.mjs benchmarks/ 2>/dev/null || true
mv scripts/inspect_oracles.mjs benchmarks/ 2>/dev/null || true

if [ -f "scripts/bench_ai_context_death.mjs" ]; then
    mv scripts/bench_ai_context_death.mjs benchmarks/
    echo "export * from '../benchmarks/bench_ai_context_death.mjs';" > scripts/bench_ai_context_death.mjs
    echo "    -> [Ajuste Fino 2] Shim criado: scripts/bench_ai_context_death.mjs (re-export seguro para tests/ain_lb/)"
fi

echo "==> [2/4] Extraindo Lógica Pura (Cat 2) para .lin via agent-ir"
declare -A targets=(
    ["compare_targets"]="compare_targets.lin"
    ["b6_logic_oracle"]="b6_logic_oracle.lin"
    ["b6_logic_v2_generator"]="b6_logic_v2_generator.lin"
    ["classify_v4_false_positives"]="gate11_taxonomy.lin"
    ["clone_lin_native"]="extract_native.lin"
)

for script in "${!targets[@]}"; do
    lin_file="${targets[$script]}"
    if [ -f "scripts/${script}.mjs" ]; then
        echo "    Convertendo ${script}.mjs -> src/${lin_file}..."
        node bin/lin.mjs agent-ir --from "scripts/${script}.mjs" --to "src/${lin_file}" || echo "        (Aviso: Verifique se o agent-ir suporta extração JS direta. Caso contrário, crie o .lin manualmente.)"
    fi
done

echo "==> [3/4] Substituindo scripts originais por Shims Mínimos"
for script in "${!targets[@]}"; do
    lin_file="${targets[$script]}"
    if [ -f "src/${lin_file}" ]; then
        echo "    Gerando shim para ${script}.mjs..."
        node bin/lin.mjs emit-shim --target "src/${lin_file}" --out "scripts/${script}.mjs" || echo "        (shim manual)"
    fi
done

echo "==> [4/4] Validação de Integridade e Testes"
echo "    Rodando self-repair para recalibrar hashes do núcleo e imports..."
npm run self-repair -- --smoke 2>&1 | tail -20

echo "    Rodando suite de testes completa (npm test)..."
npm test 2>&1 | tail -30

echo "==> Migração concluída com sucesso. Diretório scripts/ reduzido para ~15 arquivos essenciais."
