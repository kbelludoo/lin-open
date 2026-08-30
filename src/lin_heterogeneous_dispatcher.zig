//! lin_heterogeneous_dispatcher.zig — Physical Execution Dispatcher & Provenance Validator (LIN-GPU-006E)
//!
//! Architectural Invariant:
//!   "O dispatcher materializa a ExecutionDecision exatamente como foi planejada,
//!    sem jamais alterar o backend no caminho físico."
//!
//! Provenance Chain:
//!   H_source -> H_semantic -> H_workload -> H_decision -> H_artifact -> H_result

const std = @import("std");
const engine = @import("lin_mir_engine.zig");
const analyzer = @import("lin_reduction_analyzer.zig");
const lowerer = @import("lin_reduction_gpu_lowerer.zig");
const planner = @import("lin_workload_planner.zig");

const WorkloadDescriptor = planner.WorkloadDescriptor;
const CostModel = planner.CostModel;
const ExecutionDecision = planner.ExecutionDecision;
const BackendTarget = planner.BackendTarget;
const LinReductionOp = analyzer.LinReductionOp;
const ReductionDescriptor = analyzer.ReductionDescriptor;
const ReductionGpuLowerer = lowerer.ReductionGpuLowerer;
const GpuTarget = lowerer.GpuTarget;

const cl = @cImport({
    @cDefine("CL_TARGET_OPENCL_VERSION", "200");
    @cInclude("CL/cl.h");
});

fn cl_check(err: cl.cl_int, msg: []const u8) !void {
    if (err != cl.CL_SUCCESS) {
        std.debug.print("[OCL ERROR] {s}: code={d}\n", .{ msg, err });
        return error.OpenCLError;
    }
}

pub const DispatchResult = struct {
    decision: ExecutionDecision,
    artifact_hash: [32]u8,
    result_hash: [32]u8,
    target: BackendTarget,
    executed: bool,
    oracle_match: bool,
    dispatched_scalar_output: i32,
    oracle_scalar_output: i32,
};

pub const HeterogeneousDispatcher = struct {
    /// Pure LinVM Sequential Oracle (Exact 32-bit Modular Arithmetic)
    pub fn computeOracle(op: LinReductionOp, input: []const i32) i32 {
        var accum: i32 = switch (op) {
            .sum => 0,
            .product => 1,
            .band => @as(i32, @bitCast(@as(u32, 0xFFFFFFFF))),
            .bor => 0,
            .bxor => 0,
            .min => std.math.maxInt(i32),
            .max => std.math.minInt(i32),
        };
        for (input) |x| {
            accum = switch (op) {
                .sum => accum +% x,
                .product => accum *% x,
                .band => accum & x,
                .bor => accum | x,
                .bxor => accum ^ x,
                .min => if (x < accum) x else accum,
                .max => if (x > accum) x else accum,
            };
        }
        return accum;
    }

    /// Compute H_artifact = SHA256(H_decision || target || strategy || compiler_version)
    pub fn computeArtifactHash(decision_hash: [32]u8, target_name: []const u8, strategy: []const u8, compiler_version: []const u8) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN_ARTIFACT_V1");
        hasher.update(&decision_hash);
        hasher.update(target_name);
        hasher.update(strategy);
        hasher.update(compiler_version);
        var h: [32]u8 = undefined;
        hasher.final(&h);
        return h;
    }

    /// CPU Scalar Backend Execution
    pub fn executeCpuScalar(op: LinReductionOp, input: []const i32) i32 {
        return computeOracle(op, input);
    }

    /// CPU SIMD Backend Execution (AVX2 Unrolled Loop)
    pub fn executeCpuSimd(op: LinReductionOp, input: []const i32) i32 {
        if (op != .sum) return computeOracle(op, input);

        var a0: i32 = 0;
        var a1: i32 = 0;
        var a2: i32 = 0;
        var a3: i32 = 0;
        const n = input.len;
        var i: usize = 0;
        while (i + 4 <= n) : (i += 4) {
            a0 +%= input[i];
            a1 +%= input[i + 1];
            a2 +%= input[i + 2];
            a3 +%= input[i + 3];
        }
        var total: i32 = (a0 +% a1) +% (a2 +% a3);
        while (i < n) : (i += 1) {
            total +%= input[i];
        }
        return total;
    }

    /// Physical Hardware Dispatcher
    pub fn dispatch(
        allocator: std.mem.Allocator,
        decision: ExecutionDecision,
        workload: WorkloadDescriptor,
        input_data: []const i32,
        ocl_ctx: ?cl.cl_context,
        ocl_queue: ?cl.cl_command_queue,
        ocl_dev: ?cl.cl_device_id,
    ) !DispatchResult {
        const d_hash = decision.computeDecisionHash();
        const oracle_out = computeOracle(workload.reduction_op orelse .sum, input_data);

        // 1. Calculate H_artifact
        const artifact_hash = computeArtifactHash(d_hash, decision.device, decision.strategy, "1.0.0");

        var dispatched_out: i32 = 0;

        // 2. Strict Immutability: Dispatch according to planned backend
        switch (decision.backend) {
            .cpu_scalar => {
                dispatched_out = executeCpuScalar(workload.reduction_op orelse .sum, input_data);
            },
            .cpu_simd => {
                dispatched_out = executeCpuSimd(workload.reduction_op orelse .sum, input_data);
            },
            .gpu_rocm => {
                if (ocl_ctx == null or ocl_queue == null or ocl_dev == null) {
                    return error.GpuDeviceNotSupplied;
                }
                const ctx = ocl_ctx.?;
                const queue = ocl_queue.?;
                const dev = ocl_dev.?;

                // Build self-provenance GPU Lowerer artifact
                const gpu_target = GpuTarget{
                    .name = "opencl_c_2.0",
                    .numeric_model = "opencl_modular_i32",
                    .memory_model = "global_lds_2pass",
                };

                const desc = ReductionDescriptor{
                    .op = workload.reduction_op orelse .sum,
                    .input_type = .i32,
                    .accum_type = .i32,
                    .identity_val_raw = workload.identity_val_raw,
                    .is_associative = workload.dependencies.is_associative,
                    .is_commutative = workload.dependencies.is_commutative,
                    .fp_mode = .strict_sequential,
                    .accum_reg = 0,
                    .input_reg = 1,
                    .loop_id = 0,
                    .dependency_proof = .{},
                    .memory_safety_proof = .{},
                };

                const low_res = try ReductionGpuLowerer.lower(allocator, desc, "dispatched_kernel", d_hash, gpu_target);
                defer low_res.deinit(allocator);

                // Inject Decision and Artifact Provenance into OpenCL source header
                const full_source = try std.fmt.allocPrint(allocator,
                    \\/* LIN_ARTIFACT_V1
                    \\ * decision_hash = sha256:{s}
                    \\ * workload_hash = sha256:{s}
                    \\ * artifact_hash = sha256:{s}
                    \\ * target        = {s}
                    \\ * strategy      = {s}
                    \\ * version       = 1.0.0
                    \\ */
                    \\{s}
                , .{
                    std.fmt.fmtSliceHexLower(&d_hash),
                    std.fmt.fmtSliceHexLower(&decision.workload_hash),
                    std.fmt.fmtSliceHexLower(&artifact_hash),
                    decision.device,
                    decision.strategy,
                    low_res.source,
                });
                defer allocator.free(full_source);

                // Compile on AMD Radeon RX 6600 (gfx1030)
                var err: cl.cl_int = undefined;
                const src_ptr: ?[*]const u8 = full_source.ptr;
                const src_len: usize = full_source.len;
                const program = cl.clCreateProgramWithSource(ctx, 1, @ptrCast(@constCast(&src_ptr)), &src_len, &err);
                try cl_check(err, "clCreateProgramWithSource");
                defer _ = cl.clReleaseProgram(program);

                try cl_check(cl.clBuildProgram(program, 1, &dev, "-cl-std=CL2.0", null, null), "clBuildProgram");

                const k1 = cl.clCreateKernel(program, low_res.pass1_kernel_name.ptr, &err);
                try cl_check(err, "clCreateKernel pass1");
                defer _ = cl.clReleaseKernel(k1);

                const k2 = cl.clCreateKernel(program, low_res.pass2_kernel_name.ptr, &err);
                try cl_check(err, "clCreateKernel pass2");
                defer _ = cl.clReleaseKernel(k2);

                const n = input_data.len;
                const num_wgs: usize = if (n == 0) 1 else (n + 255) / 256;

                // GPU memory buffers
                const d_in = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_WRITE, @max(n, 1) * @sizeOf(i32), null, &err);
                try cl_check(err, "clCreateBuffer in");
                defer _ = cl.clReleaseMemObject(d_in);

                const d_part = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_WRITE, num_wgs * @sizeOf(i32), null, &err);
                try cl_check(err, "clCreateBuffer part");
                defer _ = cl.clReleaseMemObject(d_part);

                const d_out = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_WRITE, @sizeOf(i32), null, &err);
                try cl_check(err, "clCreateBuffer out");
                defer _ = cl.clReleaseMemObject(d_out);

                // H2D Transfer
                if (n > 0) {
                    try cl_check(cl.clEnqueueWriteBuffer(queue, d_in, cl.CL_TRUE, 0, n * @sizeOf(i32), input_data.ptr, 0, null, null), "clEnqueueWriteBuffer");
                }

                // Pass 1 Execution
                const n_int: cl.cl_int = @intCast(n);
                try cl_check(cl.clSetKernelArg(k1, 0, @sizeOf(cl.cl_mem), @ptrCast(&d_in)), "setArg0 p1");
                try cl_check(cl.clSetKernelArg(k1, 1, @sizeOf(cl.cl_mem), @ptrCast(&d_part)), "setArg1 p1");
                try cl_check(cl.clSetKernelArg(k1, 2, @sizeOf(cl.cl_int), &n_int), "setArg2 p1");

                const g_p1: usize = num_wgs * 256;
                const l_p1: usize = 256;
                try cl_check(cl.clEnqueueNDRangeKernel(queue, k1, 1, null, &g_p1, &l_p1, 0, null, null), "NDRange p1");

                // Pass 2 Execution
                const num_parts_int: cl.cl_int = @intCast(num_wgs);
                try cl_check(cl.clSetKernelArg(k2, 0, @sizeOf(cl.cl_mem), @ptrCast(&d_part)), "setArg0 p2");
                try cl_check(cl.clSetKernelArg(k2, 1, @sizeOf(cl.cl_mem), @ptrCast(&d_out)), "setArg1 p2");
                try cl_check(cl.clSetKernelArg(k2, 2, @sizeOf(cl.cl_int), &num_parts_int), "setArg2 p2");

                const g_p2: usize = 256;
                const l_p2: usize = 256;
                try cl_check(cl.clEnqueueNDRangeKernel(queue, k2, 1, null, &g_p2, &l_p2, 0, null, null), "NDRange p2");

                // D2H Readback
                try cl_check(cl.clEnqueueReadBuffer(queue, d_out, cl.CL_TRUE, 0, @sizeOf(i32), &dispatched_out, 0, null, null), "clEnqueueReadBuffer");
            },
            .reject_illegal => {
                return error.CannotDispatchIllegalWorkload;
            },
        }

        // 3. Compute H_result = SHA256(result bytes)
        var res_hasher = std.crypto.hash.sha2.Sha256.init(.{});
        res_hasher.update(std.mem.asBytes(&dispatched_out));
        var result_hash: [32]u8 = undefined;
        res_hasher.final(&result_hash);

        const match = (dispatched_out == oracle_out);

        return DispatchResult{
            .decision = decision,
            .artifact_hash = artifact_hash,
            .result_hash = result_hash,
            .target = decision.backend,
            .executed = true,
            .oracle_match = match,
            .dispatched_scalar_output = dispatched_out,
            .oracle_scalar_output = oracle_out,
        };
    }
};
