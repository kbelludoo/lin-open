const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");

fn executeAotSemantics(func: engine.MirFunction, args: []const i64) !i64 {
    var r: [256]i64 = [_]i64{0} ** 256;
    for (args, 0..) |arg, i| {
        if (i < 256) r[i] = arg;
    }
    var current_block: u32 = 0;
    var prev_block: u32 = 0;
    var iters: usize = 0;

    while (iters < 100_000) : (iters += 1) {
        var found_b: ?engine.MirBlock = null;
        for (func.blocks) |b| {
            if (b.id == current_block) {
                found_b = b;
                break;
            }
        }
        if (found_b == null) return error.BlockNotFound;
        const b = found_b.?;

        for (b.instructions) |inst| {
            switch (inst.opcode) {
                .const_val => r[inst.dst] = inst.imm,
                .param => r[inst.dst] = r[inst.lhs],
                .add => r[inst.dst] = r[inst.lhs] +% r[inst.rhs],
                .sub => r[inst.dst] = r[inst.lhs] -% r[inst.rhs],
                .mul => r[inst.dst] = r[inst.lhs] *% r[inst.rhs],
                .and_op => r[inst.dst] = r[inst.lhs] & r[inst.rhs],
                .or_op => r[inst.dst] = r[inst.lhs] | r[inst.rhs],
                .xor_op => r[inst.dst] = r[inst.lhs] ^ r[inst.rhs],
                .cmp_lt => r[inst.dst] = if (r[inst.lhs] < r[inst.rhs]) 1 else 0,
                .cmp_eq => r[inst.dst] = if (r[inst.lhs] == r[inst.rhs]) 1 else 0,
                .phi_op => {
                    var resolved = false;
                    for (0..inst.phi_count) |k| {
                        if (inst.phi_incoming_blocks[k] == prev_block) {
                            r[inst.dst] = r[inst.phi_incoming_vals[k]];
                            resolved = true;
                            break;
                        }
                    }
                    if (!resolved and inst.phi_count > 0) {
                        r[inst.dst] = r[inst.phi_incoming_vals[0]];
                    }
                },
                .br_jmp => {
                    prev_block = current_block;
                    current_block = inst.target_block;
                    break;
                },
                .br_if => {
                    prev_block = current_block;
                    const cond = r[inst.lhs];
                    current_block = if (cond != 0) inst.target_block else inst.target_block_else;
                    break;
                },
                .ret_op => return r[inst.lhs],
                else => {},
            }
        }
    }
    return error.InfiniteLoopDetected;
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-MIR-JIT-GENERIC-002: LOOPS, BACK-EDGES & MULTIPLE PHI ORACLE ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // We build a real Loop Function: fn sum_1_to_n(n: i64) -> i64
    // Computes: sum = 0; i = n; while (i > 0) { sum += i; i -= 1; } return sum;
    //
    // Block 0 (Header / Entry):
    //   %0 = param n (reg 0)
    //   %1 = const 0 (initial sum)
    //   %2 = const 1
    //   br Block 1
    //
    // Block 1 (Loop Header with Multiple PHIs):
    //   %3 = phi [B0: %1 (0), B2: %6 (new_sum)]   ; accumulator sum
    //   %4 = phi [B0: %0 (n), B2: %7 (new_i)]     ; counter i
    //   %5 = cmp_lt %1, %4                        ; 0 < i (i > 0)
    //   br_if %5, Block 2 (Body), Block 3 (Exit)
    //
    // Block 2 (Loop Body & Back-Edge):
    //   %6 = add %3, %4                           ; sum += i
    //   %7 = sub %4, %2                           ; i -= 1
    //   br_jmp Block 1                            ; (Back-edge to Block 1)
    //
    // Block 3 (Exit):
    //   ret %3

    // Block 0
    const b0_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 1, .imm = 0 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 2, .imm = 1 },
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 },
    };

    // Block 1 (Multiple PHIs)
    var phi_sum = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 3, .phi_count = 2 };
    phi_sum.phi_incoming_blocks[0] = 0;
    phi_sum.phi_incoming_vals[0] = 1;
    phi_sum.phi_incoming_blocks[1] = 2;
    phi_sum.phi_incoming_vals[1] = 6;

    var phi_i = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 4, .phi_count = 2 };
    phi_i.phi_incoming_blocks[0] = 0;
    phi_i.phi_incoming_vals[0] = 0;
    phi_i.phi_incoming_blocks[1] = 2;
    phi_i.phi_incoming_vals[1] = 7;

    const b1_insts = [_]engine.MirInst{
        phi_sum,
        phi_i,
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 5, .lhs = 1, .rhs = 4 }, // 0 < i
        .{ .opcode = .br_if, .ty = .i1, .lhs = 5, .target_block = 2, .target_block_else = 3 },
    };

    // Block 2 (Body & Back-Edge)
    const b2_insts = [_]engine.MirInst{
        .{ .opcode = .add, .ty = .i64, .dst = 6, .lhs = 3, .rhs = 4 },
        .{ .opcode = .sub, .ty = .i64, .dst = 7, .lhs = 4, .rhs = 2 },
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 }, // Back-Edge!
    };

    // Block 3 (Exit)
    const b3_insts = [_]engine.MirInst{
        .{ .opcode = .ret_op, .ty = .i64, .lhs = 3 },
    };

    const blocks = [_]engine.MirBlock{
        .{ .id = 0, .instructions = &b0_insts },
        .{ .id = 1, .instructions = &b1_insts },
        .{ .id = 2, .instructions = &b2_insts },
        .{ .id = 3, .instructions = &b3_insts },
    };

    const params = [_]engine.MirType{.i64};
    const func = engine.MirFunction{
        .name = "mir_sum_loop",
        .params = &params,
        .returns = .i64,
        .blocks = &blocks,
    };

    // 1. Compile Generic JIT with Loop Back-Edge
    var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
    defer jit_compiled.deinit();

    // 2. Test Loop across inputs: n = 0, 1, 5, 10, 100, 1000
    const test_n = [_]i64{ 0, 1, 5, 10, 50, 100, 1000 };

    for (test_n, 0..) |n, idx| {
        // MirVm
        var vm = engine.MirVm.init();
        const vm_val = try vm.execute(func, &[_]i64{n});

        // AOT
        const aot_val = try executeAotSemantics(func, &[_]i64{n});

        // JIT
        const jit_val = jit_compiled.fn_ptr(n, 0);

        const expected = @divExact(n * (n + 1), 2);
        const match = (vm_val == expected and aot_val == expected and jit_val == expected);

        try stdout.print("[LOOP TEST {d}] n={d:4} -> Expected: {d:7} | VM={d:7} | AOT={d:7} | JIT={d:7} -> {s}\n", .{
            idx + 1, n, expected, vm_val, aot_val, jit_val, if (match) "100% BIT-EXACT MATCH" else "MISMATCH"
        });
        if (!match) return error.LoopOracleMismatch;
    }

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== GATE PASS: LIN-MIR-JIT-GENERIC-002 (LOOPS + BACK-EDGES + MULTIPLE PHIS) ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});
}
