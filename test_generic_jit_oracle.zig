const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-MIR-JIT-GENERIC-001: COMPILING ARBITRARY MirFunction DIRECTLY IN JIT ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // Construct MirFunction: abs_diff
    const b0_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 },
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
        .{ .opcode = .br_if, .ty = .i1, .lhs = 2, .target_block = 1, .target_block_else = 2 },
    };
    const b1_insts = [_]engine.MirInst{
        .{ .opcode = .sub, .ty = .i64, .dst = 3, .lhs = 1, .rhs = 0 },
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };
    const b2_insts = [_]engine.MirInst{
        .{ .opcode = .sub, .ty = .i64, .dst = 4, .lhs = 0, .rhs = 1 },
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };
    var phi_inst = engine.MirInst{
        .opcode = .phi_op,
        .ty = .i64,
        .dst = 5,
        .phi_count = 2,
    };
    phi_inst.phi_incoming_blocks[0] = 1;
    phi_inst.phi_incoming_vals[0] = 3;
    phi_inst.phi_incoming_blocks[1] = 2;
    phi_inst.phi_incoming_vals[1] = 4;

    const b3_insts = [_]engine.MirInst{
        phi_inst,
        .{ .opcode = .ret_op, .ty = .i64, .lhs = 5 },
    };

    const blocks = [_]engine.MirBlock{
        .{ .id = 0, .instructions = &b0_insts },
        .{ .id = 1, .instructions = &b1_insts },
        .{ .id = 2, .instructions = &b2_insts },
        .{ .id = 3, .instructions = &b3_insts },
    };
    const params = [_]engine.MirType{ .i64, .i64 };
    const func = engine.MirFunction{
        .name = "generic_abs_diff",
        .params = &params,
        .returns = .i64,
        .blocks = &blocks,
    };

    // Compile MirFunction generically to x86_64 machine code via GenericJitEngine
    var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
    defer jit_compiled.deinit();

    // Test across adversarial cases
    const test_cases = [_]struct { a: i64, b: i64, name: []const u8 }{
        .{ .a = 30, .b = 100, .name = "Standard a < b" },
        .{ .a = 150, .b = 40, .name = "Standard a >= b" },
        .{ .a = 0, .b = 0, .name = "Zero boundary (0, 0)" },
        .{ .a = 0, .b = 1, .name = "Zero / One (0, 1)" },
        .{ .a = 1, .b = 0, .name = "One / Zero (1, 0)" },
        .{ .a = -1, .b = 0, .name = "Negative / Zero (-1, 0)" },
        .{ .a = 0, .b = -1, .name = "Zero / Negative (0, -1)" },
        .{ .a = -50, .b = -20, .name = "Both Negative (-50, -20)" },
        .{ .a = -20, .b = -50, .name = "Both Negative (-20, -50)" },
    };

    for (test_cases, 0..) |tc, idx| {
        var vm = engine.MirVm.init();
        const vm_val = try vm.execute(func, &[_]i64{ tc.a, tc.b });
        const jit_val = jit_compiled.fn_ptr(tc.a, tc.b);

        const expected = if (tc.a < tc.b) tc.b -% tc.a else tc.a -% tc.b;
        const match = (vm_val == expected and jit_val == expected);

        try stdout.print("[GENERIC-JIT {d:02}] {s:25} Input: ({d}, {d}) -> VM={d} | JIT={d} -> {s}\n", .{
            idx + 1, tc.name, tc.a, tc.b, vm_val, jit_val, if (match) "100% BIT-EXACT MATCH" else "MISMATCH"
        });
        if (!match) return error.GenericJitMismatch;
    }

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== GATE PASS: LIN-MIR-JIT-GENERIC-001 (GENERIC MirFunction -> JIT COMPILER) ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});
}
