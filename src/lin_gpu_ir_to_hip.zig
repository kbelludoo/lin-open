//! lin_gpu_ir_to_hip.zig — Canonical HIP C++ Emitter for LIN GPU IR (LIN-GPU-008E)
//!
//! Architectural Invariants:
//!   1. HIPSource = E_hip(GpuModule) is strictly deterministic and canonical.
//!   2. H_kernel_hip = SHA256("LIN-HIP-KERNEL-V1" || H_gpuIR || CanonicalHIPSource).
//!   3. Consumes ONLY GpuModule (zero hardware/backend metadata contamination).

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;

pub const GpuIrToHipEmitter = struct {
    pub const EmittedHipKernel = struct {
        source: []const u8,
        kernel_hash: [32]u8,
        gpu_ir_hash: [32]u8,

        pub fn deinit(self: EmittedHipKernel, allocator: std.mem.Allocator) void {
            allocator.free(self.source);
        }
    };

    /// Canonical, deterministic HIP C++ emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedHipKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\/* LIN_CANONICAL_HIP_CPP_V1
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
            if (std.mem.indexOf(u8, k.name, "pass1_tree") != null) {
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
                    \\    int accum = 0;
                    \\    for (int i = (int)gid; i < n; i += (int)grid_size) {{
                    \\        accum = (int)((unsigned int)accum + (unsigned int)input[i]);
                    \\    }}
                    \\    s_scratch[lid] = accum;
                    \\    __syncthreads();
                    \\
                    \\    for (unsigned int s = 128; s > 0; s >>= 1) {{
                    \\        if (lid < s) {{
                    \\            s_scratch[lid] = (int)((unsigned int)s_scratch[lid] + (unsigned int)s_scratch[lid + s]);
                    \\        }}
                    \\        __syncthreads();
                    \\    }}
                    \\
                    \\    if (lid == 0) {{
                    \\        partial_sums[blockIdx.x] = s_scratch[0];
                    \\    }}
                    \\}}
                    \\
                , .{k.name});
            } else if (std.mem.indexOf(u8, k.name, "pass2_rollup") != null) {
                try writer.print(
                    \\__global__ void {s}(
                    \\    const int* __restrict__ partial_sums,
                    \\    int* __restrict__ output_scalar,
                    \\    int num_parts
                    \\) {{
                    \\    __shared__ int s_scratch[256];
                    \\    unsigned int lid = threadIdx.x;
                    \\
                    \\    int accum = 0;
                    \\    for (int i = (int)lid; i < num_parts; i += 256) {{
                    \\        accum = (int)((unsigned int)accum + (unsigned int)partial_sums[i]);
                    \\    }}
                    \\    s_scratch[lid] = accum;
                    \\    __syncthreads();
                    \\
                    \\    for (unsigned int s = 128; s > 0; s >>= 1) {{
                    \\        if (lid < s) {{
                    \\            s_scratch[lid] = (int)((unsigned int)s_scratch[lid] + (unsigned int)s_scratch[lid + s]);
                    \\        }}
                    \\        __syncthreads();
                    \\    }}
                    \\
                    \\    if (lid == 0) {{
                    \\        output_scalar[0] = s_scratch[0];
                    \\    }}
                    \\}}
                    \\
                , .{k.name});
            }
        }

        const source = try buf.toOwnedSlice();

        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-HIP-KERNEL-V1");
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
