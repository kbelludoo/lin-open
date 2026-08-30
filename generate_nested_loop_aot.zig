const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const alloc = gpa.allocator();

    const b0_insts = [_]engine.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 }, // rows
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 }, // cols
        .{ .opcode = .const_val, .ty = .i64, .dst = 2, .imm = 0 }, // 0
        .{ .opcode = .const_val, .ty = .i64, .dst = 3, .imm = 1 }, // 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 },
    };

    var phi_tot_out = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 4, .phi_count = 2 };
    phi_tot_out.phi_incoming_blocks[0] = 0;
    phi_tot_out.phi_incoming_vals[0] = 2;
    phi_tot_out.phi_incoming_blocks[1] = 6;
    phi_tot_out.phi_incoming_vals[1] = 13;

    var phi_r = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 5, .phi_count = 2 };
    phi_r.phi_incoming_blocks[0] = 0;
    phi_r.phi_incoming_vals[0] = 2;
    phi_r.phi_incoming_blocks[1] = 6;
    phi_r.phi_incoming_vals[1] = 14;

    const b1_insts = [_]engine.MirInst{
        phi_tot_out,
        phi_r,
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 6, .lhs = 5, .rhs = 0 },
        .{ .opcode = .br_if, .ty = .i1, .lhs = 6, .target_block = 2, .target_block_else = 5 },
    };

    const b2_insts = [_]engine.MirInst{
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };

    var phi_tot_in = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 7, .phi_count = 2 };
    phi_tot_in.phi_incoming_blocks[0] = 2;
    phi_tot_in.phi_incoming_vals[0] = 4;
    phi_tot_in.phi_incoming_blocks[1] = 4;
    phi_tot_in.phi_incoming_vals[1] = 11;

    var phi_c = engine.MirInst{ .opcode = .phi_op, .ty = .i64, .dst = 8, .phi_count = 2 };
    phi_c.phi_incoming_blocks[0] = 2;
    phi_c.phi_incoming_vals[0] = 2;
    phi_c.phi_incoming_blocks[1] = 4;
    phi_c.phi_incoming_vals[1] = 12;

    const b3_insts = [_]engine.MirInst{
        phi_tot_in,
        phi_c,
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 9, .lhs = 8, .rhs = 1 },
        .{ .opcode = .br_if, .ty = .i1, .lhs = 9, .target_block = 4, .target_block_else = 6 },
    };

    const b4_insts = [_]engine.MirInst{
        .{ .opcode = .mul, .ty = .i64, .dst = 10, .lhs = 5, .rhs = 1 },
        .{ .opcode = .add, .ty = .i64, .dst = 11, .lhs = 7, .rhs = 3 },
        .{ .opcode = .add, .ty = .i64, .dst = 12, .lhs = 8, .rhs = 3 },
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 3 },
    };

    const b6_insts = [_]engine.MirInst{
        .{ .opcode = .add, .ty = .i64, .dst = 13, .lhs = 7, .rhs = 2 }, // copy %7 + 0 -> %13
        .{ .opcode = .add, .ty = .i64, .dst = 14, .lhs = 5, .rhs = 3 }, // r += 1
        .{ .opcode = .br_jmp, .ty = .i1, .target_block = 1 },
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
        .name = "nested_matrix_sum_aot",
        .params = &params,
        .returns = .i64,
        .blocks = &blocks,
    };

    const aot_code = try engine.MirAotEmitter.emitToZigString(alloc, func);
    defer alloc.free(aot_code);

    const f = try std.fs.cwd().createFile("src/lin_mir_nested_loop_aot_compiled.zig", .{});
    defer f.close();
    try f.writeAll(aot_code);
    std.debug.print("Emitted src/lin_mir_nested_loop_aot_compiled.zig!\n", .{});
}
