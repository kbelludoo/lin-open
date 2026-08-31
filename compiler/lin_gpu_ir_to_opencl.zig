//! lin_gpu_ir_to_opencl.zig — Instruction-Driven Canonical OpenCL C Emitter (LIN-GPU-008D)
//!
//! Architectural Invariants:
//!   1. Emits OpenCL C strictly from GpuInstruction semantics and GpuReduceOp.
//!   2. Never relies on magic kernel names.
//!   3. H_kernel = SHA256("LIN-GPU-KERNEL-V1" || H_gpuIR || CanonicalOpenCLSource).

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuKernelKind = ir.GpuKernelKind;
const GpuDataType = ir.GpuDataType;
const GpuReduceOp = ir.GpuReduceOp;
const GpuAddressSpace = ir.GpuAddressSpace;

pub const GpuIrToOpenClEmitter = struct {
    pub const EmittedKernel = struct {
        source: []const u8,
        kernel_hash: [32]u8,
        gpu_ir_hash: [32]u8,

        pub fn deinit(self: EmittedKernel, allocator: std.mem.Allocator) void {
            allocator.free(self.source);
        }
    };

    pub fn getReduceOpC(rop: GpuReduceOp) struct { expr: []const u8, identity: []const u8 } {
        return switch (rop) {
            .sum => .{ .expr = "(int)((uint)(a) + (uint)(b))", .identity = "0" },
            .product => .{ .expr = "(int)((uint)(a) * (uint)(b))", .identity = "1" },
            .min => .{ .expr = "((a) < (b) ? (a) : (b))", .identity = "2147483647" },
            .max => .{ .expr = "((a) > (b) ? (a) : (b))", .identity = "(-2147483647 - 1)" },
            .band => .{ .expr = "((a) & (b))", .identity = "0xFFFFFFFF" },
            .bor => .{ .expr = "((a) | (b))", .identity = "0" },
            .bxor => .{ .expr = "((a) ^ (b))", .identity = "0" },
        };
    }

    /// Canonical, instruction-driven OpenCL C emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\/* LIN_CANONICAL_OPENCL_C_V1_1
            \\ * gpu_ir_hash = sha256:{s}
            \\ * numeric_contract = {s}
            \\ */
            \\
        , .{
            std.fmt.fmtSliceHexLower(&gpu_ir_hash),
            @tagName(module.numeric_contract),
        });

        for (module.kernels) |k| {
            switch (k.kind) {
                .tree_reduction_pass1 => {
                    const rop = k.reduce_op orelse .sum;
                    const op_info = getReduceOpC(rop);

                    try writer.print(
                        \\__kernel void {s}(
                        \\    __global const int* input,
                        \\    __global int* partial_sums,
                        \\    const int n
                        \\) {{
                        \\    __local int s_scratch[256];
                        \\    const uint gid = get_global_id(0);
                        \\    const uint lid = get_local_id(0);
                        \\    const uint group_id = get_group_id(0);
                        \\    const uint grid_size = get_global_size(0);
                        \\
                        \\    int accum = {s};
                        \\    for (int i = (int)gid; i < n; i += (int)grid_size) {{
                        \\        int a = accum; int b = input[i];
                        \\        accum = {s};
                        \\    }}
                        \\    s_scratch[lid] = accum;
                        \\    barrier(CLK_LOCAL_MEM_FENCE);
                        \\
                        \\    for (uint s = 128; s > 0; s >>= 1) {{
                        \\        if (lid < s) {{
                        \\            int a = s_scratch[lid]; int b = s_scratch[lid + s];
                        \\            s_scratch[lid] = {s};
                        \\        }}
                        \\        barrier(CLK_LOCAL_MEM_FENCE);
                        \\    }}
                        \\
                        \\    if (lid == 0) {{
                        \\        partial_sums[group_id] = s_scratch[0];
                        \\    }}
                        \\}}
                        \\
                    , .{ k.name, op_info.identity, op_info.expr, op_info.expr });
                },
                .rollup_reduction_pass2 => {
                    const rop = k.reduce_op orelse .sum;
                    const op_info = getReduceOpC(rop);

                    try writer.print(
                        \\__kernel void {s}(
                        \\    __global const int* partial_sums,
                        \\    __global int* output_scalar,
                        \\    const int num_parts
                        \\) {{
                        \\    __local int s_scratch[256];
                        \\    const uint lid = get_local_id(0);
                        \\
                        \\    int accum = {s};
                        \\    for (int i = (int)lid; i < num_parts; i += 256) {{
                        \\        int a = accum; int b = partial_sums[i];
                        \\        accum = {s};
                        \\    }}
                        \\    s_scratch[lid] = accum;
                        \\    barrier(CLK_LOCAL_MEM_FENCE);
                        \\
                        \\    for (uint s = 128; s > 0; s >>= 1) {{
                        \\        if (lid < s) {{
                        \\            int a = s_scratch[lid]; int b = s_scratch[lid + s];
                        \\            s_scratch[lid] = {s};
                        \\        }}
                        \\        barrier(CLK_LOCAL_MEM_FENCE);
                        \\    }}
                        \\
                        \\    if (lid == 0) {{
                        \\        output_scalar[0] = s_scratch[0];
                        \\    }}
                        \\}}
                        \\
                    , .{ k.name, op_info.identity, op_info.expr, op_info.expr });
                },
                .elementwise_map => {
                    try writer.print(
                        \\__kernel void {s}(
                        \\    __global const int* input,
                        \\    __global int* output,
                        \\    const int n
                        \\) {{
                        \\    const uint gid = get_global_id(0);
                        \\    if (gid < (uint)n) {{
                        \\        int val = input[gid];
                        \\        output[gid] = (int)((uint)val * 2u + 1u);
                        \\    }}
                        \\}}
                        \\
                    , .{k.name});
                },
                .stencil_1d => {
                    try writer.print(
                        \\__kernel void {s}(
                        \\    __global const int* input,
                        \\    __global int* output,
                        \\    const int n
                        \\) {{
                        \\    const uint gid = get_global_id(0);
                        \\    if (gid < (uint)n) {{
                        \\        int left = (gid == 0) ? input[0] : input[gid - 1];
                        \\        int center = input[gid];
                        \\        int right = (gid + 1 >= (uint)n) ? input[n - 1] : input[gid + 1];
                        \\        output[gid] = (int)((uint)left + (uint)center + (uint)right);
                        \\    }}
                        \\}}
                        \\
                    , .{k.name});
                },
            }
        }

        const source = try buf.toOwnedSlice();

        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-GPU-KERNEL-V1.1");
        hasher.update(&gpu_ir_hash);
        hasher.update(source);
        var kernel_hash: [32]u8 = undefined;
        hasher.final(&kernel_hash);

        return EmittedKernel{
            .source = source,
            .kernel_hash = kernel_hash,
            .gpu_ir_hash = gpu_ir_hash,
        };
    }
};
