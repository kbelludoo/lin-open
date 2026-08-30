const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");
const compiled_aot = @import("src/lin_mir_fuzz_compiled_aot.zig");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-MIR-FUZZ-005B: 21,600 FULL TRIPLE EXECUTIONS (VM == COMPILED AOT == JIT) ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var prng = std.Random.DefaultPrng.init(998877);
    const rand = prng.random();

    const opcodes = [_]engine.MirOpcode{
        .add,
        .sub,
        .mul,
        .and_op,
        .or_op,
        .xor_op,
    };

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const alloc = gpa.allocator();

    var funcs_buf: [216]engine.MirFunction = undefined;
    var f_idx: usize = 0;

    for (opcodes) |op0| {
        for (opcodes) |op1| {
            for (opcodes) |op2| {
                const b0_insts = try alloc.alloc(engine.MirInst, 5);
                b0_insts[0] = .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 };
                b0_insts[1] = .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 };
                b0_insts[2] = .{ .opcode = op0, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 };
                b0_insts[3] = .{ .opcode = .cmp_lt, .ty = .i64, .dst = 3, .lhs = 2, .rhs = 0 };
                b0_insts[4] = .{ .opcode = .br_if, .ty = .i1, .lhs = 3, .target_block = 1, .target_block_else = 2 };

                const b1_insts = try alloc.alloc(engine.MirInst, 2);
                b1_insts[0] = .{ .opcode = op1, .ty = .i64, .dst = 4, .lhs = 0, .rhs = 1 };
                b1_insts[1] = .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 };

                const b2_insts = try alloc.alloc(engine.MirInst, 2);
                b2_insts[0] = .{ .opcode = op2, .ty = .i64, .dst = 5, .lhs = 1, .rhs = 0 };
                b2_insts[1] = .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 };

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

                const b3_insts = try alloc.alloc(engine.MirInst, 2);
                b3_insts[0] = phi_inst;
                b3_insts[1] = .{ .opcode = .ret_op, .ty = .i64, .lhs = 6 };

                const blocks = try alloc.alloc(engine.MirBlock, 4);
                blocks[0] = .{ .id = 0, .instructions = b0_insts };
                blocks[1] = .{ .id = 1, .instructions = b1_insts };
                blocks[2] = .{ .id = 2, .instructions = b2_insts };
                blocks[3] = .{ .id = 3, .instructions = b3_insts };

                const fn_name = try std.fmt.allocPrint(alloc, "fuzz_fn_{d}", .{f_idx});
                const params = try alloc.alloc(engine.MirType, 2);
                params[0] = .i64;
                params[1] = .i64;

                const func = engine.MirFunction{
                    .name = fn_name,
                    .params = params,
                    .returns = .i64,
                    .blocks = blocks,
                };
                funcs_buf[f_idx] = func;
                f_idx += 1;
            }
        }
    }

    const total_funcs: usize = 216;
    const inputs_per_func: usize = 100;
    const total_target_execs = total_funcs * inputs_per_func; // 21,600
    var total_triple_matches: usize = 0;

    var timer = try std.time.Timer.start();

    for (funcs_buf[0..total_funcs], 0..) |func, idx| {
        // Compile directly via GenericJitEngine
        var jit_compiled = try generic_jit.GenericJitEngine.compile(func);
        defer jit_compiled.deinit();

        // Get the real compiled AOT function pointer from src/lin_mir_fuzz_compiled_aot.zig
        const aot_fn_ptr = compiled_aot.all_aot_fns[idx];

        for (0..inputs_per_func) |_| {
            const arg0 = rand.int(i64) & 0xFFFF;
            const arg1 = rand.int(i64) & 0xFFFF;

            // 1. MirVm
            var vm = engine.MirVm.init();
            const vm_res = try vm.execute(func, &[_]i64{ arg0, arg1 });

            // 2. Real Compiled AOT execution (Zig LLVM native)
            const aot_res = aot_fn_ptr(arg0, arg1);

            // 3. Generic JIT execution (RAM W^X)
            const jit_res = jit_compiled.fn_ptr(arg0, arg1);

            if (vm_res == aot_res and aot_res == jit_res) {
                total_triple_matches += 1;
            } else {
                std.debug.print("[FAIL] Mismatch in {s}: VM={d}, AOT={d}, JIT={d}\n", .{ func.name, vm_res, aot_res, jit_res });
                return error.TripleMismatch;
            }
        }
    }

    const elapsed_ns = timer.read();
    const rate = (@as(f64, @floatFromInt(total_target_execs)) / @as(f64, @floatFromInt(elapsed_ns))) * 1000.0;

    try stdout.print("[FUZZING SUMMARY] 21,600 Full Triple Executions Verified Across All 216 Operator Permutations:\n", .{});
    try stdout.print("                  Total Operator Permutations: {d} (All 6^3 Permutations)\n", .{total_funcs});
    try stdout.print("                  Inputs Tested Per Program:   {d}\n", .{inputs_per_func});
    try stdout.print("                  Total Triple Executions:     {d}\n", .{total_target_execs});
    try stdout.print("                  Triple Matches:              {d} (100.0% Exact Parity VM == CompiledAOT == GenericJit)\n", .{total_triple_matches});
    try stdout.print("                  Total Execution Time:        {d:.2} ms ({d:.2} M executions/s)\n", .{ @as(f64, @floatFromInt(elapsed_ns)) / 1_000_000.0, rate });
    try stdout.print("                  Triple Divergences:          0\n\n", .{});
    try stdout.print("================================================================================\n", .{});
    try stdout.print("=== GATE PASS: LIN-MIR-FUZZ-005B (100% COMPILED AOT == VM == GENERIC JIT) ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});
}
