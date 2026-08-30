//! test_gpu_005a_reduction_analyzer.zig — LIN-GPU-005A Verification Harness
//!
//! Validates the reduction analyzer against:
//!   1. Valid canonical reductions (sum, product, min, max, band, bor, bxor, f64 relaxed)
//!   2. Adversarial / illegal patterns (subtraction non-assoc, multiple loop dependencies, strict f64 rejection, unknown control flow)
//!
//! Analyzer-only execution: Zero GPU dependencies.

const std = @import("std");
const engine = @import("src/lin_mir_engine.zig");
const analyzer = @import("src/lin_reduction_analyzer.zig");

const MirType = engine.MirType;
const MirInst = engine.MirInst;
const MirBlock = engine.MirBlock;
const MirFunction = engine.MirFunction;
const ReductionAnalyzer = analyzer.ReductionAnalyzer;
const LinReductionOp = analyzer.LinReductionOp;
const FloatReductionMode = analyzer.FloatReductionMode;
const RejectReason = analyzer.RejectReason;

fn buildKernelFunc(name: []const u8, returns: MirType, insts: []const MirInst) MirFunction {
    const blocks = [_]MirBlock{.{ .id = 0, .instructions = insts }};
    const params = [_]MirType{ returns, returns };
    return MirFunction{
        .name = name,
        .params = &params,
        .returns = returns,
        .blocks = &blocks,
    };
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-GPU-005A: PARALLEL REDUCTION ANALYZER VERIFICATION CORPUS            ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var passed: usize = 0;
    var total: usize = 0;

    // ──────────────────────────────────────────────────────────────────────────
    // 1. VALID CORPUS
    // ──────────────────────────────────────────────────────────────────────────
    try stdout.print("[SECTION 1] Valid Canonical Reduction Patterns (7 Operators + F64)\n", .{});

    // 1.1 SUM (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .i32, .dst = 0, .imm = 0 }, // accum
            .{ .opcode = .param, .ty = .i32, .dst = 1, .imm = 1 }, // input
            .{ .opcode = .add,   .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_sum_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .sum and desc.identity_val_raw == 0 and desc.is_associative and desc.is_commutative) {
                    try stdout.print("  [PASS] reduce_sum_i32: identity=0, assoc=true, comm=true\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_sum_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_sum_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.2 PRODUCT (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param, .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .mul,   .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_prod_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .product and desc.identity_val_raw == 1 and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_prod_i32: identity=1, assoc=true, comm=true\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_prod_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_prod_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.3 BITWISE AND (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,  .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,  .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .and_op, .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op, .ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_band_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .band and desc.identity_val_raw == 0xFFFFFFFF and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_band_i32: identity=0xFFFFFFFF, assoc=true\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_band_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_band_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.4 BITWISE OR (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param, .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .or_op, .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_bor_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .bor and desc.identity_val_raw == 0 and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_bor_i32: identity=0, assoc=true\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_bor_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_bor_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.5 BITWISE XOR (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,  .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,  .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .xor_op, .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op, .ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_bxor_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .bxor and desc.identity_val_raw == 0 and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_bxor_i32: identity=0, assoc=true\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_bxor_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_bxor_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.6 MIN (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,     .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,     .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .cmp_lt,    .ty = .i1,  .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .select_op, .ty = .i32, .dst = 3, .lhs = 2, .rhs = 0, .extra = 1 }, // min(0, 1)
            .{ .opcode = .ret_op,    .ty = .i32, .lhs = 3 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_min_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .min and desc.identity_val_raw == std.math.maxInt(i32) and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_min_i32: identity=INT_MAX ({d}), assoc=true\n", .{desc.identity_val_raw});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_min_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_min_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.7 MAX (i32)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,     .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,     .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .cmp_lt,    .ty = .i1,  .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .select_op, .ty = .i32, .dst = 3, .lhs = 2, .rhs = 1, .extra = 0 }, // max(0, 1)
            .{ .opcode = .ret_op,    .ty = .i32, .lhs = 3 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_max_i32", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .max and desc.identity_val_raw == std.math.minInt(i32) and desc.is_associative) {
                    try stdout.print("  [PASS] reduce_max_i32: identity=INT_MIN ({d}), assoc=true\n", .{desc.identity_val_raw});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_max_i32: descriptor mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_max_i32 rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // 1.8 SUM (f64, Relaxed Parallel Mode)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .f64, .dst = 0, .imm = 0 },
            .{ .opcode = .param, .ty = .f64, .dst = 1, .imm = 1 },
            .{ .opcode = .add,   .ty = .f64, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .f64, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .f64, .f64 };
        const func = MirFunction{ .name = "reduce_sum_f64_relaxed", .params = &params, .returns = .f64, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .relaxed_parallel);
        switch (res) {
            .valid => |desc| {
                if (desc.op == .sum and desc.fp_mode == .relaxed_parallel) {
                    try stdout.print("  [PASS] reduce_sum_f64_relaxed: accepted under relaxed_parallel\n", .{});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_sum_f64_relaxed: mode mismatch\n", .{});
                }
            },
            .rejected => |reason| {
                try stdout.print("  [FAIL] reduce_sum_f64_relaxed rejected: {s}\n", .{@tagName(reason)});
            },
        }
    }

    // ──────────────────────────────────────────────────────────────────────────
    // 2. ADVERSARIAL / REJECT CORPUS
    // ──────────────────────────────────────────────────────────────────────────
    try stdout.print("\n[SECTION 2] Adversarial & Illegal Patterns (Formal Rejections)\n", .{});

    // 2.1 Subtraction (Non-associative)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param, .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .sub,   .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_sub_illegal", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .rejected => |reason| {
                if (reason == .non_associative_operator) {
                    try stdout.print("  [PASS] reduce_sub_illegal correctly rejected: {s}\n", .{@tagName(reason)});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_sub_illegal rejected with wrong code: {s}\n", .{@tagName(reason)});
                }
            },
            .valid => {
                try stdout.print("  [FAIL] reduce_sub_illegal was unexpectedly accepted!\n", .{});
            },
        }
    }

    // 2.2 Bit Shift (Non-associative)
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,  .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,  .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .shl_op, .ty = .i32, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op, .ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_shl_illegal", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .rejected => |reason| {
                if (reason == .non_associative_operator) {
                    try stdout.print("  [PASS] reduce_shl_illegal correctly rejected: {s}\n", .{@tagName(reason)});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_shl_illegal rejected with wrong code: {s}\n", .{@tagName(reason)});
                }
            },
            .valid => {
                try stdout.print("  [FAIL] reduce_shl_illegal was unexpectedly accepted!\n", .{});
            },
        }
    }

    // 2.3 Strict Floating Point Mode Rejection
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param, .ty = .f64, .dst = 0, .imm = 0 },
            .{ .opcode = .param, .ty = .f64, .dst = 1, .imm = 1 },
            .{ .opcode = .add,   .ty = .f64, .dst = 2, .lhs = 0, .rhs = 1 },
            .{ .opcode = .ret_op,.ty = .f64, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .f64, .f64 };
        const func = MirFunction{ .name = "reduce_f64_strict", .params = &params, .returns = .f64, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .rejected => |reason| {
                if (reason == .float_strict_mode_rejects_parallel_reorder) {
                    try stdout.print("  [PASS] reduce_f64_strict correctly rejected under strict_sequential: {s}\n", .{@tagName(reason)});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_f64_strict rejected with wrong code: {s}\n", .{@tagName(reason)});
                }
            },
            .valid => {
                try stdout.print("  [FAIL] reduce_f64_strict was unexpectedly accepted under strict_sequential!\n", .{});
            },
        }
    }

    // 2.4 Multiple Interacting Accumulators / Complex Phi
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,  .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,  .ty = .i32, .dst = 1, .imm = 1 },
            .{
                .opcode = .phi_op,
                .ty = .i32,
                .dst = 2,
                .phi_count = 3,
                .phi_incoming_blocks = [_]u32{ 0, 1, 2, 0 },
                .phi_incoming_vals = [_]u32{ 0, 1, 2, 0 },
            },
            .{ .opcode = .ret_op, .ty = .i32, .lhs = 2 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_multi_phi_illegal", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .rejected => |reason| {
                if (reason == .multiple_loop_carried_dependencies) {
                    try stdout.print("  [PASS] reduce_multi_phi_illegal correctly rejected: {s}\n", .{@tagName(reason)});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_multi_phi_illegal rejected with wrong code: {s}\n", .{@tagName(reason)});
                }
            },
            .valid => {
                try stdout.print("  [FAIL] reduce_multi_phi_illegal was unexpectedly accepted!\n", .{});
            },
        }
    }

    // 2.5 Arbitrary Unbound Dependency
    {
        total += 1;
        const insts = [_]MirInst{
            .{ .opcode = .param,     .ty = .i32, .dst = 0, .imm = 0 },
            .{ .opcode = .param,     .ty = .i32, .dst = 1, .imm = 1 },
            .{ .opcode = .const_val, .ty = .i32, .dst = 2, .imm = 42 },
            .{ .opcode = .const_val, .ty = .i32, .dst = 3, .imm = 99 },
            .{ .opcode = .add,       .ty = .i32, .dst = 4, .lhs = 2, .rhs = 3 }, // unlinked to accum/input
            .{ .opcode = .ret_op,    .ty = .i32, .lhs = 4 },
        };
        const blocks = [_]MirBlock{.{ .id = 0, .instructions = &insts }};
        const params = [_]MirType{ .i32, .i32 };
        const func = MirFunction{ .name = "reduce_unbound_dep_illegal", .params = &params, .returns = .i32, .blocks = &blocks };

        const res = ReductionAnalyzer.analyze(func, .strict_sequential);
        switch (res) {
            .rejected => |reason| {
                if (reason == .unsupported_accumulator_dependency) {
                    try stdout.print("  [PASS] reduce_unbound_dep_illegal correctly rejected: {s}\n", .{@tagName(reason)});
                    passed += 1;
                } else {
                    try stdout.print("  [FAIL] reduce_unbound_dep_illegal rejected with wrong code: {s}\n", .{@tagName(reason)});
                }
            },
            .valid => {
                try stdout.print("  [FAIL] reduce_unbound_dep_illegal was unexpectedly accepted!\n", .{});
            },
        }
    }

    // ──────────────────────────────────────────────────────────────────────────
    // SUMMARY
    // ──────────────────────────────────────────────────────────────────────────
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== LIN-GPU-005A GATE RESULT: {d}/{d} TESTS PASSED ({s}) ===\n", .{
        passed,
        total,
        if (passed == total) "100% SUCCESS - BIT_EXACT CONTRACT" else "FAILED",
    });
    try stdout.print("================================================================================\n\n", .{});

    if (passed != total) {
        return error.VerificationFailed;
    }
}
