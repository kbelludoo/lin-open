const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");

pub fn main() !void {
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

    var list = std.ArrayList(u8).init(alloc);
    const writer = list.writer();

    try writer.print("// AUTO-GENERATED COMPILED AOT MODULE FOR LIN-MIR-FUZZ-005B\n", .{});
    try writer.print("const std = @import(\"std\");\n\n", .{});

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

                const aot_code = try engine.MirAotEmitter.emitToZigString(alloc, func);
                try writer.print("{s}\n", .{aot_code});
                alloc.free(aot_code);

                f_idx += 1;
            }
        }
    }

    // Now write the dispatcher table: pub const all_aot_fns = [_]*const fn(i64, i64) i64 { ... };
    try writer.print("pub const all_aot_fns = [_]*const fn(i64, i64) i64{{\n", .{});
    for (0..216) |i| {
        try writer.print("    fuzz_fn_{d},\n", .{i});
    }
    try writer.print("}};\n", .{});

    const file = try std.fs.cwd().createFile("src/lin_mir_fuzz_compiled_aot.zig", .{});
    try file.writeAll(list.items);
    file.close();

    std.debug.print("Successfully generated src/lin_mir_fuzz_compiled_aot.zig with 216 functions + function table!\n", .{});
}
