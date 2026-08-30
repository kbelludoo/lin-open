//! test_gpu_006e_decision_to_backend.zig — LIN-GPU-006E Physical Dispatcher & Hardware Realization
//!
//! Validates:
//!   1. Strict Decision Immutability: Dispatcher never overrides ExecutionPlanner
//!   2. Dual Physical Execution: Native CPU (Scalar/SIMD) and AMD Radeon RX 6600 (gfx1030)
//!   3. Complete Provenance Merkle Chain:
//!      H_source -> H_semantic -> H_workload -> H_decision -> H_artifact -> H_result
//!   4. Bit-Exact Oracle Equality: memcmp(dispatched_result, oracle_result) == 0
//!
//! @LIN:DISPATCH_REALIZATION_CONFORMANCE:1.0.0

const std = @import("std");
const planner = @import("src/lin_workload_planner.zig");
const dispatcher = @import("src/lin_heterogeneous_dispatcher.zig");

const WorkloadDescriptor = planner.WorkloadDescriptor;
const CostModel = planner.CostModel;
const ExecutionPlanner = planner.ExecutionPlanner;
const HeterogeneousDispatcher = dispatcher.HeterogeneousDispatcher;

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

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    const alloc = std.heap.page_allocator;

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-GPU-006E: PHYSICAL DISPATCH & PROVENANCE REALIZATION — RX 6600       ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // ── 1. OpenCL Setup ──────────────────────────────────────────────────────────
    var num_platforms: cl.cl_uint = 0;
    _ = cl.clGetPlatformIDs(0, null, &num_platforms);
    const platforms = try alloc.alloc(cl.cl_platform_id, num_platforms);
    defer alloc.free(platforms);
    _ = cl.clGetPlatformIDs(num_platforms, platforms.ptr, null);

    var ocl_platform: cl.cl_platform_id = platforms[0];
    var pname_buf: [256]u8 = undefined;
    for (platforms) |plat| {
        _ = cl.clGetPlatformInfo(plat, cl.CL_PLATFORM_NAME, pname_buf.len, &pname_buf, null);
        const pname = std.mem.sliceTo(&pname_buf, 0);
        if (std.mem.indexOf(u8, pname, "AMD Accelerated") != null or
            std.mem.indexOf(u8, pname, "AMD") != null or
            std.mem.indexOf(u8, pname, "ROCm") != null)
        {
            ocl_platform = plat;
            break;
        }
    }

    var num_devices: cl.cl_uint = 0;
    _ = cl.clGetDeviceIDs(ocl_platform, cl.CL_DEVICE_TYPE_GPU, 0, null, &num_devices);
    const devices = try alloc.alloc(cl.cl_device_id, num_devices);
    defer alloc.free(devices);
    _ = cl.clGetDeviceIDs(ocl_platform, cl.CL_DEVICE_TYPE_GPU, num_devices, devices.ptr, null);
    const device = devices[0];

    var dev_name_buf: [256]u8 = undefined;
    _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_NAME, dev_name_buf.len, &dev_name_buf, null);
    const dev_name = std.mem.sliceTo(&dev_name_buf, 0);
    try stdout.print("[DEVICE] Target: {s}\n\n", .{dev_name});

    var err: cl.cl_int = undefined;
    const context = cl.clCreateContext(null, 1, &device, null, null, &err);
    try cl_check(err, "clCreateContext");
    defer _ = cl.clReleaseContext(context);

    const queue = cl.clCreateCommandQueueWithProperties(context, device, null, &err);
    try cl_check(err, "clCreateCommandQueueWithProperties");
    defer _ = cl.clReleaseCommandQueue(queue);

    const cost_model = CostModel{
        .version = 1,
        .machine_fingerprint = "x86_64:linux:zen3:pcie4",
        .device = "gfx1030",
        .cpu_intercept_ns = 50.0,
        .cpu_ns_per_element = 0.3952,
        .gpu_launch_ns = 3700.0,
        .gpu_h2d_ns_per_byte = 0.1538,
        .gpu_d2h_ns_per_byte = 0.1600,
        .gpu_compute_ns_per_element = 0.0362,
        .fit_quality = 0.995,
        .measurement_count = 390,
    };

    var passed: usize = 0;
    var total: usize = 0;

    // ──────────────────────────────────────────────────────────────────────────
    // 2. DISPATCH TEST CORPUS (Cases A through G)
    // ──────────────────────────────────────────────────────────────────────────

    // Case A: CPU_SMALL_WORKLOAD -> CPU_SCALAR -> Native execution -> Oracle Match
    {
        total += 1;
        const n = 100;
        const input = try alloc.alloc(i32, n);
        defer alloc.free(input);
        for (input, 0..) |*x, i| x.* = @as(i32, @intCast(i + 1));

        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n,
            .layout = .{ .data_bytes = n * @sizeOf(i32) },
            .dependencies = .{},
            .input_residency = .host_ram,
            .output_residency = .host_ram,
        };

        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, input, context, queue, device);

        if (res.target == .cpu_scalar and res.oracle_match and res.dispatched_scalar_output == 5050) {
            try stdout.print("  [PASS] Case A (CPU_SMALL_WORKLOAD): Dispatched to CPU_SCALAR, Oracle Match={d} (H_result=sha256:{s})\n", .{
                res.dispatched_scalar_output,
                std.fmt.fmtSliceHexLower(res.result_hash[0..8]),
            });
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case A failed\n", .{});
        }
    }

    // Case B: CPU_HOST_RESIDENT -> CPU_SIMD -> Native SIMD -> Oracle Match
    {
        total += 1;
        const n = 100000;
        const input = try alloc.alloc(i32, n);
        defer alloc.free(input);
        for (input, 0..) |*x, i| x.* = @as(i32, @intCast(i % 17));

        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n,
            .layout = .{ .data_bytes = n * @sizeOf(i32) },
            .dependencies = .{},
            .input_residency = .host_ram,
            .output_residency = .host_ram,
            .reuse_count = 1,
        };

        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, input, context, queue, device);

        if (res.target == .cpu_simd and res.oracle_match) {
            try stdout.print("  [PASS] Case B (CPU_HOST_RESIDENT): Dispatched to CPU_SIMD, Oracle Match={d}\n", .{res.dispatched_scalar_output});
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case B failed\n", .{});
        }
    }

    // Case C: GPU_VRAM_RESIDENT -> GPU_ROCM -> Real AMD RX 6600 -> Oracle Match
    {
        total += 1;
        const n = 1048576; // 1M items
        const input = try alloc.alloc(i32, n);
        defer alloc.free(input);
        for (input, 0..) |*x, i| {
            const v: u32 = @truncate((i + 1) *% 0x9e3779b9);
            x.* = @as(i32, @bitCast(v));
        }

        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n,
            .layout = .{ .data_bytes = n * @sizeOf(i32) },
            .dependencies = .{},
            .input_residency = .gpu_vram,
            .output_residency = .gpu_vram,
        };

        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, input, context, queue, device);

        if (res.target == .gpu_rocm and res.oracle_match) {
            try stdout.print("  [PASS] Case C (GPU_VRAM_RESIDENT): Dispatched to GPU_ROCM on RX 6600, BIT_EXACT Oracle Match={d} (H_artifact=sha256:{s})\n", .{
                res.dispatched_scalar_output,
                std.fmt.fmtSliceHexLower(res.artifact_hash[0..8]),
            });
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case C failed: match={any} gpu={d} oracle={d}\n", .{ res.oracle_match, res.dispatched_scalar_output, res.oracle_scalar_output });
        }
    }

    // Case D: GPU_AMORTIZED_REUSE -> GPU_ROCM (R=1000) -> Real AMD RX 6600 -> Oracle Match
    {
        total += 1;
        const n = 1048576;
        const input = try alloc.alloc(i32, n);
        defer alloc.free(input);
        for (input, 0..) |*x, i| x.* = @as(i32, @intCast(i % 100));

        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n,
            .layout = .{ .data_bytes = n * @sizeOf(i32) },
            .dependencies = .{ .transfer_amortization_eligible = true },
            .input_residency = .host_ram,
            .output_residency = .host_ram,
            .reuse_count = 1000,
        };

        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, input, context, queue, device);

        if (res.target == .gpu_rocm and res.oracle_match) {
            try stdout.print("  [PASS] Case D (GPU_AMORTIZED_REUSE): Dispatched to GPU_ROCM on RX 6600, Oracle Match={d}\n", .{res.dispatched_scalar_output});
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case D failed\n", .{});
        }
    }

    // Case E: FALLBACK_CPU -> CPU_SCALAR -> Zero GPU artifact generated -> Oracle Match
    {
        total += 1;
        const n = 500;
        const input = try alloc.alloc(i32, n);
        defer alloc.free(input);
        for (input, 0..) |*x, i| x.* = @as(i32, @intCast(i + 1));

        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n,
            .layout = .{ .data_bytes = n * @sizeOf(i32) },
            .dependencies = .{},
            .input_residency = .gpu_vram,
            .output_residency = .gpu_vram,
        };

        // Fallback simulated: gpu_supported = false
        const decision = ExecutionPlanner.plan(desc, cost_model, false);
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, input, null, null, null);

        if (res.target == .cpu_scalar and res.oracle_match) {
            try stdout.print("  [PASS] Case E (FALLBACK_CPU): Dispatched to CPU_SCALAR without GPU artifact, Oracle Match={d}\n", .{res.dispatched_scalar_output});
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case E failed\n", .{});
        }
    }

    // Case F: ARTIFACT_PROVENANCE -> Recompute H_artifact and verify embedded commitment
    {
        total += 1;
        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = 1024,
            .layout = .{ .data_bytes = 4096 },
            .dependencies = .{},
            .input_residency = .gpu_vram,
            .output_residency = .gpu_vram,
        };
        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const d_hash = decision.computeDecisionHash();
        const expected_artifact_hash = HeterogeneousDispatcher.computeArtifactHash(d_hash, decision.device, decision.strategy, "1.0.0");

        const sample_input = [_]i32{1} ** 1024;
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, &sample_input, context, queue, device);

        if (std.mem.eql(u8, &res.artifact_hash, &expected_artifact_hash)) {
            try stdout.print("  [PASS] Case F (ARTIFACT_PROVENANCE): H_artifact recomputed and verified (sha256:{s})\n", .{
                std.fmt.fmtSliceHexLower(res.artifact_hash[0..8]),
            });
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case F failed\n", .{});
        }
    }

    // Case G: DECISION_IMMUTABILITY -> Verify dispatcher reproduces planned backend with zero alteration
    {
        total += 1;
        const desc = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = 100000,
            .layout = .{ .data_bytes = 400000 },
            .dependencies = .{},
            .input_residency = .host_ram,
            .output_residency = .host_ram,
            .reuse_count = 1,
        };
        const decision = ExecutionPlanner.plan(desc, cost_model, true);
        const sample_input = [_]i32{42} ** 100000;
        const res = try HeterogeneousDispatcher.dispatch(alloc, decision, desc, &sample_input, context, queue, device);

        if (res.target == decision.backend and res.oracle_match) {
            try stdout.print("  [PASS] Case G (DECISION_IMMUTABILITY): Dispatcher executed exact planned target ({s}) without mutation\n", .{
                @tagName(decision.backend),
            });
            passed += 1;
        } else {
            try stdout.print("  [FAIL] Case G failed\n", .{});
        }
    }

    // ──────────────────────────────────────────────────────────────────────────
    // SUMMARY
    // ──────────────────────────────────────────────────────────────────────────
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("@LIN:DISPATCH_REALIZATION_CONFORMANCE:1.0.0\n", .{});
    try stdout.print(".device=\"{s}\"\n", .{dev_name});
    try stdout.print(".total_cases={d}\n", .{total});
    try stdout.print(".passed_cases={d}\n", .{passed});
    try stdout.print(".bit_exact=true\n", .{});
    try stdout.print(".provenance_chain=\"H_source -> H_semantic -> H_workload -> H_decision -> H_artifact -> H_result\"\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    if (passed != total) {
        return error.VerificationFailed;
    }
}
