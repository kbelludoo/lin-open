//! lin_gpu_ir_to_spirv.zig — Canonical SPIR-V Emitter (LIN-GPU-008F)
//!
//! Architectural Invariants:
//!   1. Distinguishes H_spirv_text (disassembly) and H_spirv_binary.
//!   2. Consumes ONLY GpuModule.
//!   3. Zero hardware-specific parameters.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;

pub const GpuIrToSpirvEmitter = struct {
    pub const EmittedSpirvKernel = struct {
        text_source: []const u8,
        text_hash: [32]u8,
        binary_hash: [32]u8,
        gpu_ir_hash: [32]u8,

        pub fn deinit(self: EmittedSpirvKernel, allocator: std.mem.Allocator) void {
            allocator.free(self.text_source);
        }
    };

    /// Canonical SPIR-V text emitter
    pub fn emit(allocator: std.mem.Allocator, module: GpuModule) !EmittedSpirvKernel {
        const gpu_ir_hash = module.computeGpuIrHash();
        var buf = std.ArrayList(u8).init(allocator);
        const writer = buf.writer();

        try writer.print(
            \\; SPIR-V
            \\; Version: 1.5
            \\; Generator: LIN Universal GPU IR Emitter; 2
            \\; Bound: 128
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
                \\; Kernel: {s} (Kind: {s})
                \\; LocalMemoryBytes: {d}
                \\               OpName %{s} "{s}"
                \\
            , .{ k.name, @tagName(k.kind), k.local_scratch_bytes, k.name, k.name });
        }

        const text_source = try buf.toOwnedSlice();

        // Calculate H_spirv_text
        var text_hasher = std.crypto.hash.sha2.Sha256.init(.{});
        text_hasher.update("LIN-SPIRV-TEXT-V1.1");
        text_hasher.update(&gpu_ir_hash);
        text_hasher.update(text_source);
        var text_hash: [32]u8 = undefined;
        text_hasher.final(&text_hash);

        // Calculate synthetic H_spirv_binary (representing the compiled SPIR-V bytecode stream)
        var bin_hasher = std.crypto.hash.sha2.Sha256.init(.{});
        bin_hasher.update("LIN-SPIRV-BINARY-V1.1");
        bin_hasher.update(&text_hash);
        var binary_hash: [32]u8 = undefined;
        bin_hasher.final(&binary_hash);

        return EmittedSpirvKernel{
            .text_source = text_source,
            .text_hash = text_hash,
            .binary_hash = binary_hash,
            .gpu_ir_hash = gpu_ir_hash,
        };
    }
};
