const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const exe = b.addExecutable(.{
        .name = "lin",
        .root_source_file = b.path("bin/lin.zig"),
        .target = target,
        .optimize = optimize,
    });
    // Allow bin/lin.zig to @import("../src/lin_compiler.zig")
    exe.root_module.addAnonymousImport("lin_compiler", .{
        .root_source_file = b.path("src/lin_compiler.zig"),
    });
    b.installArtifact(exe);

    const run_step = b.step("run", "Run lin zig CLI");
    const run_cmd = b.addRunArtifact(exe);
    run_step.dependOn(&run_cmd.step);
    if (b.args) |args| {
        run_cmd.addArgs(args);
    }
}
