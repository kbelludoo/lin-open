const std = @import("std");
const mir_vm = @import("src/lin_mir_vm.zig");
const verifier = @import("src/lin_mir_verifier.zig");

pub fn main() !void {
    std.debug.print("\n=== TESTING LIN-MIR STATIC VERIFIER ===\n", .{});

    // 1. Valid Function Test
    const valid_insts = [_]mir_vm.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 },
        .{ .opcode = .add, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
        .{ .opcode = .ret_op, .ty = .i64, .dst = 0, .lhs = 2 },
    };
    const valid_block = mir_vm.MirBlock{ .id = 0, .instructions = &valid_insts };
    const params = [_]mir_vm.MirType{ .i64, .i64 };
    const valid_func = mir_vm.MirFunction{
        .name = "valid_add",
        .params = &params,
        .returns = .i64,
        .blocks = &[_]mir_vm.MirBlock{valid_block},
    };

    try verifier.MirVerifier.verifyFunction(valid_func);
    std.debug.print("[PASS] Valid SSA MIR Function successfully verified!\n", .{});

    // 2. Invalid Function Test (SSA violation: duplicate definition of %2)
    const invalid_insts = [_]mir_vm.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 },
        .{ .opcode = .add, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
        .{ .opcode = .sub, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 }, // SSA violation: dst 2 redefined!
        .{ .opcode = .ret_op, .ty = .i64, .dst = 0, .lhs = 2 },
    };
    const invalid_block = mir_vm.MirBlock{ .id = 0, .instructions = &invalid_insts };
    const invalid_func = mir_vm.MirFunction{
        .name = "invalid_redef",
        .params = &params,
        .returns = .i64,
        .blocks = &[_]mir_vm.MirBlock{invalid_block},
    };

    if (verifier.MirVerifier.verifyFunction(invalid_func)) |_| {
        @panic("Expected SSA Duplicate Definition error but verifier passed!");
    } else |err| {
        std.debug.print("[PASS] Verifier correctly caught invalid SSA: {s}\n", .{@errorName(err)});
    }

    std.debug.print("=== ALL MIR VERIFIER TESTS PASSED! ===\n\n", .{});
}
