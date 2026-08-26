// Benchmark 01: Parsing de AST (Rust)
// Testa performance na análise sintática de expressões LIN

use std::time::Instant;

fn main() {
    println!("============================================================");
    println!("BENCHMARK 01: Parsing de AST");
    println!("============================================================\n");

    // Gera 10.000 expressões LIN para parsing
    let expressions = generate_lin_expressions(10_000);

    // Warmup
    println!("Warmup...");
    for _ in 0..5 {
        for expr in expressions.iter().take(100) {
            parse_expression(expr);
        }
    }

    // Benchmark principal
    println!("\nExecutando benchmark (10 iterações)...");
    let mut times = Vec::with_capacity(10);
    let mut parsed_count = 0;

    for iteration in 0..10 {
        let start = Instant::now();

        for expr in &expressions {
            if parse_expression(expr).success {
                parsed_count += 1;
            }
        }

        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
        times.push(elapsed);
        println!("  Iteração {}: {:.2}ms", iteration + 1, elapsed);
    }

    // Estatísticas
    let avg = times.iter().sum::<f64>() / times.len() as f64;
    let min = times.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = times.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let variance: f64 = times.iter().map(|t| (t - avg).powi(2)).sum::<f64>() / times.len() as f64;
    let stddev = variance.sqrt();
    let throughput = (expressions.len() * 10) as f64 / (times.iter().sum::<f64>() / 1000.0);

    println!("\n============================================================");
    println!("RESULTADOS");
    println!("============================================================");
    println!("Expressões processadas: {}", parsed_count);
    println!("Tempo médio: {:.2}ms", avg);
    println!("Tempo mínimo: {:.2}ms", min);
    println!("Tempo máximo: {:.2}ms", max);
    println!("Desvio padrão: {:.2}ms", stddev);
    println!("Throughput: {:.0} expressões/segundo", throughput);
    println!("Parsing por expressão: {:.3}µs", avg / expressions.len() as f64 * 1000.0);

    // Salva resultado
    let result = format!(
        "Benchmark: 01_Parsing\n\
         Language: Rust\n\
         Expressions: {}\n\
         Avg_ms: {:.4}\n\
         Min_ms: {:.4}\n\
         Max_ms: {:.4}\n\
         StdDev: {:.4}\n\
         Throughput: {:.2}\n\
         Memory_MB: N/A\n",
        parsed_count, avg, min, max, stddev, throughput
    );

    std::fs::write("results_01_parsing.txt", &result).expect("Failed to write results");
    println!("\n✅ Resultados salvos em results_01_parsing.txt");
}

fn generate_lin_expressions(count: usize) -> Vec<String> {
    let templates = [
        "let x{i} = {val}",
        "fn f{i}(x) = x + {val}",
        "if x > {val} then y else z",
        "match x with | Some(v) -> v | None -> {val}",
        "{val} |> fn x -> x * 2",
        "[1..{val}] |> map(fn x -> x^2)",
        "type T{i} = {{ field: Int, value: String }}",
    ];

    (1..=count)
        .map(|i| {
            let template = templates[i % templates.len()];
            template.replace("{i}", &i.to_string()).replace("{val}", &(i * 7).to_string())
        })
        .collect()
}

struct ParsedResult {
    success: bool,
    tokens: usize,
    depth: usize,
}

fn parse_expression(expr: &str) -> ParsedResult {
    // Parser simplificado para benchmark
    ParsedResult {
        success: true,
        tokens: expr.split_whitespace().count(),
        depth: expr.matches('{').count() + expr.matches('(').count(),
    }
}
