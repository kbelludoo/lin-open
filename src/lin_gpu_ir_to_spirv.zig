//! lin_gpu_ir_to_spirv.zig — Canonical SPIR-V Emitter for LIN GPU IR (LIN-GPU-008F)
//!
//! Architectural Invariants:
//!   1. SPIRVSource = E_spirv(GpuModule) is strictly deterministic and canonical.
//!   2. H_kernel_spirv = SHA256("LIN-SPIRV-KERNEL-V1" || H_gpuIR || CanonicalSPIRVSource).
//!   3. Consumes ONLY GpuModule (zero hardware/backend metadata contamination).

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;

pub const GpuIrToSpirvEmitter = struct {
    pub const EmittedSpirvKernel = struct {
        source: []const u8,
        kernel_hash: [32]u8,
        gpu_ir_hash: [32]u8,

        pub fn deinit(self: EmittedSpirvKernel, allocator: std.mem.Allocator) void {
            allocator.free(self.source);
        }
    };

    /// Canonical, deterministic SPIR-V text/disassembly emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedSpirvKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\; SPIR-V
            \\; Version: 1.5
            \\; Generator: LIN Universal GPU IR Emitter; 1
            \\; Bound: 64
            \\; Schema: 0
            \\; gpu_ir_hash: sha256:{s}
            \\; numeric_contract: {s}
            \\               OpCapability Shader
            \\               OpMemoryModel Logical GLSL450
            \\               OpEntryPoint GLCompute %main "main" %gl_GlobalInvocationID %gl_LocalInvocationID
            \\               OpExecutionMode %main LocalSize 256 1 1
            \\
        , .{
            std.fmt.fmtSliceHexLower(&gpu_ir_hash),
            @tagName(module.numeric_contract),
        });

        for (module.kernels) |k| {
            try writer.print(
                \\; Kernel: {s}
                \\; LocalMemoryBytes: {d}
                \\               OpName %{s} "{s}"
                \\
            , .{ k.name, k.local_scratch_bytes, k.name, k.name });
        }

        const source = try buf.toOwnedSlice();

        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-SPIRV-KERNEL-V1");
        hasher.update(&gpu_ir_hash);
        hasher.update(source);
        var kernel_hash: [32]u8 = undefined;
        hasher.final(&kernel_hash);

        return EmittedSpirvKernel{
            .source = source,
            .kernel_hash = kernel_hash,
            .gpu_ir_hash = gpu_ir_hash,
        };
    }
};
