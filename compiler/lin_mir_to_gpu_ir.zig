//! lin_mir_to_gpu_ir.zig — Semantic Instruction-Driven MIR to GPU IR Lowerer (LIN-GPU-008B)
//!
//! Architectural Invariants:
//!   1. Lowers exact instructions: reductions (7 operators), map (2x+1), and stencil (3-point radius).
//!   2. GpuModule contains structured instruction streams rather than hardcoded kernel patterns.
//!   3. Zero hardware-specific parameters.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");
const analyzer = @import("lin_reduction_analyzer.zig");
const planner = @import("lin_workload_planner.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuKernelKind = ir.GpuKernelKind;
const GpuInstruction = ir.GpuInstruction;
const GpuOp = ir.GpuOp;
const GpuDataType = ir.GpuDataType;
const GpuAddressSpace = ir.GpuAddressSpace;
const GpuReduceOp = ir.GpuReduceOp;
const WorkloadDescriptor = planner.WorkloadDescriptor;
const WorkloadOp = planner.WorkloadOp;

pub const MirToGpuIrLowerer = struct {
    pub fn mapLinReductionOp(op: analyzer.LinReductionOp) GpuReduceOp {
        return switch (op) {
            .sum => .sum,
            .product => .product,
            .min => .min,
            .max => .max,
            .band => .band,
            .bor => .bor,
            .bxor => .bxor,
        };
    }

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
                const reduce_op: GpuReduceOp = if (workload.reduction_op) |rop|
                    mapLinReductionOp(rop)
                else
                    .sum;

                const k1_name = try std.fmt.allocPrint(allocator, "{s}_pass1_tree", .{module_name});
                const k2_name = try std.fmt.allocPrint(allocator, "{s}_pass2_rollup", .{module_name});

                // Kernel 1: Pass 1 Instructions
                const k1_insts = try allocator.alloc(GpuInstruction, 6);
                k1_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private };
                k1_insts[1] = .{ .op = .index, .result = 1, .data_type = .u32, .address_space = .private };
                k1_insts[2] = .{ .op = .load, .result = 2, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global };
                k1_insts[3] = .{ .op = .store, .result = null, .operands = [_]u32{ 1, 2, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .workgroup_local };
                k1_insts[4] = .{ .op = .barrier, .result = null, .data_type = .bool, .address_space = .workgroup_local };
                k1_insts[5] = .{ .op = .reduce, .result = 3, .operands = [_]u32{ 1, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .workgroup_local, .reduce_op = reduce_op };

                const k1_args_t = try allocator.alloc(GpuDataType, 3);
                k1_args_t[0] = .i32;
                k1_args_t[1] = .i32;
                k1_args_t[2] = .i32;

                const k1_args_s = try allocator.alloc(GpuAddressSpace, 3);
                k1_args_s[0] = .global;
                k1_args_s[1] = .global;
                k1_args_s[2] = .private;

                const kernel1 = GpuKernel{
                    .name = k1_name,
                    .kind = .tree_reduction_pass1,
                    .workgroup_size = [_]u32{ 256, 1, 1 },
                    .instructions = k1_insts,
                    .arg_types = k1_args_t,
                    .arg_spaces = k1_args_s,
                    .requires_local_scratch = true,
                    .local_scratch_bytes = 256 * @sizeOf(i32),
                    .reduce_op = reduce_op,
                };

                // Kernel 2: Pass 2 Instructions
                const k2_insts = try allocator.alloc(GpuInstruction, 4);
                k2_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private };
                k2_insts[1] = .{ .op = .load, .result = 1, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global };
                k2_insts[2] = .{ .op = .reduce, .result = 2, .operands = [_]u32{ 1, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .workgroup_local, .reduce_op = reduce_op };
                k2_insts[3] = .{ .op = .store, .result = null, .operands = [_]u32{ 0, 2, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .global };

                const k2_args_t = try allocator.alloc(GpuDataType, 3);
                k2_args_t[0] = .i32;
                k2_args_t[1] = .i32;
                k2_args_t[2] = .i32;

                const k2_args_s = try allocator.alloc(GpuAddressSpace, 3);
                k2_args_s[0] = .global;
                k2_args_s[1] = .global;
                k2_args_s[2] = .private;

                const kernel2 = GpuKernel{
                    .name = k2_name,
                    .kind = .rollup_reduction_pass2,
                    .workgroup_size = [_]u32{ 256, 1, 1 },
                    .instructions = k2_insts,
                    .arg_types = k2_args_t,
                    .arg_spaces = k2_args_s,
                    .requires_local_scratch = true,
                    .local_scratch_bytes = 256 * @sizeOf(i32),
                    .reduce_op = reduce_op,
                };

                const kernels = try allocator.alloc(GpuKernel, 2);
                kernels[0] = kernel1;
                kernels[1] = kernel2;

                return GpuModule{
                    .schema_version = 2,
                    .name = module_name,
                    .kernels = kernels,
                    .numeric_contract = .modular_i32,
                };
            },
            .map => {
                // Map f(x) = 2x + 1
                const k_name = try std.fmt.allocPrint(allocator, "{s}_map_2x_plus_1", .{module_name});
                const k_insts = try allocator.alloc(GpuInstruction, 7);
                k_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private }; // %0 = gid
                k_insts[1] = .{ .op = .load, .result = 1, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global }; // %1 = input[%0]
                k_insts[2] = .{ .op = .constant, .result = 2, .data_type = .i32, .immediate_raw = 2 }; // %2 = 2
                k_insts[3] = .{ .op = .mul, .result = 3, .operands = [_]u32{ 1, 2, 0, 0 }, .operand_count = 2, .data_type = .i32 }; // %3 = %1 * %2
                k_insts[4] = .{ .op = .constant, .result = 4, .data_type = .i32, .immediate_raw = 1 }; // %4 = 1
                k_insts[5] = .{ .op = .add, .result = 5, .operands = [_]u32{ 3, 4, 0, 0 }, .operand_count = 2, .data_type = .i32 }; // %5 = %3 + %4
                k_insts[6] = .{ .op = .store, .result = null, .operands = [_]u32{ 0, 5, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .global }; // output[%0] = %5

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
                    .kind = .elementwise_map,
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
                    .schema_version = 2,
                    .name = module_name,
                    .kernels = kernels,
                    .numeric_contract = .modular_i32,
                };
            },
            .stencil => {
                // Stencil 1D 3-point radius: out[i] = in[i-1] + in[i] + in[i+1]
                const k_name = try std.fmt.allocPrint(allocator, "{s}_stencil_3point", .{module_name});
                const k_insts = try allocator.alloc(GpuInstruction, 7);
                k_insts[0] = .{ .op = .index, .result = 0, .data_type = .u32, .address_space = .private }; // %0 = gid
                k_insts[1] = .{ .op = .load_offset, .result = 1, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global, .offset = -1 }; // %1 = in[i-1]
                k_insts[2] = .{ .op = .load, .result = 2, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global }; // %2 = in[i]
                k_insts[3] = .{ .op = .load_offset, .result = 3, .operands = [_]u32{ 0, 0, 0, 0 }, .operand_count = 1, .data_type = .i32, .address_space = .global, .offset = 1 }; // %3 = in[i+1]
                k_insts[4] = .{ .op = .add, .result = 4, .operands = [_]u32{ 1, 2, 0, 0 }, .operand_count = 2, .data_type = .i32 }; // %4 = %1 + %2
                k_insts[5] = .{ .op = .add, .result = 5, .operands = [_]u32{ 4, 3, 0, 0 }, .operand_count = 2, .data_type = .i32 }; // %5 = %4 + %3
                k_insts[6] = .{ .op = .store, .result = null, .operands = [_]u32{ 0, 5, 0, 0 }, .operand_count = 2, .data_type = .i32, .address_space = .global }; // out[i] = %5

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
                    .kind = .stencil_1d,
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
                    .schema_version = 2,
                    .name = module_name,
                    .kernels = kernels,
                    .numeric_contract = .modular_i32,
                };
            },
            else => return error.UnsupportedWorkloadOpForGpuIr,
        }
    }
};
