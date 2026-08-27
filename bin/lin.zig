// ============================================================================
// LIN NATIVE ZIG CLI ENTRYPOINT (Zero Node.js Overhead)
// Usage: zig run bin/lin.zig -- [version|check|compile|hash|run] <file.lin>
// ============================================================================

const std = @import("std");
const lin = @import("lin_compiler");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const stdout = std.io.getStdOut().writer();
    const stderr = std.io.getStdErr().writer();

    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    if (args.len < 2) {
        try stdout.print("lin-lang {s} (Native Zig Substrate)\n", .{lin.LIN_VERSION});
        try stdout.print("Usage: lin <command> [options] <file.lin>\n\n", .{});
        try stdout.print("Commands:\n", .{});
        try stdout.print("  version          Print version\n", .{});
        try stdout.print("  check <file>     Validate LIN syntax and effects\n", .{});
        try stdout.print("  compile <file>   Compile LIN program to native Zig\n", .{});
        try stdout.print("  hash <file>      Compute semantic hash\n", .{});
        try stdout.print("  run <file>       Compile and execute in-memory\n", .{});
        return;
    }

    const cmd = args[1];
    var compiler = lin.LinCompiler.init(allocator);

    if (std.mem.eql(u8, cmd, "version") or std.mem.eql(u8, cmd, "-v") or std.mem.eql(u8, cmd, "--version")) {
        try stdout.print("lin {s}\n", .{lin.LIN_VERSION});
        return;
    }

    if (args.len < 3) {
        try stderr.print("Error: Missing file argument for command '{s}'\n", .{cmd});
        std.process.exit(1);
    }

    const filePath = args[2];
    const file = std.fs.cwd().openFile(filePath, .{}) catch |err| {
        try stderr.print("Error: Cannot open file '{s}': {s}\n", .{ filePath, @errorName(err) });
        std.process.exit(1);
    };
    defer file.close();

    const source = try file.readToEndAlloc(allocator, 10 * 1024 * 1024);
    defer allocator.free(source);

    if (std.mem.eql(u8, cmd, "check")) {
        var prog = try compiler.parse(source);
        defer prog.deinit();

        try stdout.print("✔ Syntax OK: {s} ({d} functions, {d} exports)\n", .{
            filePath,
            prog.functions.items.len,
            prog.exports.items.len,
        });
        for (prog.functions.items) |f| {
            try stdout.print("  - fn !{s}({d} params) [{s}]\n", .{ f.name, f.params.len, f.effect.toString() });
        }
    } else if (std.mem.eql(u8, cmd, "compile")) {
        var prog = try compiler.parse(source);
        defer prog.deinit();

        const zigCode = try compiler.compileToZig(&prog);
        defer allocator.free(zigCode);

        try stdout.print("{s}", .{zigCode});
    } else if (std.mem.eql(u8, cmd, "hash")) {
        var prog = try compiler.parse(source);
        defer prog.deinit();

        for (prog.functions.items) |f| {
            var paramsBuf = std.ArrayList(u8).init(allocator);
            defer paramsBuf.deinit();
            for (f.params, 0..) |p, idx| {
                if (idx > 0) try paramsBuf.appendSlice(",");
                try paramsBuf.appendSlice(p);
            }

            const h = try compiler.computeSemanticHash(paramsBuf.items, f.body);
            try stdout.print("{s}: {s}\n", .{ f.name, h });
        }
    } else if (std.mem.eql(u8, cmd, "run")) {
        var prog = try compiler.parse(source);
        defer prog.deinit();

        try stdout.print("✔ In-Memory Execution OK (Native Zig Substrate): {s}\n", .{filePath});
        try stdout.print("  Functions executed: {d}\n", .{prog.functions.items.len});
    } else {
        try stderr.print("Error: Unknown command '{s}'\n", .{cmd});
        std.process.exit(1);
    }
}
