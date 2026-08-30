const std = @import("std");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== EXECUTING 34-TARGET CORPUS VIA 'lin hypo' WITH RULEL VERDICTS ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const alloc = gpa.allocator();

    const targets = [_]struct { file: []const u8, fn_name: []const u8, args: []const []const u8, expected: []const u8 }{
        .{ .file = "test/corpus/adler32.lin", .fn_name = "test_adler32_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/crc32.lin", .fn_name = "test_crc32_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/fast_bitset.lin", .fn_name = "test_bitset_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/siphash.lin", .fn_name = "sipround", .args = &.{ "1", "2", "3", "4", "0" }, .expected = "12885164039" },
    };

    var verified_count: usize = 0;

    for (targets, 0..) |t, idx| {
        var argv = std.ArrayList([]const u8).init(alloc);
        defer argv.deinit();

        try argv.append("bin/lin_native");
        try argv.append("hypo");
        try argv.append(t.file);
        try argv.append(t.fn_name);
        for (t.args) |arg| {
            try argv.append(arg);
        }
        try argv.append("--expected");
        try argv.append(t.expected);

        var child = std.process.Child.init(argv.items, alloc);
        child.stdout_behavior = .Pipe;
        child.stderr_behavior = .Pipe;

        try child.spawn();
        const out = try child.stdout.?.readToEndAlloc(alloc, 1024 * 1024);
        defer alloc.free(out);
        _ = try child.wait();

        const confirmed = std.mem.indexOf(u8, out, ".verdict=\"CONFIRMED\"") != null;
        if (confirmed) {
            verified_count += 1;
            try stdout.print("[HYPO {d:02}/04] {s:26} :: {s:20} -> CONFIRMED (Matched expected {s})\n", .{
                idx + 1, t.file, t.fn_name, t.expected,
            });
        } else {
            try stdout.print("[HYPO {d:02}/04] {s:26} :: {s:20} -> REFUTED / FAILED\nOutput:\n{s}\n", .{
                idx + 1, t.file, t.fn_name, out,
            });
        }
    }

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== SUMMARY: {d}/{d} CORPUS HYPOTHESES CONFIRMED VIA 'lin hypo' ===\n", .{ verified_count, targets.len });
    try stdout.print("================================================================================\n\n", .{});
}
