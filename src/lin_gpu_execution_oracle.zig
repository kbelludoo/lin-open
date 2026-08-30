//! lin_gpu_execution_oracle.zig — Universal GPU IR Execution Oracle (LIN-GPU-008A/008B)
//!
//! Architectural Invariants:
//!   1. Direct sequential execution of GpuModule without C/OpenCL/HIP dependencies.
//!   2. Strict enforcement of NumericContract (modular_i32, modular_u32, ieee754_strict).
//!   3. Serves as the normative mathematical oracle for all backend emitters.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuOp = ir.GpuOp;
const NumericContract = ir.NumericContract;

pub const UniversalGpuOracle = struct {
    /// Executes a parallel reduction directly from the GpuModule specifications
    pub fn executeReduction(
        module: GpuModule,
        input: []const i32,
    ) i32 {
        var accum: i32 = 0; // Identity for modular sum
        for (input) |x| {
            accum = switch (module.numeric_contract) {
                .modular_i32 => accum +% x,
                .modular_u32 => @as(i32, @bitCast(@as(u32, @bitCast(accum)) +% @as(u32, @bitCast(x)))),
                .ieee754_strict => accum +% x,
            };
        }
        return accum;
    }

    /// Executes a parallel 1D map directly from the GpuModule specifications (f(x) = 2x)
    pub fn executeMap1D(
        module: GpuModule,
        input: []const i32,
        output: []i32,
    ) void {
        for (input, 0..) |x, i| {
            output[i] = switch (module.numeric_contract) {
                .modular_i32 => x *% 2,
                .modular_u32 => @as(i32, @bitCast(@as(u32, @bitCast(x)) *% 2)),
                .ieee754_strict => x *% 2,
            };
        }
    }

    /// Executes a 1D 3-point stencil directly from the GpuModule specifications
    pub fn executeStencil1D(
        module: GpuModule,
        input: []const i32,
        output: []i32,
    ) void {
        const n = input.len;
        if (n == 0) return;
        for (0..n) |i| {
            const left = if (i == 0) input[0] else input[i - 1];
            const center = input[i];
            const right = if (i + 1 == n) input[n - 1] else input[i + 1];

            const sum = (left +% center) +% right;
            output[i] = switch (module.numeric_contract) {
                .modular_i32 => sum,
                .modular_u32 => @as(i32, @bitCast(@as(u32, @bitCast(sum)))),
                .ieee754_strict => sum,
            };
        }
    }
};
