//! lin_reduction_gpu_lowerer.zig — Hierarchical GPU Reduction Lowerer (LIN-GPU-005B)
//!
//! Architectural Invariant:
//!   "O analisador decide se a transformação é legal; o lowerer apenas implementa uma decisão já provada legal."
//!
//! Consumes exclusively a verified `ReductionDescriptor` from `lin_reduction_analyzer`.
//! Emits deterministic 2-pass hierarchical tree reduction OpenCL C kernels:
//!   - Pass 1: Workgroup local tree reduction (256 WIs, __local LDS, output: partial[num_wgs])
//!   - Pass 2: Final rollup reduction (1 WG, 256 WIs, input: partial[num_wgs], output: result[0])
//!   - Lowering Manifest + H_artifact provenance hash.

const std = @import("std");
const engine = @import("lin_mir_engine.zig");
const analyzer = @import("lin_reduction_analyzer.zig");
const lowerer_base = @import("lin_mir_gpu_lowerer.zig");

const MirType = engine.MirType;
const ReductionDescriptor = analyzer.ReductionDescriptor;
const LinReductionOp = analyzer.LinReductionOp;
pub const GpuTarget = lowerer_base.GpuTarget;
pub const OPENCL_ROCM_TARGET = lowerer_base.OPENCL_ROCM_TARGET;

pub const ReductionLoweringManifest = struct {
    semantic_hash: [32]u8,
    artifact_hash: [32]u8,
    op: LinReductionOp,
    input_type: MirType,
    accum_type: MirType,
    identity_val_raw: i64,
    workgroup_size: u32 = 256,
    tile_size: u32 = 1,
    num_passes: u32 = 2,
    use_atomics: bool = false,
    target: GpuTarget,
};

pub const ReductionLoweringResult = struct {
    source: []const u8,
    pass1_kernel_name: []const u8,
    pass2_kernel_name: []const u8,
    manifest: ReductionLoweringManifest,

    pub fn deinit(self: ReductionLoweringResult, allocator: std.mem.Allocator) void {
        allocator.free(self.source);
        allocator.free(self.pass1_kernel_name);
        allocator.free(self.pass2_kernel_name);
    }
};

pub const ReductionGpuLowerer = struct {
    pub fn lower(
        allocator: std.mem.Allocator,
        desc: ReductionDescriptor,
        base_name: []const u8,
        semantic_hash: [32]u8,
        target: GpuTarget,
    ) !ReductionLoweringResult {
        // 1. Calculate artifact hash:
        // H_artifact = SHA256(H_semantic || target.name || target.numeric_model || target.memory_model || "tree_2pass_256" || op_name || type_name)
        var ahasher = std.crypto.hash.sha2.Sha256.init(.{});
        ahasher.update(&semantic_hash);
        ahasher.update(target.name);
        ahasher.update(target.numeric_model);
        ahasher.update(target.memory_model);
        ahasher.update("tree_2pass_256");
        ahasher.update(@tagName(desc.op));
        ahasher.update(@tagName(desc.input_type));

        var artifact_hash: [32]u8 = undefined;
        ahasher.final(&artifact_hash);

        const manifest = ReductionLoweringManifest{
            .semantic_hash = semantic_hash,
            .artifact_hash = artifact_hash,
            .op = desc.op,
            .input_type = desc.input_type,
            .accum_type = desc.accum_type,
            .identity_val_raw = desc.identity_val_raw,
            .workgroup_size = 256,
            .tile_size = 1,
            .num_passes = 2,
            .use_atomics = false,
            .target = target,
        };

        const pass1_name = try std.fmt.allocPrint(allocator, "{s}_pass1_wg", .{base_name});
        const pass2_name = try std.fmt.allocPrint(allocator, "{s}_pass2_final", .{base_name});

        const c_type: []const u8 = switch (desc.input_type) {
            .i32 => "int",
            .u32 => "uint",
            .i64 => "long",
            .u64 => "ulong",
            .f64 => "double",
            else => "int",
        };

        const op_expr = switch (desc.op) {
            .sum => "a + b",
            .product => "a * b",
            .min => "(a < b) ? a : b",
            .max => "(a > b) ? a : b",
            .band => "a & b",
            .bor => "a | b",
            .bxor => "a ^ b",
        };

        var buf = std.ArrayList(u8).init(allocator);
        const w = buf.writer();

        // Emit header
        try w.print(
            \\/* LIN-GPU-005B: Hierarchical Deterministic 2-Pass Reduction
            \\ * mir_semantic_hash = sha256:{s}
            \\ * artifact_hash     = sha256:{s}
            \\ * operator          = {s}
            \\ * identity          = {d}
            \\ * workgroup_size    = 256
            \\ * target            = {s} | {s} | {s}
            \\ */
            \\
            \\#define REDUCE_OP(a, b) ({s})
            \\#define REDUCE_IDENTITY ({d})
            \\#define WG_SIZE 256
            \\
            \\// Pass 1: Workgroup-level tree reduction (Global -> Partials)
            \\__kernel void {s}(
            \\    __global const {s}* restrict input,
            \\    __global {s}* restrict partial_out,
            \\    const int n)
            \\{{
            \\    __local {s} ldata[WG_SIZE];
            \\    int tid = get_local_id(0);
            \\    int gid = get_global_id(0);
            \\    int grid_size = get_global_size(0);
            \\
            \\    {s} accum = REDUCE_IDENTITY;
            \\    for (int i = gid; i < n; i += grid_size) {{
            \\        accum = REDUCE_OP(accum, input[i]);
            \\    }}
            \\    ldata[tid] = accum;
            \\    barrier(CLK_LOCAL_MEM_FENCE);
            \\
            \\    // Unrolled Tree Reduction in LDS (256 -> 1)
            \\    if (tid < 128) {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 128]); }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 64)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 64]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 32)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 32]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 16)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 16]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 8)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 8]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 4)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 4]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 2)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 2]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 1)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 1]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\
            \\    if (tid == 0) {{
            \\        partial_out[get_group_id(0)] = ldata[0];
            \\    }}
            \\}}
            \\
            \\// Pass 2: Final Rollup Reduction (Partials -> Final Scalar)
            \\__kernel void {s}(
            \\    __global const {s}* restrict partial_in,
            \\    __global {s}* restrict result_out,
            \\    const int num_partials)
            \\{{
            \\    __local {s} ldata[WG_SIZE];
            \\    int tid = get_local_id(0);
            \\
            \\    {s} accum = REDUCE_IDENTITY;
            \\    for (int i = tid; i < num_partials; i += WG_SIZE) {{
            \\        accum = REDUCE_OP(accum, partial_in[i]);
            \\    }}
            \\    ldata[tid] = accum;
            \\    barrier(CLK_LOCAL_MEM_FENCE);
            \\
            \\    if (tid < 128) {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 128]); }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 64)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 64]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 32)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 32]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 16)  {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 16]);  }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 8)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 8]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 4)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 4]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 2)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 2]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\    if (tid < 1)   {{ ldata[tid] = REDUCE_OP(ldata[tid], ldata[tid + 1]);   }} barrier(CLK_LOCAL_MEM_FENCE);
            \\
            \\    if (tid == 0) {{
            \\        result_out[0] = ldata[0];
            \\    }}
            \\}}
            \\
        , .{
            std.fmt.fmtSliceHexLower(&manifest.semantic_hash),
            std.fmt.fmtSliceHexLower(&manifest.artifact_hash),
            @tagName(desc.op),
            desc.identity_val_raw,
            target.name, target.numeric_model, target.memory_model,
            op_expr,
            desc.identity_val_raw,
            pass1_name,
            c_type, c_type, c_type, c_type,
            pass2_name,
            c_type, c_type, c_type, c_type,
        });

        return ReductionLoweringResult{
            .source = try buf.toOwnedSlice(),
            .pass1_kernel_name = pass1_name,
            .pass2_kernel_name = pass2_name,
            .manifest = manifest,
        };
    }
};
