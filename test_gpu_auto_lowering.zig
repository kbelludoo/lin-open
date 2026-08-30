//! LIN-GPU-003: MIR-to-GPU Automatic Lowering Differential Test
//!
//! Closes the compiler trust gap: the OpenCL C kernel is generated automatically
//! from MirInst[], NOT hand-written.
//!
//! PRNG fix: uses Fibonacci hashing (Knuth multiplicative)  input[i] = u32(i+1) * 0x9e3779b9
//! which is identically portable in Zig and C (same bit pattern, no stdlib PRNG dependency).
//!
//! Oracle quad: MirVm == GenericJIT == CompiledAOT == LIN-Generated-GPU-Kernel
//!
//! @LIN:GPU_AUTO_LOWERING:1.0.0

const std = @import("std");
const engine  = @import("src/lin_mir_engine.zig");
const generic_jit = @import("src/lin_mir_generic_jit.zig");
const lowerer = @import("src/lin_mir_gpu_lowerer.zig");
const MirType = engine.MirType;
const MirOpcode = engine.MirOpcode;
const MirInst = engine.MirInst;
const MirBlock = engine.MirBlock;
const MirFunction = engine.MirFunction;
const MirVm = engine.MirVm;
const GenericJitEngine = generic_jit.GenericJitEngine;
const MirToOpenCLLowerer = lowerer.MirToOpenCLLowerer;

// Unified PRNG: Fibonacci hashing (identical in Zig and C)
fn unified_prng_i32(i: usize) i32 {
    const v: u32 = @truncate((i + 1) *% 0x9e3779b9);
    return @bitCast(v);
}

// AOT oracle (native Zig, compile-time exact)
fn aot_kernel(x: i32) i32 {
    return x *% 3 +% 7;
}

// OpenCL C API via @cImport
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
    try stdout.print("=== LIN-GPU-003: MIR-to-GPU AUTOMATIC LOWERING — AMD RX 6600 (gfx1030)     ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    // ── 1. Define MIR kernel ──────────────────────────────────────────────────
    const kernel_insts = [_]MirInst{
        .{ .opcode = .param,     .ty = .i64, .dst = 0, .imm = 0 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 1, .imm = 3 },
        .{ .opcode = .mul,       .ty = .i64, .dst = 2, .lhs = 0, .rhs = 1 },
        .{ .opcode = .const_val, .ty = .i64, .dst = 3, .imm = 7 },
        .{ .opcode = .add,       .ty = .i64, .dst = 4, .lhs = 2, .rhs = 3 },
        .{ .opcode = .ret_op,    .ty = .i64, .lhs = 4 },
    };
    const kernel_blocks = [_]MirBlock{.{ .id = 0, .instructions = &kernel_insts }};
    const kernel_params  = [_]MirType{.i64};
    const kernel_func = MirFunction{
        .name    = "parallel_map_kernel_i32",
        .params  = &kernel_params,
        .returns = .i32,
        .blocks  = &kernel_blocks,
    };

    // ── 2. Auto-lower MIR → OpenCL C ─────────────────────────────────────────
    const result = try MirToOpenCLLowerer.lower(alloc, kernel_func, "parallel_map_i32_auto");
    defer result.deinit(alloc);

    try stdout.print("[LOWERER] MIR → OpenCL C generated ({d} bytes)\n", .{result.source.len});
    try stdout.print("[LOWERER] mir_semantic_hash = sha256:{s}\n\n", .{std.fmt.fmtSliceHexLower(&result.mir_semantic_hash)});
    try stdout.print("--- BEGIN GENERATED OpenCL C ---\n{s}--- END GENERATED OpenCL C ---\n\n", .{result.source});

    // ── 3. Compile JIT ───────────────────────────────────────────────────────
    var jit_fn = try GenericJitEngine.compile(kernel_func);
    defer jit_fn.deinit();

    // ── 4. OpenCL device setup ────────────────────────────────────────────────
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
            std.mem.indexOf(u8, pname, "ROCm") != null)
        {
            ocl_platform = plat;
            break;
        }
    }

    var num_devs: cl.cl_uint = 0;
    _ = cl.clGetDeviceIDs(ocl_platform, cl.CL_DEVICE_TYPE_GPU, 0, null, &num_devs);
    const devs = try alloc.alloc(cl.cl_device_id, num_devs);
    defer alloc.free(devs);
    _ = cl.clGetDeviceIDs(ocl_platform, cl.CL_DEVICE_TYPE_GPU, num_devs, devs.ptr, null);
    const dev = devs[0];

    var dname_buf: [256]u8 = undefined;
    _ = cl.clGetDeviceInfo(dev, cl.CL_DEVICE_NAME, dname_buf.len, &dname_buf, null);
    const dname = std.mem.sliceTo(&dname_buf, 0);
    try stdout.print("[DEVICE] {s}\n\n", .{dname});

    var err: cl.cl_int = 0;
    const ctx   = cl.clCreateContext(null, 1, &dev, null, null, &err);
    try cl_check(err, "clCreateContext");
    defer _ = cl.clReleaseContext(ctx);

    const queue = cl.clCreateCommandQueueWithProperties(ctx, dev, null, &err);
    try cl_check(err, "clCreateCommandQueue");
    defer _ = cl.clReleaseCommandQueue(queue);

    // Build with auto-generated source
    var src_ptr: [*c]const u8 = result.source.ptr;
    var src_len: usize = result.source.len;
    const prog = cl.clCreateProgramWithSource(ctx, 1, @ptrCast(&src_ptr), &src_len, &err);
    try cl_check(err, "clCreateProgramWithSource");
    defer _ = cl.clReleaseProgram(prog);

    err = cl.clBuildProgram(prog, 1, &dev, "-cl-std=CL2.0", null, null);
    if (err != cl.CL_SUCCESS) {
        var log_size: usize = 0;
        _ = cl.clGetProgramBuildInfo(prog, dev, cl.CL_PROGRAM_BUILD_LOG, 0, null, &log_size);
        const log = try alloc.alloc(u8, log_size + 1);
        defer alloc.free(log);
        _ = cl.clGetProgramBuildInfo(prog, dev, cl.CL_PROGRAM_BUILD_LOG, log_size, log.ptr, null);
        try stdout.print("[BUILD ERROR]\n{s}\n", .{log});
        return error.OpenCLBuildFailed;
    }
    try stdout.print("[LOWERER] OpenCL build: OK\n\n", .{});

    const kernel = cl.clCreateKernel(prog, "parallel_map_i32_auto", &err);
    try cl_check(err, "clCreateKernel");
    defer _ = cl.clReleaseKernel(kernel);

    // ── 5. Differential test matrix ───────────────────────────────────────────
    const SIZES = [_]usize{ 1, 2, 7, 31, 1024, 65536, 1_000_000 };
    var total_confirmed: usize = 0;
    var total_elements: usize = 0;

    for (SIZES, 1..) |n, idx| {
        const h_in  = try alloc.alloc(i32, n);
        defer alloc.free(h_in);
        const vm_out  = try alloc.alloc(i32, n);
        defer alloc.free(vm_out);
        const jit_out = try alloc.alloc(i32, n);
        defer alloc.free(jit_out);
        const aot_out = try alloc.alloc(i32, n);
        defer alloc.free(aot_out);
        const gpu_out = try alloc.alloc(i32, n);
        defer alloc.free(gpu_out);

        // Unified PRNG — same formula in C harness
        for (h_in, 0..) |*v, i| v.* = unified_prng_i32(i);

        // MirVm
        var vm = MirVm.init();
        for (h_in, 0..) |x, i| {
            const args = [_]i64{@as(i64, x)};
            vm_out[i] = @as(i32, @truncate(try vm.execute(kernel_func, &args)));
        }
        // JIT
        for (h_in, 0..) |x, i|
            jit_out[i] = @as(i32, @truncate(jit_fn.fn_ptr(@as(i64, x), 0)));
        // AOT
        for (h_in, 0..) |x, i|
            aot_out[i] = aot_kernel(x);

        // GPU — auto-generated kernel
        const d_in  = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_ONLY,  n*4, null, &err);
        defer _ = cl.clReleaseMemObject(d_in);
        const d_out = cl.clCreateBuffer(ctx, cl.CL_MEM_WRITE_ONLY, n*4, null, &err);
        defer _ = cl.clReleaseMemObject(d_out);

        _ = cl.clEnqueueWriteBuffer(queue, d_in, cl.CL_TRUE, 0, n*4, h_in.ptr, 0, null, null);

        const nn: cl.cl_int = @intCast(n);
        _ = cl.clSetKernelArg(kernel, 0, @sizeOf(cl.cl_mem), @ptrCast(&d_in));
        _ = cl.clSetKernelArg(kernel, 1, @sizeOf(cl.cl_mem), @ptrCast(&d_out));
        _ = cl.clSetKernelArg(kernel, 2, @sizeOf(cl.cl_int), &nn);

        const local_ws: usize = 256;
        const global_ws: usize = ((n + local_ws - 1) / local_ws) * local_ws;

        var ev: cl.cl_event = undefined;
        _ = cl.clEnqueueNDRangeKernel(queue, kernel, 1, null, &global_ws, &local_ws, 0, null, &ev);
        _ = cl.clWaitForEvents(1, &ev);
        _ = cl.clReleaseEvent(ev);

        _ = cl.clEnqueueReadBuffer(queue, d_out, cl.CL_TRUE, 0, n*4, gpu_out.ptr, 0, null, null);

        // Verify all 4 executors agree
        var ok = true;
        for (0..n) |i| {
            const exp = aot_kernel(h_in[i]);
            if (vm_out[i] != exp or jit_out[i] != exp or aot_out[i] != exp or gpu_out[i] != exp) {
                ok = false;
                try stdout.print("[GPU-003 {d}/7] N={d} DIVERGENCE at i={d}: vm={d} jit={d} aot={d} gpu={d} exp={d}\n",
                    .{ idx, n, i, vm_out[i], jit_out[i], aot_out[i], gpu_out[i], exp });
                break;
            }
        }
        if (ok) {
            total_confirmed += 1;
            total_elements  += n;
            try stdout.print("[GPU-003 {d}/7] N={d:<8} VM=OK JIT=OK AOT=OK GPU(auto)=OK  BIT_EXACT (CONFIRMED)\n", .{ idx, n });
        }
    }

    // ── 6. RULEL blocks ───────────────────────────────────────────────────────
    try stdout.print("\n@LIN:MIR_GPU_LOWERER:1.0.0\n", .{});
    try stdout.print(".lowerer=\"MirToOpenCLLowerer\"\n", .{});
    try stdout.print(".mir_function=\"{s}\"\n", .{kernel_func.name});
    try stdout.print(".mir_semantic_hash=\"sha256:{s}\"\n", .{std.fmt.fmtSliceHexLower(&result.mir_semantic_hash)});
    try stdout.print(".output_language=\"OpenCL C 2.0\"\n", .{});
    try stdout.print(".kernel_name=\"{s}\"\n", .{result.kernel_name});
    try stdout.print(".hand_written=false\n", .{});
    try stdout.print(".auto_lowered=true\n\n", .{});

    try stdout.print("@LIN:GPU_AUTO_LOWERING:1.0.0\n", .{});
    try stdout.print(".device=\"{s}\"\n", .{dname});
    try stdout.print(".operation=\"parallel_map\"\n", .{});
    try stdout.print(".element_type=\"i32\"\n", .{});
    try stdout.print(".prng=\"fibonacci_hashing(i+1)*0x9e3779b9\"\n", .{});
    try stdout.print(".prng_portable=true\n", .{});
    try stdout.print(".mir_semantic_hash=\"sha256:{s}\"\n", .{std.fmt.fmtSliceHexLower(&result.mir_semantic_hash)});
    try stdout.print(".matrix_sizes=[1,2,7,31,1024,65536,1000000]\n", .{});
    try stdout.print(".total_elements={d}\n", .{total_elements});
    try stdout.print(".targets=7\n", .{});
    try stdout.print(".confirmed={d}\n", .{total_confirmed});
    try stdout.print(".refuted={d}\n", .{7 - total_confirmed});
    try stdout.print(".cross_backend={{\n  vm=true,\n  jit=true,\n  aot=true,\n  gpu_auto_generated=true\n}}\n", .{});
    try stdout.print(".equivalence=\"BIT_EXACT\"\n", .{});

    if (total_confirmed == 7) {
        try stdout.print(".status=\"PASS\"\n", .{});
    } else {
        try stdout.print(".status=\"FAIL\"\n", .{});
        std.process.exit(1);
    }
}
