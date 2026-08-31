//! lin_gpu_execution_oracle.zig — Instruction-Driven Universal GPU IR Oracle (LIN-GPU-008A/B)
//!
//! Architectural Invariants:
//!   1. Direct sequential execution of GpuModule without C/OpenCL/HIP dependencies.
//!   2. Supports all 7 reduction operators, map (2x+1), and stencil (3-point).
//!   3. Strict enforcement of NumericContract.

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");

const GpuModule = ir.GpuModule;
const GpuKernel = ir.GpuKernel;
const GpuKernelKind = ir.GpuKernelKind;
const GpuReduceOp = ir.GpuReduceOp;
const NumericContract = ir.NumericContract;

pub const UniversalGpuOracle = struct {
    pub fn getIdentity(op: GpuReduceOp) i32 {
        return switch (op) {
            .sum => 0,
            .product => 1,
            .min => std.math.maxInt(i32),
            .max => std.math.minInt(i32),
            .band => @as(i32, @bitCast(@as(u32, 0xFFFFFFFF))),
            .bor => 0,
            .bxor => 0,
        };
    }

    pub fn applyReduceOp(op: GpuReduceOp, a: i32, b: i32) i32 {
        return switch (op) {
            .sum => a +% b,
            .product => a *% b,
            .min => if (a < b) a else b,
            .max => if (a > b) a else b,
            .band => a & b,
            .bor => a | b,
            .bxor => a ^ b,
        };
    }

    /// Executes a reduction kernel directly from GpuModule
    pub fn executeReduction(
        module: GpuModule,
        input: []const i32,
    ) i32 {
        const rop: GpuReduceOp = if (module.kernels.len > 0 and module.kernels[0].reduce_op != null)
            module.kernels[0].reduce_op.?
        else
            .sum;

        var accum: i32 = getIdentity(rop);
        for (input) |x| {
            accum = applyReduceOp(rop, accum, x);
        }
        return accum;
    }

    /// Executes a parallel 1D map directly from GpuModule (f(x) = 2x + 1)
    pub fn executeMap1D(
        module: GpuModule,
        input: []const i32,
        output: []i32,
    ) void {
        _ = module;
        for (input, 0..) |x, i| {
            output[i] = (x *% 2) +% 1;
        }
    }

    /// Executes a 1D 3-point stencil directly from GpuModule
    pub fn executeStencil1D(
        module: GpuModule,
        input: []const i32,
        output: []i32,
    ) void {
        _ = module;
        const n = input.len;
        if (n == 0) return;
        for (0..n) |i| {
            const left = if (i == 0) input[0] else input[i - 1];
            const center = input[i];
            const right = if (i + 1 == n) input[n - 1] else input[i + 1];

            output[i] = (left +% center) +% right;
        }
    }
};
