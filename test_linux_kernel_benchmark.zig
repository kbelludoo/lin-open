const std = @import("std");
const lk = @import("src/lin_linux_kernel.zig");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("=== LINUX KERNEL VS LIN TRANSPILATION & OPTIMIZATION ===\n", .{});

    // 1. Correctness validation
    const v_test = lk.test_linux_kernel_vectors();
    try stdout.print("1. LIN Vector Test Suite: {s}\n", .{if (v_test == 1) "PASSED (100% OK)" else "FAILED"});

    // 2. Binary GCD Benchmark (1,000,000 iterations)
    const iterations: usize = 1_000_000;
    var prng = std.Random.DefaultPrng.init(12345);
    const random = prng.random();

    var timer = try std.time.Timer.start();
    var sum1: i64 = 0;
    for (0..iterations) |_| {
        const a = random.int(u32);
        const b = random.int(u32);
        sum1 +%= lk.lk_gcd(a, b);
    }
    std.mem.doNotOptimizeAway(&sum1);
    const time_orig_ns = timer.read();

    prng = std.Random.DefaultPrng.init(12345);
    timer.reset();
    var sum2: i64 = 0;
    for (0..iterations) |_| {
        const a = random.int(u32);
        const b = random.int(u32);
        sum2 +%= lk.lin_opt_gcd(a, b);
    }
    std.mem.doNotOptimizeAway(&sum2);
    const time_opt_ns = timer.read();

    try stdout.print("\n2. Binary GCD Benchmark ({d} runs):\n", .{iterations});
    try stdout.print("   Original Linux Kernel GCD: {d:.2} ms ({d:.2} M ops/sec) [checksum={d}]\n", .{
        @as(f64, @floatFromInt(time_orig_ns)) / 1_000_000.0,
        (@as(f64, @floatFromInt(iterations)) / @as(f64, @floatFromInt(time_orig_ns))) * 1000.0,
        sum1,
    });
    try stdout.print("   LIN Optimized GCD:         {d:.2} ms ({d:.2} M ops/sec) [checksum={d}]\n", .{
        @as(f64, @floatFromInt(time_opt_ns)) / 1_000_000.0,
        (@as(f64, @floatFromInt(iterations)) / @as(f64, @floatFromInt(time_opt_ns))) * 1000.0,
        sum2,
    });

    if (sum1 == sum2) {
        const speedup = @as(f64, @floatFromInt(time_orig_ns)) / @as(f64, @floatFromInt(time_opt_ns));
        try stdout.print("   >>> SPEEDUP: {d:.2}x ({d:.1}% faster) WITH ZERO DIVERGENCE! <<<\n", .{
            speedup, (speedup - 1.0) * 100.0,
        });
    }

    // 3. JHash Throughput
    timer.reset();
    var jhash_sum: i64 = 0;
    for (0..iterations) |k| {
        jhash_sum +%= lk.lk_jhash_1word(@intCast(k), 0xdeadbeef);
    }
    std.mem.doNotOptimizeAway(&jhash_sum);
    const jhash_time_ns = timer.read();
    try stdout.print("\n3. Linux jhash_1word Benchmark ({d} runs):\n", .{iterations});
    try stdout.print("   Throughput: {d:.2} M hashes/sec ({d:.2} ms) [checksum={d}]\n", .{
        (@as(f64, @floatFromInt(iterations)) / @as(f64, @floatFromInt(jhash_time_ns))) * 1000.0,
        @as(f64, @floatFromInt(jhash_time_ns)) / 1_000_000.0,
        jhash_sum,
    });
}
