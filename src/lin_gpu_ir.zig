//! lin_gpu_ir.zig — Canonical Declarative Target-Neutral LIN GPU IR (LIN-GPU-007A)
//!
//! Architectural Invariants:
//!   1. "GPU IR nunca conhece o backend; o emitter conhece o backend."
//!   2. Complete vendor neutrality (no OpenCL, HIP, CUDA, or gfx1030 constructs).
//!   3. H_gpuIR = SHA256("LIN-GPU-IR-V1" || schema_version || CanonicalEncode(GpuModule)).

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

pub const GpuOp = enum(u8) {
    parallel_for = 1,
    load = 2,
    store = 3,
    add = 4,
    sub = 5,
    mul = 6,
    div = 7,
    reduce = 8,
    barrier = 9,
    index = 10,
    cast = 11,
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
    data_type: GpuDataType,
    address_space: ?GpuAddressSpace = null,
    immediate_raw: i64 = 0,
};

pub const GpuKernel = struct {
    name: []const u8,
    workgroup_size: [3]u32 = [_]u32{ 256, 1, 1 },
    instructions: []const GpuInstruction,
    arg_types: []const GpuDataType,
    arg_spaces: []const GpuAddressSpace,
    requires_local_scratch: bool = false,
    local_scratch_bytes: usize = 0,
};

pub const GpuModule = struct {
    schema_version: u32 = 1,
    name: []const u8 = "lin_gpu_module",
    kernels: []const GpuKernel,
    numeric_contract: NumericContract = .modular_i32,

    /// Computes the canonical GPU IR hash H_gpuIR
    pub fn computeGpuIrHash(self: GpuModule) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-GPU-IR-V1");
        hasher.update(std.mem.asBytes(&self.schema_version));
        hasher.update(self.name);
        hasher.update(&[_]u8{@intFromEnum(self.numeric_contract)});

        for (self.kernels) |k| {
            hasher.update(k.name);
            hasher.update(std.mem.asBytes(&k.workgroup_size));
            hasher.update(&[_]u8{if (k.requires_local_scratch) 1 else 0});
            hasher.update(std.mem.asBytes(&k.local_scratch_bytes));

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
            }
        }

        var hash: [32]u8 = undefined;
        hasher.final(&hash);
        return hash;
    }
};
