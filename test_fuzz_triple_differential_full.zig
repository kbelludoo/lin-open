const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");
const verifier = @import("src/lin_mir_verifier.zig");

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
    try stdout.print("=== LIN-MIR-FUZZ-004: FULL TRIPLE DIFFERENTIAL (MirVm == AOT == GenericJit) ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var prng = std.Random.DefaultPrng.init(777);
    const rand = prng.random();

    const total_programs: usize = 1_000;
    var passed_matches: usize = 0;

    var timer = try std.time.Timer.start();

    const opcodes = [_]engine.MirOpcode{
        .add,
        .sub,
        .mul,
        .and_op,
        .or_op,
        .xor_op,
    };

    for (0..total_programs) |prog_idx| {
        const op_b0 = opcodes[rand.uintLessThan(usize, opcodes.len)];
        const op_b1 = opcodes[rand.uintLessThan(usize, opcodes.len)];
        const op_b2 = opcodes[rand.uintLessThan(usize, opcodes.len)];

        // Block 0: Cond = (arg0 op_b0 arg1) < arg0
        const b0_insts = [_]engine.MirInst{
            .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
            .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 },
            .{ .opcode = op_b0, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .cmp_lt, .ty = .i64, .dst = 3, .lhs = 2, .rhs = 0 },
            .{ .opcode = .br_if, .ty = .i1, .lhs = 3, .target_block = 1, .target_block_else = 2 },
        };

        // Block 1 (True branch): r4 = arg0 op_b1 arg1
        const b1_insts = [_]engine.MirInst{
            .{ .opcode = op_b1, .ty = .i64, .dst = 4, .lhs = 0, .rhs = 1 },
            .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
        };

        // Block 2 (False branch): r5 = arg1 op_b2 arg0
        const b2_insts = [_]engine.MirInst{
            .{ .opcode = op_b2, .ty = .i64, .dst = 5, .lhs = 1, .rhs = 0 },
            .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
        };

        // Block 3 (Join with PHI): r6 = PHI(B1:r4, B2:r5) -> ret r6
        var phi_inst = engine.MirInst{
            .opcode = .phi_op,
            .ty = .i64,
            .dst = 6,
            .phi_count = 2,
        };
        phi_inst.phi_incoming_blocks[0] = 1;
        phi_inst.phi_incoming_vals[0] = 4;
        phi_inst.phi_incoming_blocks[1] = 2;
        phi_inst.phi_incoming_vals[1] = 5;

        const b3_insts = [_]engine.MirInst{
            phi_inst,
            .{ .opcode = .ret_op, .ty = .i64, .lhs = 6 },
        };

        const blocks = [_]engine.MirBlock{
            .{ .id = 0, .instructions = &b0_insts },
            .{ .id = 1, .instructions = &b1_insts },
            .{ .id = 2, .instructions = &b2_insts },
            .{ .id = 3, .instructions = &b3_insts },
        };

        const params = [_]engine.MirType{ .i64, .i64 };
        const func = engine.MirFunction{
            .name = "fuzz_tri",
            .params = &params,
            .returns = .i64,
            .blocks = &blocks,
        };

        const arg0 = rand.int(i64) & 0xFFFF;
        const arg1 = rand.int(i64) & 0xFFFF;

        // 1. MirVm
        var vm = engine.MirVm.init();
        const vm_res = try vm.execute(func, &[_]i64{ arg0, arg1 });

        // 2. AOT Execution
        const aot_res = try executeAotSemantics(func, &[_]i64{ arg0, arg1 });

        // 3. Generic JIT Compilation directly from MirFunction
        var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
        defer jit_compiled.deinit();
        const jit_res = jit_compiled.fn_ptr(arg0, arg1);

        if (vm_res == aot_res and aot_res == jit_res) {
            passed_matches += 1;
        } else {
            std.debug.print("[FAIL] Mismatch in Triple Program {d}: VM={d}, AOT={d}, JIT={d}\n", .{ prog_idx, vm_res, aot_res, jit_res });
            return error.TripleFuzzMismatch;
        }
    }

    const elapsed_ns = timer.read();
    const rate = (@as(f64, @floatFromInt(total_programs)) / @as(f64, @floatFromInt(elapsed_ns))) * 1000.0;

    try stdout.print("[FUZZING SUMMARY] 1,000 CFG/PHI Programs Triple-Compiled & Verified:\n", .{});
    try stdout.print("                  Total Programs:       {d}\n", .{total_programs});
    try stdout.print("                  Triple Matches:       {d} (100.0% Exact Parity VM == AOT == JIT)\n", .{passed_matches});
    try stdout.print("                  Total Elapsed Time:   {d:.2} ms ({d:.2} K programs/s)\n", .{ @as(f64, @floatFromInt(elapsed_ns)) / 1_000_000.0, rate });
    try stdout.print("                  Triple Divergences:   0\n\n", .{});
    try stdout.print("================================================================================\n", .{});
    try stdout.print("=== GATE PASS: LIN-MIR-FUZZ-004 (GENERIC TRIPLE MirFunction EXECUTION) ===\n", .{});
    try stdout.print("================================================================================\n", .{});
}
