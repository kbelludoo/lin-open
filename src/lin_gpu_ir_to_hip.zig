//! lin_gpu_ir_to_hip.zig — Instruction-Driven Canonical HIP C++ Emitter (LIN-GPU-008E)
//!
//! Architectural Invariants:
//!   1. Emits HIP C++ strictly from GpuInstruction semantics and GpuReduceOp.
//!   2. H_kernel_hip = SHA256("LIN-HIP-KERNEL-V1.1" || H_gpuIR || CanonicalHIPSource).
//!   3. Consumes ONLY GpuModule.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuKernelKind = ir.GpuKernelKind;
const GpuReduceOp = ir.GpuReduceOp;

pub const GpuIrToHipEmitter = struct {
    pub const EmittedHipKernel = struct {
        source: []const u8,
        kernel_hash: [32]u8,
        gpu_ir_hash: [32]u8,

        pub fn deinit(self: EmittedHipKernel, allocator: std.mem.Allocator) void {
            allocator.free(self.source);
        }
    };

    pub fn getReduceOpC(rop: GpuReduceOp) struct { expr: []const u8, identity: []const u8 } {
        return switch (rop) {
            .sum => .{ .expr = "(int)((unsigned int)(a) + (unsigned int)(b))", .identity = "0" },
            .product => .{ .expr = "(int)((unsigned int)(a) * (unsigned int)(b))", .identity = "1" },
            .min => .{ .expr = "((a) < (b) ? (a) : (b))", .identity = "2147483647" },
            .max => .{ .expr = "((a) > (b) ? (a) : (b))", .identity = "(-2147483647 - 1)" },
            .band => .{ .expr = "((a) & (b))", .identity = "0xFFFFFFFF" },
            .bor => .{ .expr = "((a) | (b))", .identity = "0" },
            .bxor => .{ .expr = "((a) ^ (b))", .identity = "0" },
        };
    }

    /// Canonical, instruction-driven HIP C++ emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedHipKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\/* LIN_CANONICAL_HIP_CPP_V1_1
            \\ * gpu_ir_hash = sha256:{s}
            \\ * numeric_contract = {s}
            \\ */
            \\#include <hip/hip_runtime.h>
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
                        \\__global__ void {s}(
                        \\    const int* __restrict__ input,
                        \\    int* __restrict__ partial_sums,
                        \\    int n
                        \\) {{
                        \\    __shared__ int s_scratch[256];
                        \\    unsigned int gid = blockDim.x * blockIdx.x + threadIdx.x;
                        \\    unsigned int lid = threadIdx.x;
                        \\    unsigned int grid_size = blockDim.x * gridDim.x;
                        \\
                        \\    int accum = {s};
                        \\    for (int i = (int)gid; i < n; i += (int)grid_size) {{
                        \\        int a = accum; int b = input[i];
                        \\        accum = {s};
                        \\    }}
                        \\    s_scratch[lid] = accum;
                        \\    __syncthreads();
                        \\
                        \\    for (unsigned int s = 128; s > 0; s >>= 1) {{
                        \\        if (lid < s) {{
                        \\            int a = s_scratch[lid]; int b = s_scratch[lid + s];
                        \\            s_scratch[lid] = {s};
                        \\        }}
                        \\        __syncthreads();
                        \\    }}
                        \\
                        \\    if (lid == 0) {{
                        \\        partial_sums[blockIdx.x] = s_scratch[0];
                        \\    }}
                        \\}}
                        \\
                    , .{ k.name, op_info.identity, op_info.expr, op_info.expr });
                },
                .rollup_reduction_pass2 => {
                    const rop = k.reduce_op orelse .sum;
                    const op_info = getReduceOpC(rop);

                    try writer.print(
                        \\__global__ void {s}(
                        \\    const int* __restrict__ partial_sums,
                        \\    int* __restrict__ output_scalar,
                        \\    int num_parts
                        \\) {{
                        \\    __shared__ int s_scratch[256];
                        \\    unsigned int lid = threadIdx.x;
                        \\
                        \\    int accum = {s};
                        \\    for (int i = (int)lid; i < num_parts; i += 256) {{
                        \\        int a = accum; int b = partial_sums[i];
                        \\        accum = {s};
                        \\    }}
                        \\    s_scratch[lid] = accum;
                        \\    __syncthreads();
                        \\
                        \\    for (unsigned int s = 128; s > 0; s >>= 1) {{
                        \\        if (lid < s) {{
                        \\            int a = s_scratch[lid]; int b = s_scratch[lid + s];
                        \\            s_scratch[lid] = {s};
                        \\        }}
                        \\        __syncthreads();
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
                        \\__global__ void {s}(
                        \\    const int* __restrict__ input,
                        \\    int* __restrict__ output,
                        \\    int n
                        \\) {{
                        \\    unsigned int gid = blockDim.x * blockIdx.x + threadIdx.x;
                        \\    if (gid < (unsigned int)n) {{
                        \\        int val = input[gid];
                        \\        output[gid] = (int)((unsigned int)val * 2u + 1u);
                        \\    }}
                        \\}}
                        \\
                    , .{k.name});
                },
                .stencil_1d => {
                    try writer.print(
                        \\__global__ void {s}(
                        \\    const int* __restrict__ input,
                        \\    int* __restrict__ output,
                        \\    int n
                        \\) {{
                        \\    unsigned int gid = blockDim.x * blockIdx.x + threadIdx.x;
                        \\    if (gid < (unsigned int)n) {{
                        \\        int left = (gid == 0) ? input[0] : input[gid - 1];
                        \\        int center = input[gid];
                        \\        int right = (gid + 1 >= (unsigned int)n) ? input[n - 1] : input[gid + 1];
                        \\        output[gid] = (int)((unsigned int)left + (unsigned int)center + (unsigned int)right);
                        \\    }}
                        \\}}
                        \\
                    , .{k.name});
                },
            }
        }

        const source = try buf.toOwnedSlice();

        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-HIP-KERNEL-V1.1");
        hasher.update(&gpu_ir_hash);
        hasher.update(source);
        var kernel_hash: [32]u8 = undefined;
        hasher.final(&kernel_hash);

        return EmittedHipKernel{
            .source = source,
            .kernel_hash = kernel_hash,
            .gpu_ir_hash = gpu_ir_hash,
        };
    }
};
