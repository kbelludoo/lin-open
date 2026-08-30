const std = @import("std");
const jit = @import("src/lin_jit.zig");

pub fn main() !void {
    // 1. Test In-Memory JIT add
    const add_res = try jit.emitAddJit();
    defer jit.JitEngine.freePage(add_res.page);
    const sum = add_res.fn_ptr(100, 250);
    std.debug.print("JIT In-Memory Add(100, 250) = {d} (Expected 350)\n", .{sum});

    // 2. Test In-Memory JIT rotl64
    const rot_res = try jit.emitRotl64Jit();
    defer jit.JitEngine.freePage(rot_res.page);
    const rot = rot_res.fn_ptr(1, 4); // 1 << 4 = 16
    std.debug.print("JIT In-Memory Rotl64(1, 4) = {d} (Expected 16)\n", .{rot});

    if (sum == 350 and rot == 16) {
        std.debug.print("JIT IN-MEMORY TESTS: 100% PASSED!\n", .{});
    } else {
        return error.JitMismatch;
    }
}
