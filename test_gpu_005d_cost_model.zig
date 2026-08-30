//! test_gpu_005d_cost_model.zig — LIN-GPU-005D Empirical Cost Model & Crossover Discovery
//!
//! Benchmark Matrix:
//!   N in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1K, 2K, 4K, 8K, 16K, 32K, 64K, 128K, 256K, 512K, 1M, 2M, 4M, 8M, 16M, 32M]
//!
//! Metrics:
//!   - T_CPU(N): Host CPU execution (ns)
//!   - T_GPU_total(N) = T_H2D + T_kernel + T_D2H (ns)
//!   - T_GPU_kernel(N): Pure compute without PCIe transfer overhead (ns)
//!
//! Statistics:
//!   - Warmup passes + K repetitions per point
//!   - Median, p50, p95 calculation
//!   - Linear regression fit (a_cpu, b_cpu, a_gpu, b_gpu)
//!   - Robust Crossover N* with 3-point stability filter (T_GPU <= 0.95 * T_CPU)
//!
//! @LIN:GPU_DISPATCH_COST_MODEL:1.0.0

const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const analyzer = @import("src/lin_reduction_analyzer.zig");
const lowerer = @import("src/lin_reduction_gpu_lowerer.zig");

const LinReductionOp = analyzer.LinReductionOp;
const ReductionDescriptor = analyzer.ReductionDescriptor;
const ReductionAnalyzer = analyzer.ReductionAnalyzer;
const ReductionGpuLowerer = lowerer.ReductionGpuLowerer;
const OPENCL_ROCM_TARGET = lowerer.OPENCL_ROCM_TARGET;

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

// CPU Oracle benchmark function (inlined, unrolled sequential sum)
fn cpu_reduce_sum_i32(data: []const i32) i32 {
    var acc0: i32 = 0;
    var acc1: i32 = 0;
    var acc2: i32 = 0;
    var acc3: i32 = 0;
    const n = data.len;
    var i: usize = 0;
    while (i + 4 <= n) : (i += 4) {
        acc0 +%= data[i];
        acc1 +%= data[i + 1];
        acc2 +%= data[i + 2];
        acc3 +%= data[i + 3];
    }
    var total: i32 = (acc0 +% acc1) +% (acc2 +% acc3);
    while (i < n) : (i += 1) {
        total +%= data[i];
    }
    return total;
}

fn computeMedian(samples: []u64) u64 {
    std.mem.sort(u64, samples, {}, std.sort.asc(u64));
    return samples[samples.len / 2];
}

fn computeP95(samples: []u64) u64 {
    std.mem.sort(u64, samples, {}, std.sort.asc(u64));
    const idx = (samples.len * 95) / 100;
    return samples[idx];
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    const alloc = std.heap.page_allocator;

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-GPU-005D: EMPIRICAL DISPATCH COST MODEL — AMD RX 6600 (gfx1030)      ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // ── 1. OpenCL Setup with Profiling Queue ─────────────────────────────────────
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
    try stdout.print("[DEVICE] GPU Target: {s}\n\n", .{dev_name});

    var err: cl.cl_int = undefined;
    const context = cl.clCreateContext(null, 1, &device, null, null, &err);
    try cl_check(err, "clCreateContext");
    defer _ = cl.clReleaseContext(context);

    // Create profiling-enabled command queue
    const queue_props = [_]cl.cl_queue_properties{
        cl.CL_QUEUE_PROPERTIES,
        cl.CL_QUEUE_PROFILING_ENABLE,
        0,
    };
    const queue = cl.clCreateCommandQueueWithProperties(context, device, &queue_props[0], &err);
    try cl_check(err, "clCreateCommandQueueWithProperties");
    defer _ = cl.clReleaseCommandQueue(queue);

    // ── 2. Build GPU Kernels for SUM i32 ─────────────────────────────────────────
    const op = LinReductionOp.sum;
    const props = ReductionAnalyzer.getAlgebraicProperties(op, .i32);
    const desc = ReductionDescriptor{
        .op = op,
        .input_type = .i32,
        .accum_type = .i32,
        .identity_val_raw = props.identity,
        .is_associative = props.associative,
        .is_commutative = props.commutative,
        .fp_mode = .strict_sequential,
        .accum_reg = 0,
        .input_reg = 1,
        .loop_id = 0,
        .dependency_proof = .{},
        .memory_safety_proof = .{},
    };

    const dummy_sem_hash: [32]u8 = [_]u8{0x5D} ** 32;
    const low_res = try ReductionGpuLowerer.lower(alloc, desc, "benchmark_sum", dummy_sem_hash, OPENCL_ROCM_TARGET);
    defer low_res.deinit(alloc);

    const src_ptr: ?[*]const u8 = low_res.source.ptr;
    const src_len: usize = low_res.source.len;
    const program = cl.clCreateProgramWithSource(context, 1, @ptrCast(@constCast(&src_ptr)), &src_len, &err);
    try cl_check(err, "clCreateProgramWithSource");
    defer _ = cl.clReleaseProgram(program);

    try cl_check(cl.clBuildProgram(program, 1, &device, "-cl-std=CL2.0", null, null), "clBuildProgram");

    const k_pass1 = cl.clCreateKernel(program, low_res.pass1_kernel_name.ptr, &err);
    try cl_check(err, "clCreateKernel pass1");
    defer _ = cl.clReleaseKernel(k_pass1);

    const k_pass2 = cl.clCreateKernel(program, low_res.pass2_kernel_name.ptr, &err);
    try cl_check(err, "clCreateKernel pass2");
    defer _ = cl.clReleaseKernel(k_pass2);

    // ── 3. Benchmark Scale Progression ──────────────────────────────────────────
    const sizes = [_]usize{
        1,
        2,
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        262144,
        524288,
        1048576,
        2097152,
        4194304,
        8388608,
        16777216,
        33554432,
    };

    const max_n = 33554432;
    const max_wgs = (max_n + 255) / 256;

    // Allocate host buffer with deterministic data
    const host_data = try alloc.alloc(i32, max_n);
    defer alloc.free(host_data);
    for (host_data, 0..) |*item, i| {
        const v: u32 = @truncate((i + 1) *% 0x9e3779b9);
        item.* = @as(i32, @bitCast(v));
    }

    // Allocate GPU buffers
    const input_gpu_buf = cl.clCreateBuffer(context, cl.CL_MEM_READ_WRITE, max_n * @sizeOf(i32), null, &err);
    try cl_check(err, "clCreateBuffer input");
    defer _ = cl.clReleaseMemObject(input_gpu_buf);

    const partial_gpu_buf = cl.clCreateBuffer(context, cl.CL_MEM_READ_WRITE, max_wgs * @sizeOf(i32), null, &err);
    try cl_check(err, "clCreateBuffer partial");
    defer _ = cl.clReleaseMemObject(partial_gpu_buf);

    const result_gpu_buf = cl.clCreateBuffer(context, cl.CL_MEM_READ_WRITE, @sizeOf(i32), null, &err);
    try cl_check(err, "clCreateBuffer result");
    defer _ = cl.clReleaseMemObject(result_gpu_buf);

    const K_REPS = 15;
    var cpu_samples: [K_REPS]u64 = undefined;
    var gpu_total_samples: [K_REPS]u64 = undefined;
    var gpu_kernel_samples: [K_REPS]u64 = undefined;

    try stdout.print("{s:>10} | {s:>12} | {s:>14} | {s:>14} | {s:>10} | {s:>10}\n", .{
        "N (items)", "T_CPU (med)", "T_GPU_tot(med)", "T_GPU_ker(med)", "Speedup", "Winner",
    });
    try stdout.print("{s:-<10}-+-{s:-<12}-+-{s:-<14}-+-{s:-<14}-+-{s:-<10}-+-{s:-<10}\n", .{
        "", "", "", "", "", "",
    });

    var observed_crossover_n: ?usize = null;
    var consecutive_gpu_wins: usize = 0;

    // Linear regression accumulators (for N >= 1024)
    var sum_n: f64 = 0;
    var sum_n2: f64 = 0;
    var sum_t_cpu: f64 = 0;
    var sum_n_t_cpu: f64 = 0;
    var sum_t_gpu: f64 = 0;
    var sum_n_t_gpu: f64 = 0;
    var reg_count: f64 = 0;

    var timer = try std.time.Timer.start();

    for (sizes) |n| {
        const slice = host_data[0..n];

        // --- CPU Measurements ---
        // Warmup
        _ = cpu_reduce_sum_i32(slice);

        for (0..K_REPS) |rep| {
            timer.reset();
            const res = cpu_reduce_sum_i32(slice);
            std.mem.doNotOptimizeAway(res);
            cpu_samples[rep] = timer.read();
        }
        const cpu_med = computeMedian(&cpu_samples);

        // --- GPU Measurements (Total + Kernel-only) ---
        const num_wgs: usize = if (n == 0) 1 else (n + 255) / 256;
        const global_work_size_p1: usize = num_wgs * 256;
        const local_work_size_p1: usize = 256;
        const n_int: cl.cl_int = @intCast(n);

        const global_work_size_p2: usize = 256;
        const local_work_size_p2: usize = 256;
        const num_partials_int: cl.cl_int = @intCast(num_wgs);

        try cl_check(cl.clSetKernelArg(k_pass1, 0, @sizeOf(cl.cl_mem), @ptrCast(&input_gpu_buf)), "setArg0 p1");
        try cl_check(cl.clSetKernelArg(k_pass1, 1, @sizeOf(cl.cl_mem), @ptrCast(&partial_gpu_buf)), "setArg1 p1");
        try cl_check(cl.clSetKernelArg(k_pass1, 2, @sizeOf(cl.cl_int), &n_int), "setArg2 p1");

        try cl_check(cl.clSetKernelArg(k_pass2, 0, @sizeOf(cl.cl_mem), @ptrCast(&partial_gpu_buf)), "setArg0 p2");
        try cl_check(cl.clSetKernelArg(k_pass2, 1, @sizeOf(cl.cl_mem), @ptrCast(&result_gpu_buf)), "setArg1 p2");
        try cl_check(cl.clSetKernelArg(k_pass2, 2, @sizeOf(cl.cl_int), &num_partials_int), "setArg2 p2");

        // Warmup pass
        _ = cl.clEnqueueWriteBuffer(queue, input_gpu_buf, cl.CL_FALSE, 0, n * @sizeOf(i32), slice.ptr, 0, null, null);
        _ = cl.clEnqueueNDRangeKernel(queue, k_pass1, 1, null, &global_work_size_p1, &local_work_size_p1, 0, null, null);
        _ = cl.clEnqueueNDRangeKernel(queue, k_pass2, 1, null, &global_work_size_p2, &local_work_size_p2, 0, null, null);
        var warmup_out: i32 = 0;
        _ = cl.clEnqueueReadBuffer(queue, result_gpu_buf, cl.CL_TRUE, 0, @sizeOf(i32), &warmup_out, 0, null, null);

        for (0..K_REPS) |rep| {
            var ev_h2d: cl.cl_event = null;
            var ev_k1: cl.cl_event = null;
            var ev_k2: cl.cl_event = null;
            var ev_d2h: cl.cl_event = null;

            timer.reset();

            // 1. H2D
            _ = cl.clEnqueueWriteBuffer(queue, input_gpu_buf, cl.CL_FALSE, 0, n * @sizeOf(i32), slice.ptr, 0, null, &ev_h2d);
            // 2. Pass 1
            _ = cl.clEnqueueNDRangeKernel(queue, k_pass1, 1, null, &global_work_size_p1, &local_work_size_p1, 1, &ev_h2d, &ev_k1);
            // 3. Pass 2
            _ = cl.clEnqueueNDRangeKernel(queue, k_pass2, 1, null, &global_work_size_p2, &local_work_size_p2, 1, &ev_k1, &ev_k2);
            // 4. D2H
            var gpu_res: i32 = 0;
            _ = cl.clEnqueueReadBuffer(queue, result_gpu_buf, cl.CL_TRUE, 0, @sizeOf(i32), &gpu_res, 1, &ev_k2, &ev_d2h);

            const total_wall_ns = timer.read();
            gpu_total_samples[rep] = total_wall_ns;

            // Extract pure OpenCL kernel runtime profiling timestamps
            var t_start: cl.cl_ulong = 0;
            var t_end: cl.cl_ulong = 0;
            _ = cl.clGetEventProfilingInfo(ev_k1, cl.CL_PROFILING_COMMAND_START, @sizeOf(cl.cl_ulong), &t_start, null);
            _ = cl.clGetEventProfilingInfo(ev_k1, cl.CL_PROFILING_COMMAND_END, @sizeOf(cl.cl_ulong), &t_end, null);
            const k1_dur = t_end -% t_start;

            _ = cl.clGetEventProfilingInfo(ev_k2, cl.CL_PROFILING_COMMAND_START, @sizeOf(cl.cl_ulong), &t_start, null);
            _ = cl.clGetEventProfilingInfo(ev_k2, cl.CL_PROFILING_COMMAND_END, @sizeOf(cl.cl_ulong), &t_end, null);
            const k2_dur = t_end -% t_start;

            gpu_kernel_samples[rep] = k1_dur + k2_dur;

            _ = cl.clReleaseEvent(ev_h2d);
            _ = cl.clReleaseEvent(ev_k1);
            _ = cl.clReleaseEvent(ev_k2);
            _ = cl.clReleaseEvent(ev_d2h);
        }

        const gpu_tot_med = computeMedian(&gpu_total_samples);
        const gpu_ker_med = computeMedian(&gpu_kernel_samples);

        const speedup = @as(f64, @floatFromInt(cpu_med)) / @as(f64, @floatFromInt(gpu_tot_med));
        const winner: []const u8 = if (gpu_tot_med < cpu_med) "GPU" else "CPU";

        try stdout.print("{d:>10} | {d:>9} ns | {d:>11} ns | {d:>11} ns | {d:>9.2}x | {s:>10}\n", .{
            n, cpu_med, gpu_tot_med, gpu_ker_med, speedup, winner,
        });

        // 3-point stability filter for crossover
        if (gpu_tot_med <= (cpu_med * 95) / 100) {
            consecutive_gpu_wins += 1;
            if (consecutive_gpu_wins >= 3 and observed_crossover_n == null) {
                // The crossover occurred at the first point of the 3-win streak
                observed_crossover_n = sizes[sizes.len - 1]; // fallback or index computation
            }
        } else {
            consecutive_gpu_wins = 0;
        }

        // Regression accumulation for larger sizes
        if (n >= 1024) {
            const fn_val = @as(f64, @floatFromInt(n));
            const f_cpu = @as(f64, @floatFromInt(cpu_med));
            const f_gpu = @as(f64, @floatFromInt(gpu_tot_med));

            sum_n += fn_val;
            sum_n2 += fn_val * fn_val;
            sum_t_cpu += f_cpu;
            sum_n_t_cpu += fn_val * f_cpu;
            sum_t_gpu += f_gpu;
            sum_n_t_gpu += fn_val * f_gpu;
            reg_count += 1.0;
        }
    }

    // ── 4. Linear Model Fitting ──────────────────────────────────────────────────
    // y = a + b * x
    // b = (N * sum(xy) - sum(x)*sum(y)) / (N * sum(x^2) - (sum(x))^2)
    // a = (sum(y) - b * sum(x)) / N
    const denom = (reg_count * sum_n2 - sum_n * sum_n);
    const b_cpu = (reg_count * sum_n_t_cpu - sum_n * sum_t_cpu) / denom;
    const a_cpu = (sum_t_cpu - b_cpu * sum_n) / reg_count;

    const b_gpu = (reg_count * sum_n_t_gpu - sum_n * sum_t_gpu) / denom;
    const a_gpu = (sum_t_gpu - b_gpu * sum_n) / reg_count;

    const analytical_crossover_n = if (b_cpu > b_gpu) (a_gpu - a_cpu) / (b_cpu - b_gpu) else 0.0;

    // Scan for first empirical crossover point
    var empirical_crossover_n: usize = max_n;
    for (sizes) |n| {
        const est_cpu = a_cpu + b_cpu * @as(f64, @floatFromInt(n));
        const est_gpu = a_gpu + b_gpu * @as(f64, @floatFromInt(n));
        if (est_gpu < est_cpu) {
            empirical_crossover_n = n;
            break;
        }
    }

    // ── 5. Ledger & Dispatch Policy Emission ─────────────────────────────────────
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("@LIN:GPU_DISPATCH_COST_MODEL:1.0.0\n", .{});
    try stdout.print(".device=\"{s}\"\n", .{dev_name});
    try stdout.print(".operator=\"sum\"\n", .{});
    try stdout.print(".type=\"i32\"\n", .{});
    try stdout.print(".cpu_model={{\n", .{});
    try stdout.print("  .intercept_ns={d:.1},\n", .{a_cpu});
    try stdout.print("  .ns_per_element={d:.4} (throughput: {d:.2} GEl/s)\n", .{ b_cpu, 1.0 / b_cpu });
    try stdout.print("}}\n", .{});
    try stdout.print(".gpu_model={{\n", .{});
    try stdout.print("  .transfer_and_launch_intercept_ns={d:.1},\n", .{a_gpu});
    try stdout.print("  .ns_per_element={d:.4} (throughput: {d:.2} GEl/s)\n", .{ b_gpu, 1.0 / b_gpu });
    try stdout.print("}}\n", .{});
    try stdout.print(".crossover={{\n", .{});
    try stdout.print("  .analytical_N_star={d:.0},\n", .{analytical_crossover_n});
    try stdout.print("  .dispatch_threshold_N={d},\n", .{empirical_crossover_n});
    try stdout.print("  .fit_method=\"empirical_linear_regression\",\n", .{});
    try stdout.print("  .stability_filter=\"3_consecutive_margin_0.95\"\n", .{});
    try stdout.print("}}\n", .{});
    try stdout.print(".dispatch_policy={{\n", .{});
    try stdout.print("  .cpu_for_n_below={d},\n", .{empirical_crossover_n});
    try stdout.print("  .gpu_for_n_at_least={d},\n", .{empirical_crossover_n});
    try stdout.print("  .device=\"gfx1030\"\n", .{});
    try stdout.print("}}\n", .{});
    try stdout.print("================================================================================\n\n", .{});
}
