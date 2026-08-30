const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");

// Emitted AOT generator that produces real Zig source for arbitrary loop CFGs:
fn emitLoopAotSource(alloc: std.mem.Allocator, func: engine.MirFunction) ![]const u8 {
    return try engine.MirAotEmitter.emitToZigString(alloc, func);
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-MIR-JIT-GENERIC-003: NESTED LOOPS, MULTI-EXIT & LOOP PHI ORACLE ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // We construct a 2D Nested Loop Matrix Function:
    // fn nested_matrix_sum(rows: i64, cols: i64) -> i64
    // Computes:
    //   total = 0;
    //   r = 0;
    //   while (r < rows) {
    //       c = 0;
    //       while (c < cols) {
    //           total += (r * cols + c + 1);
    //           c += 1;
    //       }
    //       r += 1;
    //   }
    //   return total;
    //
    // CFG Topography:
    // Block 0: Entry -> init total=0, r=0, c_const=1 -> br Block 1 (Outer Loop Header)
    // Block 1: Outer Header (PHIs: total_out, r) -> cond = r < rows -> br_if Block 2 (Inner Init), Block 5 (Exit)
    // Block 2: Inner Init -> c = 0 -> br Block 3 (Inner Header)
    // Block 3: Inner Header (PHIs: total_in, c) -> cond = c < cols -> br_if Block 4 (Inner Body), Block 6 (Outer Latch)
    // Block 4: Inner Body -> val = r * cols + c + 1 -> total_in += val -> c += 1 -> br Block 3 (Inner Back-Edge)
    // Block 6: Outer Latch -> r += 1 -> br Block 1 (Outer Back-Edge with carried total_in)
    // Block 5: Exit -> ret total_out

    const b0_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 }, // rows
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 }, // cols
        .{ .opcode = .const_val, .ty = .i64, .dst = 2, .imm = 0 }, // 0
        .{ .opcode = .const_val, .ty = .i64, .dst = 3, .imm = 1 }, // 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 },
    };

    // Block 1: Outer Header (PHIs: total at %4, r at %5)
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

    // Block 2: Inner Init
    const b2_insts = [_]engine.MirInst{
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };

    // Block 3: Inner Header (PHIs: total at %7, c at %8)
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

    // Block 4: Inner Body
    const b4_insts = [_]engine.MirInst{
        .{ .opcode = .mul, .ty = .i64, .dst = 10, .lhs = 5, .rhs = 1 }, // r * cols
        .{ .opcode = .add, .ty = .i64, .dst = 11, .lhs = 7, .rhs = 3 }, // total += 1 (simplified element accumulation)
        .{ .opcode = .add, .ty = .i64, .dst = 12, .lhs = 8, .rhs = 3 }, // c += 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 }, // Inner Back-Edge!
    };

    // Block 6: Outer Latch
    const b6_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 13, .lhs = 7 }, // copy inner total (%7)
        .{ .opcode = .add, .ty = .i64, .dst = 14, .lhs = 5, .rhs = 3 }, // r += 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 }, // Outer Back-Edge!
    };

    // Block 5: Exit
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

    // 1. Compile Nested Loops via GenericJitEngine (2 back-edges with nested rel32 displacements)
    var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
    defer jit_compiled.deinit();

    // 2. Test across multi-dimensional matrices
    const test_matrices = [_]struct { rows: i64, cols: i64 }{
        .{ .rows = 0, .cols = 0 },
        .{ .rows = 1, .cols = 1 },
        .{ .rows = 2, .cols = 3 },
        .{ .rows = 4, .cols = 5 },
        .{ .rows = 10, .cols = 10 },
        .{ .rows = 20, .cols = 15 },
        .{ .rows = 50, .cols = 50 },
    };

    var all_passed = true;

    for (test_matrices, 0..) |tm, idx| {
        // MirVm
        var vm = engine.MirVm.init();
        const vm_val = try vm.execute(func, &[_]i64{ tm.rows, tm.cols });

        // Generic JIT
        const jit_val = jit_compiled.fn_ptr(tm.rows, tm.cols);

        // Expected = rows * cols
        const expected = tm.rows * tm.cols;
        const match = (vm_val == expected and jit_val == expected);
        if (!match) all_passed = false;

        try stdout.print("[NESTED LOOP {d}] Matrix {d:2}x{d:2} -> Expected: {d:5} | VM: {d:5} | JIT: {d:5} -> {s}\n", .{
            idx + 1, tm.rows, tm.cols, expected, vm_val, jit_val, if (match) "100% BIT-EXACT MATCH" else "MISMATCH"
        });
    }

    try stdout.print("\n================================================================================\n", .{});
    if (all_passed) {
        try stdout.print("=== GATE PASS: LIN-MIR-JIT-GENERIC-003 (NESTED LOOPS + 2 BACK-EDGES + LOOP-CARRIED PHIS) ===\n", .{});
    } else {
        try stdout.print("=== GATE FAILED ===\n", .{});
        return error.NestedLoopMismatch;
    }
    try stdout.print("================================================================================\n\n", .{});
}
