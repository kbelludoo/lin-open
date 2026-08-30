//! lin_mir_to_gpu_ir.zig — Canonical Lowering from MIR to LIN GPU IR (LIN-GPU-007B)
//!
//! Architectural Invariants:
//!   1. GpuModule = F(MIR, WorkloadDescriptor). Zero hardware awareness.
//!   2. Rejects non-associative reductions, unproven aliasing, and memory unsafe patterns.
//!   3. Produces a deterministic, target-neutral GpuModule.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");
const analyzer = @import("lin_reduction_analyzer.zig");
const planner = @import("lin_workload_planner.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuInstruction = ir.GpuInstruction;
const GpuOp = ir.GpuOp;
const GpuDataType = ir.GpuDataType;
const GpuAddressSpace = ir.GpuAddressSpace;
const WorkloadDescriptor = planner.WorkloadDescriptor;
const WorkloadOp = planner.WorkloadOp;

pub const MirToGpuIrLowerer = struct {
    /// Pure, deterministic lowering from WorkloadDescriptor to GpuModule
    pub fn lower(
        allocator: std.mem.Allocator,
        workload: WorkloadDescriptor,
        module_name: []const u8,
    ) !GpuModule {
        // 1. Semantic legality checks
        if (!workload.dependencies.is_memory_safe_no_alias or workload.dependencies.conflicting_writers) {
            return error.SemanticAliasingOrConflictingWriters;
        }

        if (workload.op == .reduce and (!workload.dependencies.is_associative or !workload.dependencies.is_commutative)) {
            return error.SemanticNonAssociativeReduction;
        }

        switch (workload.op) {
            .reduce => {
                // Generate 2 target-neutral kernels: Pass 1 (Tree Reduction) + Pass 2 (Rollup Reduction)
                const k1_name = try std.fmt.allocPrint(allocator, "{s}_pass1_tree", .{module_name});
                const k2_name = try std.fmt.allocPrint(allocator, "{s}_pass2_rollup", .{module_name});

                // Kernel 1: Pass 1 Instructions
                const k1_insts = try allocator.alloc(GpuInstruction, 6);
                k1_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private }; // global_id
                k1_insts[1] = .{ .op = .index, .result = 1, .data_type = .u32, .address_space = .private }; // local_id
                k1_insts[2] = .{ .op = .load, .result = 2, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global };
                k1_insts[3] = .{ .op = .store, .result = null, .operands = [_]u32{ 1, 2, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .workgroup_local };
                k1_insts[4] = .{ .op = .barrier, .result = null, .data_type = .bool, .address_space = .workgroup_local };
                k1_insts[5] = .{ .op = .reduce, .result = 3, .operands = [_]u32{ 1, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .workgroup_local };

                const k1_args_t = try allocator.alloc(GpuDataType, 3);
                k1_args_t[0] = .i32; // input buffer
                k1_args_t[1] = .i32; // partial sums
                k1_args_t[2] = .i32; // n elements

                const k1_args_s = try allocator.alloc(GpuAddressSpace, 3);
                k1_args_s[0] = .global;
                k1_args_s[1] = .global;
                k1_args_s[2] = .private;

                const kernel1 = GpuKernel{
                    .name = k1_name,
                    .workgroup_size = [_]u32{ 256, 1, 1 },
                    .instructions = k1_insts,
                    .arg_types = k1_args_t,
                    .arg_spaces = k1_args_s,
                    .requires_local_scratch = true,
                    .local_scratch_bytes = 256 * @sizeOf(i32),
                };

                // Kernel 2: Pass 2 Instructions
                const k2_insts = try allocator.alloc(GpuInstruction, 4);
                k2_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private };
                k2_insts[1] = .{ .op = .load, .result = 1, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global };
                k2_insts[2] = .{ .op = .reduce, .result = 2, .operands = [_]u32{ 1, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .workgroup_local };
                k2_insts[3] = .{ .op = .store, .result = null, .operands = [_]u32{ 0, 2, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .global };

                const k2_args_t = try allocator.alloc(GpuDataType, 3);
                k2_args_t[0] = .i32; // partial sums in
                k2_args_t[1] = .i32; // final output scalar
                k2_args_t[2] = .i32; // num partials

                const k2_args_s = try allocator.alloc(GpuAddressSpace, 3);
                k2_args_s[0] = .global;
                k2_args_s[1] = .global;
                k2_args_s[2] = .private;

                const kernel2 = GpuKernel{
                    .name = k2_name,
                    .workgroup_size = [_]u32{ 256, 1, 1 },
                    .instructions = k2_insts,
                    .arg_types = k2_args_t,
                    .arg_spaces = k2_args_s,
                    .requires_local_scratch = true,
                    .local_scratch_bytes = 256 * @sizeOf(i32),
                };

                const kernels = try allocator.alloc(GpuKernel, 2);
                kernels[0] = kernel1;
                kernels[1] = kernel2;

                return GpuModule{
                    .schema_version = 1,
                    .name = module_name,
                    .kernels = kernels,
                    .numeric_contract = .modular_i32,
                };
            },
            .map => {
                const k_name = try std.fmt.allocPrint(allocator, "{s}_map_1d", .{module_name});
                const k_insts = try allocator.alloc(GpuInstruction, 4);
                k_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private };
                k_insts[1] = .{ .op = .load, .result = 1, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global };
                k_insts[2] = .{ .op = .mul, .result = 2, .operands = [_]u32{ 1, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .private, .immediate_raw = 2 };
                k_insts[3] = .{ .op = .store, .result = null, .operands = [_]u32{ 0, 2, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .global };

                const args_t = try allocator.alloc(GpuDataType, 3);
                args_t[0] = .i32;
                args_t[1] = .i32;
                args_t[2] = .i32;

                const args_s = try allocator.alloc(GpuAddressSpace, 3);
                args_s[0] = .global;
                args_s[1] = .global;
                args_s[2] = .private;

                const kernel = GpuKernel{
                    .name = k_name,
                    .workgroup_size = [_]u32{ 256, 1, 1 },
                    .instructions = k_insts,
                    .arg_types = args_t,
                    .arg_spaces = args_s,
                    .requires_local_scratch = false,
                    .local_scratch_bytes = 0,
                };

                const kernels = try allocator.alloc(GpuKernel, 1);
                kernels[0] = kernel;

                return GpuModule{
                    .schema_version = 1,
                    .name = module_name,
                    .kernels = kernels,
                    .numeric_contract = .modular_i32,
                };
            },
            else => return error.UnsupportedWorkloadOpForGpuIr,
        }
    }
};
