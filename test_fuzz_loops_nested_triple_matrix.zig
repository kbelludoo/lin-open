const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");
const aot_nested = @import("src/lin_mir_nested_loop_aot_compiled.zig");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-MIR-JIT-GENERIC-003A: TRUE TRIPLE ORACLE FOR NESTED LOOPS & PHIS ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    const b0_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 }, // rows
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 }, // cols
        .{ .opcode = .const_val, .ty = .i64, .dst = 2, .imm = 0 }, // 0
        .{ .opcode = .const_val, .ty = .i64, .dst = 3, .imm = 1 }, // 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 },
    };

    var phi_tot_out = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 4, .phi_count = 2 };
    phi_tot_out.phi_incoming_blocks[0] = 0;
    phi_tot_out.phi_incoming_vals[0] = 2; // init 0
    phi_tot_out.phi_incoming_blocks[1] = 6;
    phi_tot_out.phi_incoming_vals[1] = 13; // carried from outer latch (final total of inner loop)

    var phi_r = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 5, .phi_count = 2 };
    phi_r.phi_incoming_blocks[0] = 0;
    phi_r.phi_incoming_vals[0] = 2; // init 0
    phi_r.phi_incoming_blocks[1] = 6;
    phi_r.phi_incoming_vals[1] = 14; // next r

    const b1_insts = [_]engine.MirInst{
        phi_tot_out,
        phi_r,
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 6, .lhs = 5, .rhs = 0 }, // r < rows
        .{ .opcode = .br_if, .ty = .i1, .lhs = 6, .target_block = 2, .target_block_else = 5 },
    };

    const b2_insts = [_]engine.MirInst{
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };

    var phi_tot_in = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 7, .phi_count = 2 };
    phi_tot_in.phi_incoming_blocks[0] = 2;
    phi_tot_in.phi_incoming_vals[0] = 4; // start with outer total
    phi_tot_in.phi_incoming_blocks[1] = 4;
    phi_tot_in.phi_incoming_vals[1] = 11; // accumulated inner total

    var phi_c = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 8, .phi_count = 2 };
    phi_c.phi_incoming_blocks[0] = 2;
    phi_c.phi_incoming_vals[0] = 2; // init 0
    phi_c.phi_incoming_blocks[1] = 4;
    phi_c.phi_incoming_vals[1] = 12; // next c

    const b3_insts = [_]engine.MirInst{
        phi_tot_in,
        phi_c,
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 9, .lhs = 8, .rhs = 1 }, // c < cols
        .{ .opcode = .br_if, .ty = .i1, .lhs = 9, .target_block = 4, .target_block_else = 6 },
    };

    const b4_insts = [_]engine.MirInst{
        .{ .opcode = .mul, .ty = .i64, .dst = 10, .lhs = 5, .rhs = 1 },
        .{ .opcode = .add, .ty = .i64, .dst = 11, .lhs = 7, .rhs = 3 }, // total += 1
        .{ .opcode = .add, .ty = .i64, .dst = 12, .lhs = 8, .rhs = 3 }, // c += 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 }, // Inner Back-Edge!
    };

    const b6_insts = [_]engine.MirInst{
        .{ .opcode = .add, .ty = .i64, .dst = 13, .lhs = 7, .rhs = 2 }, // copy %7 + 0 -> %13
        .{ .opcode = .add, .ty = .i64, .dst = 14, .lhs = 5, .rhs = 3 }, // r += 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 }, // Outer Back-Edge!
    };

    const b5_insts = [_]engine.MirInst{
        .{ .opcode = .ret_op, .ty = .i64, .lhs = 4 },
    };

    const blocks = [_]engine.MirBlock{
        .{ .id = 0, .instructions = &b0_insts },
        .{ .id = 1, .instructions = &b1_insts },
        .{ .id = 2, .instructions = &b2_insts },
        .{ .id = 3, .instructions = &b3_insts },
        .{ .id = 4, .instructions = &b4_insts },
        .{ .id = 5, .instructions = &b5_insts },
        .{ .id = 6, .instructions = &b6_insts },
    };

    const params = [_]engine.MirType{ .i64, .i64 };
    const func = engine.MirFunction{
        .name = "nested_matrix_sum",
        .params = &params,
        .returns = .i64,
        .blocks = &blocks,
    };

    // 1. Compile Nested Loops via GenericJitEngine
    var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
    defer jit_compiled.deinit();

    // 2. Comprehensive Asymmetric, Boundary, and Large Matrix Test Suite
    const test_matrices = [_]struct { rows: i64, cols: i64, name: []const u8 }{
        .{ .rows = 0, .cols = 0, .name = "Zero boundary (0 x 0)" },
        .{ .rows = 0, .cols = 5, .name = "Zero rows (0 x 5)" },
        .{ .rows = 5, .cols = 0, .name = "Zero cols (5 x 0)" },
        .{ .rows = 1, .cols = 1, .name = "Unit square (1 x 1)" },
        .{ .rows = 1, .cols = 10, .name = "Single row (1 x 10)" },
        .{ .rows = 10, .cols = 1, .name = "Single col (10 x 1)" },
        .{ .rows = 2, .cols = 3, .name = "Asymmetric small (2 x 3)" },
        .{ .rows = 3, .cols = 2, .name = "Asymmetric small (3 x 2)" },
        .{ .rows = 7, .cols = 11, .name = "Primes (7 x 11)" },
        .{ .rows = 11, .cols = 7, .name = "Primes (11 x 7)" },
        .{ .rows = 50, .cols = 50, .name = "Medium square (50 x 50)" },
        .{ .rows = 100, .cols = 100, .name = "Large square (100 x 100)" },
        .{ .rows = 257, .cols = 193, .name = "Large asymmetric primes (257 x 193)" },
    };

    var all_passed = true;

    for (test_matrices, 0..) |tm, idx| {
        // MirVm
        var vm = engine.MirVm.init();
        const vm_val = try vm.execute(func, &[_]i64{ tm.rows, tm.cols });

        // Compiled AOT (Native Zig/LLVM)
        const aot_val = aot_nested.nested_matrix_sum_aot(tm.rows, tm.cols);

        // Generic JIT (RAM x86_64 W^X)
        const jit_val = jit_compiled.fn_ptr(tm.rows, tm.cols);

        // Closed-form mathematical oracle: rows * cols
        const expected = tm.rows * tm.cols;
        const match = (vm_val == expected and aot_val == expected and jit_val == expected);
        if (!match) all_passed = false;

        try stdout.print("[TRIPLE-LOOP {d:02}] {s:35} Input: ({d:3} x {d:3}) -> Exp: {d:6} | VM: {d:6} | AOT: {d:6} | JIT: {d:6} -> {s}\n", .{
            idx + 1, tm.name, tm.rows, tm.cols, expected, vm_val, aot_val, jit_val, if (match) "100% BIT-EXACT TRIPLE MATCH" else "MISMATCH"
        });
    }

    try stdout.print("\n================================================================================\n", .{});
    if (all_passed) {
        try stdout.print("=== GATE PASS: LIN-MIR-JIT-GENERIC-003A (100% VM == COMPILED AOT == GENERIC JIT) ===\n", .{});
    } else {
        try stdout.print("=== GATE FAILED ===\n", .{});
        return error.NestedLoopTripleMismatch;
    }
    try stdout.print("================================================================================\n\n", .{});
}
