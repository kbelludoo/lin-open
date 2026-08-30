const std = @import("std");
const jit = @import("lin_jit.zig");

pub const MirType = enum {
    i1,
    i32,
    u32,
    i64,
    u64,
    f64,
    ptr,
    v8u32,
};

pub const MirOpcode = enum {
    const_val,
    param,
    add,
    sub,
    mul,
    and_op,
    or_op,
    xor_op,
    shl_op,
    ushr_op,
    shr_op,
    cmp_eq,
    cmp_lt,
    select_op,
    phi_op,
    br_jmp,
    br_if,
    ret_op,
};

pub const MirInst = struct {
    opcode: MirOpcode,
    ty: MirType,
    dst: u32 = 0,
    imm: i64 = 0,
    lhs: u32 = 0,
    rhs: u32 = 0,
    extra: u32 = 0,
    target_block: u32 = 0,
    target_block_else: u32 = 0,
    phi_incoming_blocks: [4]u32 = [_]u32{0} ** 4,
    phi_incoming_vals: [4]u32 = [_]u32{0} ** 4,
    phi_count: u8 = 0,
};

pub const MirBlock = struct {
    id: u32,
    instructions: []const MirInst,
};

pub const MirFunction = struct {
    name: []const u8,
    params: []const MirType,
    returns: MirType,
    blocks: []const MirBlock,
};

/// 1. True CFG & PHI-Aware Interpreter (Oracle 1: MirVm)
pub const MirVm = struct {
    v_regs: [256]i64 = [_]i64{0} ** 256,
    prev_block_id: u32 = 0,

    pub fn init() MirVm {
        return .{};
    }

    pub fn execute(self: *MirVm, func: MirFunction, args: []const i64) !i64 {
        for (args, 0..) |arg, i| {
            if (i < 256) self.v_regs[i] = arg;
        }

        var current_block_id: u32 = 0;
        var iterations: usize = 0;

        while (iterations < 100_000) : (iterations += 1) {
            // Find block with id
            var found_block: ?MirBlock = null;
            for (func.blocks) |b| {
                if (b.id == current_block_id) {
                    found_block = b;
                    break;
                }
            }
            if (found_block == null) return error.BlockNotFound;
            const block = found_block.?;

            for (block.instructions) |inst| {
                switch (inst.opcode) {
                    .const_val => {
                        self.v_regs[inst.dst] = inst.imm;
                    },
                    .param => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs];
                    },
                    .add => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] +% self.v_regs[inst.rhs];
                    },
                    .sub => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] -% self.v_regs[inst.rhs];
                    },
                    .mul => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] *% self.v_regs[inst.rhs];
                    },
                    .and_op => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] & self.v_regs[inst.rhs];
                    },
                    .or_op => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] | self.v_regs[inst.rhs];
                    },
                    .xor_op => {
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] ^ self.v_regs[inst.rhs];
                    },
                    .shl_op => {
                        const shift: u6 = @intCast(self.v_regs[inst.rhs] & 63);
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] << shift;
                    },
                    .ushr_op => {
                        const shift: u6 = @intCast(self.v_regs[inst.rhs] & 63);
                        const u_val: u64 = @bitCast(self.v_regs[inst.lhs]);
                        self.v_regs[inst.dst] = @bitCast(u_val >> shift);
                    },
                    .shr_op => {
                        const shift: u6 = @intCast(self.v_regs[inst.rhs] & 63);
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs] >> shift;
                    },
                    .cmp_eq => {
                        self.v_regs[inst.dst] = if (self.v_regs[inst.lhs] == self.v_regs[inst.rhs]) 1 else 0;
                    },
                    .cmp_lt => {
                        self.v_regs[inst.dst] = if (self.v_regs[inst.lhs] < self.v_regs[inst.rhs]) 1 else 0;
                    },
                    .select_op => {
                        const cond = self.v_regs[inst.lhs];
                        self.v_regs[inst.dst] = if (cond != 0) self.v_regs[inst.rhs] else self.v_regs[inst.extra];
                    },
                    .phi_op => {
                        // True PHI predecessor resolution
                        var resolved = false;
                        for (0..inst.phi_count) |k| {
                            if (inst.phi_incoming_blocks[k] == self.prev_block_id) {
                                const reg = inst.phi_incoming_vals[k];
                                self.v_regs[inst.dst] = self.v_regs[reg];
                                resolved = true;
                                break;
                            }
                        }
                        if (!resolved and inst.phi_count > 0) {
                            self.v_regs[inst.dst] = self.v_regs[inst.phi_incoming_vals[0]];
                        }
                    },
                    .br_jmp => {
                        self.prev_block_id = current_block_id;
                        current_block_id = inst.target_block;
                        break;
                    },
                    .br_if => {
                        self.prev_block_id = current_block_id;
                        const cond = self.v_regs[inst.lhs];
                        current_block_id = if (cond != 0) inst.target_block else inst.target_block_else;
                        break;
                    },
                    .ret_op => {
                        return self.v_regs[inst.lhs];
                    },
                }
            }
        }
        return error.InfiniteLoopDetected;
    }
};

/// 2. Direct Lowering of MirFunction to AOT Zig Code in Memory
pub const MirAotEmitter = struct {
    pub fn emitToZigString(allocator: std.mem.Allocator, func: MirFunction) ![]const u8 {
        var list = std.ArrayList(u8).init(allocator);
        const writer = list.writer();

        try writer.print("pub fn {s}(", .{func.name});
        for (func.params, 0..) |_, i| {
            if (i > 0) try writer.print(", ", .{});
            try writer.print("arg{d}: i64", .{i});
        }
        try writer.print(") i64 {{\n", .{});
        try writer.print("    var r: [256]i64 = [_]i64{{0}} ** 256;\n", .{});
        for (func.params, 0..) |_, i| {
            try writer.print("    r[{d}] = arg{d};\n", .{ i, i });
        }

        for (func.blocks) |block| {
            try writer.print("    // Block {d}\n", .{block.id});
            for (block.instructions) |inst| {
                switch (inst.opcode) {
                    .const_val => try writer.print("    r[{d}] = {d};\n", .{ inst.dst, inst.imm }),
                    .param => try writer.print("    r[{d}] = r[{d}];\n", .{ inst.dst, inst.lhs }),
                    .add => try writer.print("    r[{d}] = r[{d}] +% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .sub => try writer.print("    r[{d}] = r[{d}] -% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .mul => try writer.print("    r[{d}] = r[{d}] *% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .and_op => try writer.print("    r[{d}] = r[{d}] & r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .or_op => try writer.print("    r[{d}] = r[{d}] | r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .xor_op => try writer.print("    r[{d}] = r[{d}] ^ r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .shl_op => try writer.print("    r[{d}] = r[{d}] << @intCast(r[{d}] & 63);\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .ushr_op => try writer.print("    r[{d}] = @bitCast(@as(u64, @bitCast(r[{d}])) >> @intCast(r[{d}] & 63));\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .shr_op => try writer.print("    r[{d}] = r[{d}] >> @intCast(r[{d}] & 63);\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .cmp_eq => try writer.print("    r[{d}] = if (r[{d}] == r[{d}]) 1 else 0;\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .cmp_lt => try writer.print("    r[{d}] = if (r[{d}] < r[{d}]) 1 else 0;\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .select_op => try writer.print("    r[{d}] = if (r[{d}] != 0) r[{d}] else r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs, inst.extra }),
                    .phi_op => try writer.print("    r[{d}] = r[{d}];\n", .{ inst.dst, inst.phi_incoming_vals[0] }),
                    .ret_op => try writer.print("    return r[{d}];\n", .{inst.lhs}),
                    else => {},
                }
            }
        }
        try writer.print("}}\n", .{});
        return list.toOwnedSlice();
    }
};
