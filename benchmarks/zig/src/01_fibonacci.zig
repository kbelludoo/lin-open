const std = @import("std");
const time = std.time;

// Fibonacci recursivo simples
fn fib(n: u32) u64 {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    
    try stdout.print("🔺 Zig Fibonacci Benchmark\n\n", .{});
    
    const n: u32 = 40;
    const iterations: usize = 5;
    
    var times: [iterations]i128 = undefined;
    
    try stdout.print("Calculando fib({d})...\n\n", .{n});
    
    var i: usize = 0;
    while (i < iterations) : (i += 1) {
        const start = time.nanoTimestamp();
        const result = fib(n);
        const end = time.nanoTimestamp();
        
        const elapsed_ns = end - start;
        const elapsed_ms = @as(f64, @floatFromInt(elapsed_ns)) / 1_000_000.0;
        
        times[i] = elapsed_ns;
        
        try stdout.print("  Run {d}: fib({d}) = {d} | Tempo: {d:.2}ms\n", 
            .{ i + 1, n, result, elapsed_ms });
    }
    
    // Calcular média
    var total: i128 = 0;
    for (times) |t| {
        total += t;
    }
    const avg_ms = (@as(f64, @floatFromInt(total)) / @as(f64, @floatFromInt(iterations))) / 1_000_000.0;
    
    try stdout.print("\n⏱️  Tempo médio: {d:.2}ms\n", .{avg_ms});
    try stdout.print("📊 Throughput: {d:.0} iterações/s\n\n", .{1000.0 / avg_ms});
    
    _ = std.debug.getStderrMutex();
}
