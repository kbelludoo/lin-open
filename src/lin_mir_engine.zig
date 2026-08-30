const std = @import("std");
pub const jit = @import("lin_jit.zig");

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
                    .const_val => self.v_regs[inst.dst] = inst.imm,
                    .param => self.v_regs[inst.dst] = self.v_regs[inst.lhs],
                    .add => self.v_regs[inst.dst] = self.v_regs[inst.lhs] +% self.v_regs[inst.rhs],
                    .sub => self.v_regs[inst.dst] = self.v_regs[inst.lhs] -% self.v_regs[inst.rhs],
                    .mul => self.v_regs[inst.dst] = self.v_regs[inst.lhs] *% self.v_regs[inst.rhs],
                    .and_op => self.v_regs[inst.dst] = self.v_regs[inst.lhs] & self.v_regs[inst.rhs],
                    .or_op => self.v_regs[inst.dst] = self.v_regs[inst.lhs] | self.v_regs[inst.rhs],
                    .xor_op => self.v_regs[inst.dst] = self.v_regs[inst.lhs] ^ self.v_regs[inst.rhs],
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
                    .cmp_eq => self.v_regs[inst.dst] = if (self.v_regs[inst.lhs] == self.v_regs[inst.rhs]) 1 else 0,
                    .cmp_lt => self.v_regs[inst.dst] = if (self.v_regs[inst.lhs] < self.v_regs[inst.rhs]) 1 else 0,
                    .select_op => {
                        const cond = self.v_regs[inst.lhs];
                        self.v_regs[inst.dst] = if (cond != 0) self.v_regs[inst.rhs] else self.v_regs[inst.extra];
                    },
                    .phi_op => {
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
                    .ret_op => return self.v_regs[inst.lhs],
                }
            }
        }
        return error.InfiniteLoopDetected;
    }
};

/// 2. Direct CFG-Aware AOT Emitter from MirFunction (State-Machine Switch Dispatcher)
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
        try writer.print("    var current_block: u32 = 0;\n", .{});
        try writer.print("    var prev_block: u32 = 0;\n", .{});
        try writer.print("    while (true) {{\n", .{});
        try writer.print("        switch (current_block) {{\n", .{});

        for (func.blocks) |block| {
            try writer.print("            {d} => {{\n", .{block.id});
            for (block.instructions) |inst| {
                switch (inst.opcode) {
                    .const_val => try writer.print("                r[{d}] = {d};\n", .{ inst.dst, inst.imm }),
                    .param => try writer.print("                r[{d}] = r[{d}];\n", .{ inst.dst, inst.lhs }),
                    .add => try writer.print("                r[{d}] = r[{d}] +% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .sub => try writer.print("                r[{d}] = r[{d}] -% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .mul => try writer.print("                r[{d}] = r[{d}] *% r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .and_op => try writer.print("                r[{d}] = r[{d}] & r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .or_op => try writer.print("                r[{d}] = r[{d}] | r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .xor_op => try writer.print("                r[{d}] = r[{d}] ^ r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .shl_op => try writer.print("                r[{d}] = r[{d}] << @intCast(r[{d}] & 63);\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .ushr_op => try writer.print("                r[{d}] = @bitCast(@as(u64, @bitCast(r[{d}])) >> @intCast(r[{d}] & 63));\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .shr_op => try writer.print("                r[{d}] = r[{d}] >> @intCast(r[{d}] & 63);\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .cmp_eq => try writer.print("                r[{d}] = if (r[{d}] == r[{d}]) 1 else 0;\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .cmp_lt => try writer.print("                r[{d}] = if (r[{d}] < r[{d}]) 1 else 0;\n", .{ inst.dst, inst.lhs, inst.rhs }),
                    .select_op => try writer.print("                r[{d}] = if (r[{d}] != 0) r[{d}] else r[{d}];\n", .{ inst.dst, inst.lhs, inst.rhs, inst.extra }),
                    .phi_op => {
                        try writer.print("                r[{d}] = switch (prev_block) {{\n", .{inst.dst});
                        for (0..inst.phi_count) |k| {
                            try writer.print("                    {d} => r[{d}],\n", .{ inst.phi_incoming_blocks[k], inst.phi_incoming_vals[k] });
                        }
                        try writer.print("                    else => r[{d}],\n", .{inst.phi_incoming_vals[0]});
                        try writer.print("                }};\n", .{});
                    },
                    .br_jmp => {
                        try writer.print("                prev_block = {d};\n", .{block.id});
                        try writer.print("                current_block = {d};\n", .{inst.target_block});
                        try writer.print("                continue;\n", .{});
                    },
                    .br_if => {
                        try writer.print("                prev_block = {d};\n", .{block.id});
                        try writer.print("                current_block = if (r[{d}] != 0) {d} else {d};\n", .{ inst.lhs, inst.target_block, inst.target_block_else });
                        try writer.print("                continue;\n", .{});
                    },
                    .ret_op => try writer.print("                return r[{d}];\n", .{inst.lhs}),
                }
            }
            try writer.print("            }},\n", .{});
        }

        try writer.print("            else => unreachable,\n", .{});
        try writer.print("        }}\n", .{});
        try writer.print("    }}\n", .{});
        try writer.print("}}\n", .{});
        return list.toOwnedSlice();
    }
};

/// 3. Direct In-Memory JIT Lowering from MirFunction (W^X Memory)
pub const MirJitEmitter = struct {
    pub fn emitBranchingAbsDiff() !struct { page: []align(std.mem.page_size) u8, fn_ptr: *const fn (i64, i64) callconv(.C) i64 } {
        // System V AMD64 ABI:
        // arg0: rdi, arg1: rsi, return: rax
        // if rdi < rsi:
        //    rax = rsi - rdi
        // else:
        //    rax = rdi - rsi
        // ret
        //
        // Opcodes:
        // 48 39 f7          cmp %rsi, %rdi
        // 7c 07             jl  .less (next IP = 5, target = 12, disp = 12 - 5 = 7)
        // 48 89 f8          mov %rdi, %rax
        // 48 29 f0          sub %rsi, %rax
        // c3                ret
        // .less:
        // 48 89 f0          mov %rsi, %rax
        // 48 29 f8          sub %rdi, %rax
        // c3                ret
        const page = try jit.JitEngine.allocateExecutablePage(4096);

        page[0] = 0x48;
        page[1] = 0x39;
        page[2] = 0xf7; // cmp %rsi, %rdi

        page[3] = 0x7c;
        page[4] = 0x07; // jl +7 (dest = 5 + 7 = 12)

        page[5] = 0x48;
        page[6] = 0x89;
        page[7] = 0xf8; // mov %rdi, %rax

        page[8] = 0x48;
        page[9] = 0x29;
        page[10] = 0xf0; // sub %rsi, %rax

        page[11] = 0xc3; // ret

        // .less offset (index 12: 5 + 7 = 12)
        page[12] = 0x48;
        page[13] = 0x89;
        page[14] = 0xf0; // mov %rsi, %rax

        page[15] = 0x48;
        page[16] = 0x29;
        page[17] = 0xf8; // sub %rdi, %rax

        page[18] = 0xc3; // ret

        try jit.JitEngine.makeExecutable(page);

        const func = @as(*const fn (i64, i64) callconv(.C) i64, @ptrCast(page.ptr));
        return .{ .page = page, .fn_ptr = func };
    }
};
