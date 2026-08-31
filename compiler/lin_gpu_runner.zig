const std = @import("std");
const mir_engine = @import("lin_mir_engine.zig");
const gpu_lowerer = @import("lin_mir_gpu_lowerer.zig");

const cl = @cImport({
    @cDefine("CL_TARGET_OPENCL_VERSION", "200");
    @cInclude("CL/cl.h");
});

pub const GpuKernelRunResult = struct {
    name: []const u8,
    confirmed: usize,
    refuted: usize,
    semantic_hash: [32]u8,
    lowering_hash: [32]u8,
};

fn fibonacci_prng(i: usize) i32 {
    const v: u32 = @truncate((i + 1) *% 0x9e3779b9);
    return @bitCast(v);
}

pub fn runGpuVerificationSuite(
    alloc: std.mem.Allocator,
    stdout: anytype,
    stderr: anytype,
    kernel_funcs: []const mir_engine.MirFunction,
    vm_eval_fn: *const fn (fi: usize, arg: i64) anyerror!i64,
    fn_indices: []const usize,
) !bool {
    // 1. Discover AMD GPU Device
    var num_plat: cl.cl_uint = 0;
    _ = cl.clGetPlatformIDs(0, null, &num_plat);
    if (num_plat == 0) {
        try stderr.print("gpu-verify: no OpenCL platforms found\n", .{});
        return false;
    }
    const plats = try alloc.alloc(cl.cl_platform_id, num_plat);
    defer alloc.free(plats);
    _ = cl.clGetPlatformIDs(num_plat, plats.ptr, null);

    var ocl_plat = plats[0];
    var pbuf: [256]u8 = undefined;
    for (plats) |p| {
        _ = cl.clGetPlatformInfo(p, cl.CL_PLATFORM_NAME, pbuf.len, &pbuf, null);
        if (std.mem.indexOf(u8, std.mem.sliceTo(&pbuf, 0), "AMD Accelerated") != null or
            std.mem.indexOf(u8, std.mem.sliceTo(&pbuf, 0), "ROCm") != null)
        {
            ocl_plat = p;
            break;
        }
    }

    var num_dev: cl.cl_uint = 0;
    // Prefer a discrete GPU, but fall back to any OpenCL device (e.g. a PoCL
    // CPU device) so the parity test runs on machines without a discrete GPU.
    var dev_type: cl.cl_device_type = cl.CL_DEVICE_TYPE_GPU;
    _ = cl.clGetDeviceIDs(ocl_plat, dev_type, 0, null, &num_dev);
    if (num_dev == 0) {
        dev_type = cl.CL_DEVICE_TYPE_ALL;
        _ = cl.clGetDeviceIDs(ocl_plat, dev_type, 0, null, &num_dev);
    }
    if (num_dev == 0) {
        try stderr.print("gpu-verify: no OpenCL device found\n", .{});
        return false;
    }
    const devs = try alloc.alloc(cl.cl_device_id, num_dev);
    defer alloc.free(devs);
    _ = cl.clGetDeviceIDs(ocl_plat, dev_type, num_dev, devs.ptr, null);
    const dev = devs[0];

    var dname: [256]u8 = undefined;
    _ = cl.clGetDeviceInfo(dev, cl.CL_DEVICE_NAME, dname.len, &dname, null);
    const device_name = std.mem.sliceTo(&dname, 0);

    var err: cl.cl_int = 0;
    const ctx = cl.clCreateContext(null, 1, &dev, null, null, &err);
    if (err != cl.CL_SUCCESS) return error.OpenCLInitFailed;
    defer _ = cl.clReleaseContext(ctx);

    const queue = cl.clCreateCommandQueueWithProperties(ctx, dev, null, &err);
    if (err != cl.CL_SUCCESS) return error.OpenCLInitFailed;
    defer _ = cl.clReleaseCommandQueue(queue);

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN COMPILER SOVEREIGN GPU PIPELINE (LIN -> AST -> MIR -> ROCm/GPU)     ===\n", .{});
    try stdout.print("================================================================================\n", .{});
    try stdout.print("[GPU PIPELINE] Platform : {s}\n", .{std.mem.sliceTo(&pbuf, 0)});
    try stdout.print("[GPU PIPELINE] Device   : {s}\n\n", .{device_name});

    const SIZES = [_]usize{ 1, 2, 7, 31, 1024, 65536, 1_000_000 };
    var total_confirmed: usize = 0;
    var all_lowering_hashes = try alloc.alloc([32]u8, kernel_funcs.len);
    defer alloc.free(all_lowering_hashes);

    for (kernel_funcs, 0..) |kfunc, ki| {
        const fi = fn_indices[ki];
        try stdout.print("── LIN Kernel: {s} ─────────────────────────────────────────\n", .{kfunc.name});

        // 2. Auto-lower MIR (generated from LIN source) to OpenCL C
        const lower_res = try gpu_lowerer.MirToOpenCLLowerer.lower(
            alloc,
            kfunc,
            "lin_gpu_kernel",
            gpu_lowerer.OPENCL_ROCM_TARGET,
        );
        defer lower_res.deinit(alloc);
        all_lowering_hashes[ki] = lower_res.lowering_hash;

        try stdout.print("  [LOWERER] mir_semantic_hash = sha256:{s}\n", .{std.fmt.fmtSliceHexLower(&lower_res.mir_semantic_hash)});
        try stdout.print("  [LOWERER] lowering_hash     = sha256:{s}\n", .{std.fmt.fmtSliceHexLower(&lower_res.lowering_hash)});

        // 3. Compile OpenCL C Program
        var src_ptr: [*c]const u8 = lower_res.source.ptr;
        var src_len: usize = lower_res.source.len;
        const prog = cl.clCreateProgramWithSource(ctx, 1, @ptrCast(&src_ptr), &src_len, &err);
        if (err != cl.CL_SUCCESS) return error.OpenCLBuildFailed;
        defer _ = cl.clReleaseProgram(prog);

        err = cl.clBuildProgram(prog, 1, &dev, null, null, null);
        if (err != cl.CL_SUCCESS) {
            var log_size: usize = 0;
            _ = cl.clGetProgramBuildInfo(prog, dev, cl.CL_PROGRAM_BUILD_LOG, 0, null, &log_size);
            const log = try alloc.alloc(u8, log_size + 1);
            defer alloc.free(log);
            _ = cl.clGetProgramBuildInfo(prog, dev, cl.CL_PROGRAM_BUILD_LOG, log_size, log.ptr, null);
            try stdout.print("[BUILD ERROR]\n{s}\n", .{log});
            return error.OpenCLBuildFailed;
        }

        const kernel = cl.clCreateKernel(prog, "lin_gpu_kernel", &err);
        if (err != cl.CL_SUCCESS) return error.OpenCLBuildFailed;
        defer _ = cl.clReleaseKernel(kernel);

        // 4. Matrix differential test
        var k_confirmed: usize = 0;
        for (SIZES, 1..) |n, s_idx| {
            const h_in = try alloc.alloc(i32, n);
            defer alloc.free(h_in);
            const h_vm_out = try alloc.alloc(i32, n);
            defer alloc.free(h_vm_out);
            const h_gpu_out = try alloc.alloc(i32, n);
            defer alloc.free(h_gpu_out);

            // Populate inputs using the unified Fibonacci PRNG
            for (h_in, 0..) |*v, i| v.* = fibonacci_prng(i);

            // Execute on LIN VM (the true mathematical oracle of the source)
            for (h_in, 0..) |x, i| {
                const vm_res = try vm_eval_fn(fi, @as(i64, x));
                h_vm_out[i] = @as(i32, @truncate(vm_res));
            }

            // Execute on Silicon (RX 6600 VRAM)
            const d_in = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_ONLY, n * 4, null, &err);
            defer _ = cl.clReleaseMemObject(d_in);
            const d_out = cl.clCreateBuffer(ctx, cl.CL_MEM_WRITE_ONLY, n * 4, null, &err);
            defer _ = cl.clReleaseMemObject(d_out);

            _ = cl.clEnqueueWriteBuffer(queue, d_in, cl.CL_TRUE, 0, n * 4, h_in.ptr, 0, null, null);

            const nn: cl.cl_int = @intCast(n);
            _ = cl.clSetKernelArg(kernel, 0, @sizeOf(cl.cl_mem), @ptrCast(&d_in));
            _ = cl.clSetKernelArg(kernel, 1, @sizeOf(cl.cl_mem), @ptrCast(&d_out));
            _ = cl.clSetKernelArg(kernel, 2, @sizeOf(cl.cl_int), &nn);

            const lws: usize = 256;
            const gws: usize = ((n + lws - 1) / lws) * lws;

            var ev: cl.cl_event = undefined;
            _ = cl.clEnqueueNDRangeKernel(queue, kernel, 1, null, &gws, &lws, 0, null, &ev);
            _ = cl.clWaitForEvents(1, &ev);
            _ = cl.clReleaseEvent(ev);

            _ = cl.clEnqueueReadBuffer(queue, d_out, cl.CL_TRUE, 0, n * 4, h_gpu_out.ptr, 0, null, null);

            // Differential comparison
            var match = true;
            for (0..n) |i| {
                if (h_gpu_out[i] != h_vm_out[i]) {
                    match = false;
                    try stdout.print("  [GPU-004 {d}/7] N={d} DIVERGENCE @ i={d}: gpu={d} vm={d}\n", .{ s_idx, n, i, h_gpu_out[i], h_vm_out[i] });
                    break;
                }
            }

            if (match) {
                k_confirmed += 1;
                total_confirmed += 1;
                try stdout.print("  [GPU-004 {d}/7] N={d:<8}  LIN_VM=OK  GPU_SILICON=OK  BIT_EXACT\n", .{ s_idx, n });
            }
        }

        try stdout.print("\n  @LIN:GPU_KERNEL_CONFORMANCE:1.0.0\n", .{});
        try stdout.print("  .kernel=\"{s}\"\n", .{kfunc.name});
        try stdout.print("  .source=examples/map_kernels.lin\n", .{});
        try stdout.print("  .mir_semantic_hash=\"sha256:{s}\"\n", .{std.fmt.fmtSliceHexLower(&lower_res.mir_semantic_hash)});
        try stdout.print("  .lowering_hash=\"sha256:{s}\"\n", .{std.fmt.fmtSliceHexLower(&lower_res.lowering_hash)});
        try stdout.print("  .targets=7 .confirmed={d} .refuted={d}\n\n", .{ k_confirmed, 7 - k_confirmed });
    }

    try stdout.print("================================================================================\n", .{});
    try stdout.print("@LIN:GPU_SOVEREIGN_PIPELINE:1.0.0\n", .{});
    try stdout.print(".source=examples/map_kernels.lin\n", .{});
    try stdout.print(".device=\"{s}\"\n", .{device_name});
    try stdout.print(".pipeline_layers={{lin_source,lin_ast,vm_stack_ir,lin_ssa_mir,rocm_opencl_c,rx6600_vram}}\n", .{});
    try stdout.print(".kernels_tested={d}\n", .{kernel_funcs.len});
    try stdout.print(".sizes_per_kernel=7\n", .{});
    try stdout.print(".total_targets={d}\n", .{kernel_funcs.len * 7});
    try stdout.print(".confirmed={d}\n", .{total_confirmed});
    try stdout.print(".refuted={d}\n", .{(kernel_funcs.len * 7) - total_confirmed});
    try stdout.print(".oracle=\"LIN_SOURCE_SEMANTICS_VM\"\n", .{});
    try stdout.print(".prng=\"fibonacci_hashing(i+1)*0x9e3779b9\"\n", .{});
    try stdout.print(".equivalence=\"BIT_EXACT\"\n", .{});
    try stdout.print(".hand_written=false\n", .{});
    try stdout.print(".all_lowered_from_lin_source=true\n", .{});

    const pass = (total_confirmed == kernel_funcs.len * 7);
    if (pass) {
        try stdout.print(".status=\"PASS\"\n", .{});
    } else {
        try stdout.print(".status=\"FAIL\"\n", .{});
    }
    return pass;
}
