const std = @import("std");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-HYPO-003: CROSS-BACKEND DIFFERENTIAL & ADVERSARIAL VERIFICATION ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const alloc = gpa.allocator();

    // 1. We test Positive Cases (Hypothesis holds) -> Must produce CONFIRMED with .equivalent=true
    // 2. We test Negative / Adversarial Cases (Wrong expected value, wrong function) -> Must produce REFUTED
    const test_hypotheses = [_]struct {
        name: []const u8,
        target_file: []const u8,
        fn_name: []const u8,
        args_str: []const u8,
        expected: []const u8,
        expect_confirmed: bool,
    }{
        .{
            .name = "Positive: FastBitset Popcount Canonical Vector",
            .target_file = "test/corpus/fast_bitset.lin",
            .fn_name = "test_bitset_vector",
            .args_str = "[]",
            .expected = "1",
            .expect_confirmed = true,
        },
        .{
            .name = "Positive: Adler32 Vector Verification",
            .target_file = "test/corpus/adler32.lin",
            .fn_name = "test_adler32_vector",
            .args_str = "[]",
            .expected = "1",
            .expect_confirmed = true,
        },
        .{
            .name = "Positive: SipHash Round Multivariable Step",
            .target_file = "test/corpus/siphash.lin",
            .fn_name = "sipround",
            .args_str = "[1, 2, 3, 4, 0]",
            .expected = "12885164039",
            .expect_confirmed = true,
        },
        .{
            .name = "Adversarial: Incorrect Expected Value for Popcount",
            .target_file = "test/corpus/fast_bitset.lin",
            .fn_name = "popcount64",
            .args_str = "[6148914691236517205]",
            .expected = "999", // Wrong! True value is 32
            .expect_confirmed = false,
        },
        .{
            .name = "Adversarial: Incorrect Expected Value for CRC32",
            .target_file = "test/corpus/crc32.lin",
            .fn_name = "test_crc32_vector",
            .args_str = "[]",
            .expected = "0", // Wrong! True value is 1
            .expect_confirmed = false,
        },
        .{
            .name = "Adversarial: Non-Existent Target Function",
            .target_file = "test/corpus/crc32.lin",
            .fn_name = "non_existent_fn",
            .args_str = "[]",
            .expected = "1",
            .expect_confirmed = false,
        },
    };

    var all_verified = true;

    for (test_hypotheses, 0..) |th, idx| {
        // Construct temporary RULEL v2.0.0 file
        const tmp_path = try std.fmt.allocPrint(alloc, "/tmp/hypo_test_{d}.rulel", .{idx});
        defer alloc.free(tmp_path);

        const hyp_text = try std.fmt.allocPrint(alloc,
            \\@RULEL:LIN_HYPOTHESIS:2.0.0
            \\.target_file="{s}"
            \\.fn="{s}"
            \\.args={s}
            \\.executors=["vm","aot","jit"]
            \\.oracle="reference"
            \\.expected={s}
            \\
        , .{ th.target_file, th.fn_name, th.args_str, th.expected });
        defer alloc.free(hyp_text);

        const f = try std.fs.cwd().createFile(tmp_path, .{});
        try f.writeAll(hyp_text);
        f.close();

        // Run bin/lin_native hypo <tmp_path>
        var child = std.process.Child.init(&[_][]const u8{ "bin/lin_native", "hypo", tmp_path }, alloc);
        child.stdout_behavior = .Pipe;
        child.stderr_behavior = .Pipe;

        try child.spawn();
        const out = try child.stdout.?.readToEndAlloc(alloc, 1024 * 1024);
        defer alloc.free(out);
        _ = try child.wait();

        const is_confirmed = std.mem.indexOf(u8, out, ".verdict=\"CONFIRMED\"") != null;
        const is_refuted = std.mem.indexOf(u8, out, ".verdict=\"REFUTED\"") != null;

        const correct_behavior = (th.expect_confirmed and is_confirmed) or (!th.expect_confirmed and is_refuted);
        if (!correct_behavior) all_verified = false;

        const status_str = if (is_confirmed) "CONFIRMED" else if (is_refuted) "REFUTED" else "UNKNOWN";
        const pass_fail = if (correct_behavior) "PASS (EXPECTED)" else "FAIL (UNEXPECTED)";

        try stdout.print("[HYPO-TEST {d:02}] {s:50} -> {s} -> {s}\n", .{ idx + 1, th.name, status_str, pass_fail });
    }

    try stdout.print("\n================================================================================\n", .{});
    if (all_verified) {
        try stdout.print("=== GATE PASS: LIN-HYPO-003 (POSITIVE & ADVERSARIAL REFUTATION CERTIFIED) ===\n", .{});
    } else {
        try stdout.print("=== GATE FAILED ===\n", .{});
        return error.HypoVerificationFailure;
    }
    try stdout.print("================================================================================\n\n", .{});
}
