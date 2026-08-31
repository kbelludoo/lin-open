// redteam/spoof_main.zig — PoC: "burlar" a verificação CPU/GPU do LIN.
//
// Reproduz a lógica de paridade do runner: roda o kernel no "GPU" (aqui, um
// runtime OpenCL FALSO que fabrica o resultado) e compara com o resultado da VM
// CPU. O resultado imprime BIT_EXACT mesmo sem existir GPU nenhuma.
const std = @import("std");
const cl = @cImport({
    @cDefine("CL_TARGET_OPENCL_VERSION", "200");
    @cInclude("CL/cl.h");
});

fn clCheck(err: cl.cl_int, msg: []const u8) !void {
    _ = msg;
    if (err != cl.CL_SUCCESS) return error.OpenCLError;
}

// CPU: mesmo cálculo que o kernel do LIN faz (out = in*2 + 1), somado.
fn cpuReduce(input: []const i32) i32 {
    var acc: i32 = 0;
    for (input) |v| acc +%= (v *% 2 +% 1);
    return acc;
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();

    // Descobre a "plataforma" (forjada pelo runtime fake).
    var nplat: cl.cl_uint = 0;
    _ = cl.clGetPlatformIDs(0, null, &nplat);
    const plats = try a.alloc(cl.cl_platform_id, nplat);
    _ = cl.clGetPlatformIDs(nplat, plats.ptr, null);
    const plat = plats[0];

    var pbuf: [256]u8 = undefined;
    _ = cl.clGetPlatformInfo(plat, cl.CL_PLATFORM_NAME, pbuf.len, &pbuf, null);
    const plat_name = std.mem.sliceTo(&pbuf, 0);

    var ndev: cl.cl_uint = 0;
    _ = cl.clGetDeviceIDs(plat, cl.CL_DEVICE_TYPE_GPU, 0, null, &ndev);
    const devs = try a.alloc(cl.cl_device_id, ndev);
    _ = cl.clGetDeviceIDs(plat, cl.CL_DEVICE_TYPE_GPU, ndev, devs.ptr, null);
    const dev = devs[0];

    var dbuf: [256]u8 = undefined;
    _ = cl.clGetDeviceInfo(dev, cl.CL_DEVICE_NAME, dbuf.len, &dbuf, null);
    const dev_name = std.mem.sliceTo(&dbuf, 0);

    var err: cl.cl_int = undefined;
    const ctx = cl.clCreateContext(null, 1, &dev, null, null, &err);
    try clCheck(err, "ctx");
    const queue = cl.clCreateCommandQueueWithProperties(ctx, dev, null, &err);
    try clCheck(err, "queue");

    // Dados
    const n: usize = 1024;
    const input = try a.alloc(i32, n);
    for (input, 0..) |*x, i| x.* = @intCast(i + 1);
    const gpu_out = try a.alloc(i32, n);

    // Kernel
    const src = "fake kernel source";
    const src_ptr: ?[*]const u8 = src.ptr;
    const src_len: usize = src.len;
    const prog = cl.clCreateProgramWithSource(ctx, 1, @ptrCast(@constCast(&src_ptr)), &src_len, &err);
    try clCheck(err, "prog");
    _ = cl.clBuildProgram(prog, 1, &dev, null, null, null);
    const kern = cl.clCreateKernel(prog, "lin_gpu_kernel", &err);
    try clCheck(err, "kernel");

    const d_in = cl.clCreateBuffer(ctx, cl.CL_MEM_READ_ONLY, n * 4, null, &err);
    const d_out = cl.clCreateBuffer(ctx, cl.CL_MEM_WRITE_ONLY, n * 4, null, &err);
    _ = cl.clEnqueueWriteBuffer(queue, d_in, cl.CL_TRUE, 0, n * 4, input.ptr, 0, null, null);
    _ = cl.clSetKernelArg(kern, 0, @sizeOf(cl.cl_mem), @ptrCast(&d_in));
    _ = cl.clSetKernelArg(kern, 1, @sizeOf(cl.cl_mem), @ptrCast(&d_out));
    const nn: cl.cl_int = @intCast(n);
    _ = cl.clSetKernelArg(kern, 2, @sizeOf(cl.cl_int), &nn);
    _ = cl.clEnqueueNDRangeKernel(queue, kern, 1, null, &n, null, 0, null, null);
    _ = cl.clEnqueueReadBuffer(queue, d_out, cl.CL_TRUE, 0, n * 4, gpu_out.ptr, 0, null, null);

    // Comparação de paridade
    const r_cpu = cpuReduce(input);
    var r_gpu: i32 = 0;
    for (gpu_out) |v| r_gpu +%= v;

    try stdout.print("Plataforma reportada: {s}\n", .{plat_name});
    try stdout.print("Dispositivo reportado: {s}\n", .{dev_name});
    try stdout.print("R_cpu={d}  R_gpu={d}  -> {s}\n", .{ r_cpu, r_gpu, if (r_cpu == r_gpu) "BIT_EXACT [PASS]" else "DIVERGENCE [FAIL]" });
    try stdout.print("\n=> VERIFICADOR IMPRIME BIT_EXACT/SUCESSO SEM EXISTIR GPU.\n", .{});
}
