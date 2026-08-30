const std = @import("std");
const mir_vm = @import("src/lin_mir_vm.zig");

pub fn main() !void {
    var vm = mir_vm.MirVm.init();

    // Construct a real concrete LIN-MIR Function:
    // fn test_calc(%p0: i64, %p1: i64) -> i64
    // Block 0:
    //   %0 = param %p0 (reg 0)
    //   %1 = param %p1 (reg 1)
    //   %2 = add.i64 %0, %1       ; 100 + 250 = 350
    //   %3 = const.i64 50         ; imm = 50
    //   %4 = mul.i64 %2, %3       ; 350 * 50 = 17500
    //   %5 = const.i64 10000
    //   %6 = cmp_lt.i64 %4, %5    ; 17500 < 10000 -> 0 (false)
    //   %7 = select.i64 %6, %4, %2; cond=0 -> %2 = 350
    //   ret %7
    const insts = [_]mir_vm.MirInst{
        .{ .opcode = .param, .ty = .i64, .dst = 0, .lhs = 0 },
        .{ .opcode = .param, .ty = .i64, .dst = 1, .lhs = 1 },
        .{ .opcode = .add, .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 3, .imm = 50 },
        .{ .opcode = .mul, .ty = .i64, .dst = 4, .lhs = 2, .rhs = 3 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 5, .imm = 10000 },
        .{ .opcode = .cmp_lt, .ty = .i64, .dst = 6, .lhs = 4, .rhs = 5 },
        .{ .opcode = .select_op, .ty = .i64, .dst = 7, .lhs = 6, .rhs = 4, .extra = 2 },
        .{ .opcode = .ret_op, .ty = .i64, .dst = 0, .lhs = 7 },
    };

    const block = mir_vm.MirBlock{
        .id = 0,
        .instructions = &insts,
    };

    const params = [_]mir_vm.MirType{ .i64, .i64 };
    const func = mir_vm.MirFunction{
        .name = "test_calc",
        .params = &params,
        .returns = .i64,
        .blocks = &[_]mir_vm.MirBlock{block},
    };

    const args = [_]i64{ 100, 250 };
    const res = try vm.execute(func, &args);

    std.debug.print("INDEPENDENT LIN-MIR VM EXECUTION RESULT: {d} (Expected 350)\n", .{res});
    if (res == 350) {
        std.debug.print("VM EXECUTION VERIFIED!\n", .{});
    } else {
        return error.VmResultMismatch;
    }
}
