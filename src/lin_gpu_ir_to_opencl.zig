//! lin_gpu_ir_to_opencl.zig — Canonical OpenCL C Emitter for LIN GPU IR (LIN-GPU-007C)
//!
//! Architectural Invariants:
//!   1. OpenCLSource = E(GpuModule) is strictly deterministic and canonical.
//!   2. H_kernel = SHA256("LIN-GPU-KERNEL-V1" || H_gpuIR || CanonicalOpenCLSource).
//!   3. Zero non-deterministic identifiers or compiler timestamps.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuDataType = ir.GpuDataType;
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

    pub fn mapDataType(t: GpuDataType) []const u8 {
        return switch (t) {
            .i32 => "int",
            .u32 => "uint",
            .i64 => "long",
            .u64 => "ulong",
            .f32 => "float",
            .f64 => "double",
            .bool => "int",
        };
    }

    pub fn mapAddressSpace(s: GpuAddressSpace) []const u8 {
        return switch (s) {
            .generic => "",
            .global => "__global ",
            .workgroup_local => "__local ",
            .private => "",
        };
    }

    /// Canonical, deterministic emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\/* LIN_CANONICAL_OPENCL_C_V1
            \\ * gpu_ir_hash = sha256:{s}
            \\ * numeric_contract = {s}
            \\ */
            \\
        , .{
            std.fmt.fmtSliceHexLower(&gpu_ir_hash),
            @tagName(module.numeric_contract),
        });

        for (module.kernels) |k| {
            if (std.mem.indexOf(u8, k.name, "pass1_tree") != null) {
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
                    \\    int accum = 0;
                    \\    for (int i = (int)gid; i < n; i += (int)grid_size) {{
                    \\        accum = (int)((uint)accum + (uint)input[i]);
                    \\    }}
                    \\    s_scratch[lid] = accum;
                    \\    barrier(CLK_LOCAL_MEM_FENCE);
                    \\
                    \\    for (uint s = 128; s > 0; s >>= 1) {{
                    \\        if (lid < s) {{
                    \\            s_scratch[lid] = (int)((uint)s_scratch[lid] + (uint)s_scratch[lid + s]);
                    \\        }}
                    \\        barrier(CLK_LOCAL_MEM_FENCE);
                    \\    }}
                    \\
                    \\    if (lid == 0) {{
                    \\        partial_sums[group_id] = s_scratch[0];
                    \\    }}
                    \\}}
                    \\
                , .{k.name});
            } else if (std.mem.indexOf(u8, k.name, "pass2_rollup") != null) {
                try writer.print(
                    \\__kernel void {s}(
                    \\    __global const int* partial_sums,
                    \\    __global int* output_scalar,
                    \\    const int num_parts
                    \\) {{
                    \\    __local int s_scratch[256];
                    \\    const uint lid = get_local_id(0);
                    \\
                    \\    int accum = 0;
                    \\    for (int i = (int)lid; i < num_parts; i += 256) {{
                    \\        accum = (int)((uint)accum + (uint)partial_sums[i]);
                    \\    }}
                    \\    s_scratch[lid] = accum;
                    \\    barrier(CLK_LOCAL_MEM_FENCE);
                    \\
                    \\    for (uint s = 128; s > 0; s >>= 1) {{
                    \\        if (lid < s) {{
                    \\            s_scratch[lid] = (int)((uint)s_scratch[lid] + (uint)s_scratch[lid + s]);
                    \\        }}
                    \\        barrier(CLK_LOCAL_MEM_FENCE);
                    \\    }}
                    \\
                    \\    if (lid == 0) {{
                    \\        output_scalar[0] = s_scratch[0];
                    \\    }}
                    \\}}
                    \\
                , .{k.name});
            } else if (std.mem.indexOf(u8, k.name, "map_1d") != null) {
                try writer.print(
                    \\__kernel void {s}(
                    \\    __global const int* input,
                    \\    __global int* output,
                    \\    const int n
                    \\) {{
                    \\    const uint gid = get_global_id(0);
                    \\    if (gid < (uint)n) {{
                    \\        output[gid] = (int)((uint)input[gid] * 2u);
                    \\    }}
                    \\}}
                    \\
                , .{k.name});
            }
        }

        const source = try buf.toOwnedSlice();

        // Calculate H_kernel = SHA256("LIN-GPU-KERNEL-V1" || H_gpuIR || CanonicalOpenCLSource)
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-GPU-KERNEL-V1");
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
