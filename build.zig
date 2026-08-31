const std = @import("std");

// LIN build (Zig 0.13.0)
//
// Modes:
//   zig build                 -> GPU build (links OpenCL/ROCm; needs CL headers)
//   zig build -Dgpu=false     -> CPU-only build (uses a local CL stub header,
//                                no OpenCL toolchain required). GPU commands
//                                then report "no OpenCL platform" gracefully.
//
// Output: zig-out/bin/lin_native

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const gpu = b.option(bool, "gpu", "Enable the OpenCL/GPU subsystem (default true)") orelse true;

    const exe = b.addExecutable(.{
        .name = "lin_native",
        .root_source_file = b.path("compiler/lin.zig"),
        .target = target,
        .optimize = optimize,
    });
    exe.linkLibC();

    if (gpu) {
        exe.linkSystemLibrary("OpenCL");
        // CL/cl.h is normally under /usr/include (or /opt/rocm/include on AMD).
        exe.addIncludePath(.{ .cwd_relative = "/usr/include" });
    } else {
        // CPU-only: provide a stub CL/cl.h + stub.c so the same source compiles
        // and links without an OpenCL toolchain. Stub runtime discovery returns
        // 0 platforms, so GPU commands fail gracefully instead of crashing.
        exe.addIncludePath(b.path("stubs"));
        exe.addCSourceFile(.{ .file = b.path("stubs/CL/stub.c"), .flags = &.{} });
    }

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());
    if (b.args) |args| run_cmd.addArgs(args);
    const run_step = b.step("run", "Run LIN");
    run_step.dependOn(&run_cmd.step);
}
