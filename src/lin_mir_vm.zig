const std = @import("std");

pub const MirType = enum {
    i1,
    i32,
    i64,
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
    ret_op,
};

pub const MirValue = union(MirType) {
    i1: bool,
    i32: i32,
    i64: i64,
    f64: f64,
    ptr: usize,
    v8u32: @Vector(8, u32),
};

pub const MirInst = struct {
    opcode: MirOpcode,
    ty: MirType,
    dst: u32,
    imm: i64 = 0,
    lhs: u32 = 0,
    rhs: u32 = 0,
    extra: u32 = 0,
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

pub const MirVm = struct {
    v_regs: [256]i64 = [_]i64{0} ** 256,

    pub fn init() MirVm {
        return .{};
    }

    pub fn execute(self: *MirVm, func: MirFunction, args: []const i64) !i64 {
        // Load params into registers
        for (args, 0..) |arg, i| {
            self.v_regs[i] = arg;
        }

        for (func.blocks) |block| {
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
                        self.v_regs[inst.dst] = self.v_regs[inst.lhs];
                    },
                    .ret_op => {
                        return self.v_regs[inst.lhs];
                    },
                }
            }
        }
        return self.v_regs[0];
    }
};
