//! lin_gpu_ir.zig — Semantic Instruction-Driven LIN GPU IR v1.1 (LIN-GPU-008A-IR2)
//!
//! Architectural Invariants:
//!   1. "O emitter é um tradutor puro de sequências de GpuInstruction; nunca inspeciona nomes mágicos de kernel."
//!   2. GpuInstruction expressa explicitamente reduce_op, constantes imediatas e offsets.
//!   3. Totalmente target-neutral: zero menções a vendors de GPU.

const std = @import("std");

pub const GpuAddressSpace = enum(u8) {
    generic = 1,
    global = 2,
    workgroup_local = 3,
    private = 4,
};

pub const GpuDataType = enum(u8) {
    i32 = 1,
    u32 = 2,
    i64 = 3,
    u64 = 4,
    f32 = 5,
    f64 = 6,
    bool = 7,
};

pub const GpuReduceOp = enum(u8) {
    sum = 1,
    product = 2,
    min = 3,
    max = 4,
    band = 5,
    bor = 6,
    bxor = 7,
};

pub const GpuOp = enum(u8) {
    parallel_for = 1,
    load = 2,
    load_offset = 3,
    store = 4,
    constant = 5,
    add = 6,
    sub = 7,
    mul = 8,
    div = 9,
    reduce = 10,
    barrier = 11,
    index = 12,
    cast = 13,
};

pub const NumericContract = enum(u8) {
    modular_i32 = 1,
    modular_u32 = 2,
    ieee754_strict = 3,
};

pub const GpuInstruction = struct {
    op: GpuOp,
    result: ?u32 = null,
    operands: [4]u32 = [_]u32{ 0, 0, 0, 0 },
    operand_count: u8 = 0,
    data_type: GpuDataType = .i32,
    address_space: ?GpuAddressSpace = null,
    immediate_raw: i64 = 0,
    offset: i32 = 0,
    reduce_op: ?GpuReduceOp = null,
};

pub const GpuKernelKind = enum(u8) {
    elementwise_map = 1,
    tree_reduction_pass1 = 2,
    rollup_reduction_pass2 = 3,
    stencil_1d = 4,
};

pub const GpuKernel = struct {
    name: []const u8,
    kind: GpuKernelKind,
    workgroup_size: [3]u32 = [_]u32{ 256, 1, 1 },
    instructions: []const GpuInstruction,
    arg_types: []const GpuDataType,
    arg_spaces: []const GpuAddressSpace,
    requires_local_scratch: bool = false,
    local_scratch_bytes: usize = 0,
    reduce_op: ?GpuReduceOp = null,
};

pub const GpuModule = struct {
    schema_version: u32 = 2,
    name: []const u8 = "lin_gpu_module_v1_1",
    kernels: []const GpuKernel,
    numeric_contract: NumericContract = .modular_i32,

    /// Computes the canonical GPU IR hash H_gpuIR (v1.1)
    pub fn computeGpuIrHash(self: GpuModule) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-GPU-IR-V1.1");
        hasher.update(std.mem.asBytes(&self.schema_version));
        hasher.update(self.name);
        hasher.update(&[_]u8{@intFromEnum(self.numeric_contract)});

        for (self.kernels) |k| {
            hasher.update(k.name);
            hasher.update(&[_]u8{@intFromEnum(k.kind)});
            hasher.update(std.mem.asBytes(&k.workgroup_size));
            hasher.update(&[_]u8{if (k.requires_local_scratch) 1 else 0});
            hasher.update(std.mem.asBytes(&k.local_scratch_bytes));
            if (k.reduce_op) |rop| {
                hasher.update(&[_]u8{@intFromEnum(rop)});
            } else {
                hasher.update(&[_]u8{0xFF});
            }

            for (k.arg_types, k.arg_spaces) |t, s| {
                hasher.update(&[_]u8{@intFromEnum(t)});
                hasher.update(&[_]u8{@intFromEnum(s)});
            }

            for (k.instructions) |inst| {
                hasher.update(&[_]u8{@intFromEnum(inst.op)});
                if (inst.result) |res| {
                    hasher.update(std.mem.asBytes(&res));
                } else {
                    hasher.update(&[_]u8{0xFF});
                }
                hasher.update(&[_]u8{inst.operand_count});
                hasher.update(std.mem.asBytes(&inst.operands));
                hasher.update(&[_]u8{@intFromEnum(inst.data_type)});
                if (inst.address_space) |space| {
                    hasher.update(&[_]u8{@intFromEnum(space)});
                } else {
                    hasher.update(&[_]u8{0xFF});
                }
                hasher.update(std.mem.asBytes(&inst.immediate_raw));
                hasher.update(std.mem.asBytes(&inst.offset));
                if (inst.reduce_op) |rop| {
                    hasher.update(&[_]u8{@intFromEnum(rop)});
                } else {
                    hasher.update(&[_]u8{0xFF});
                }
            }
        }

        var hash: [32]u8 = undefined;
        hasher.final(&hash);
        return hash;
    }
};
