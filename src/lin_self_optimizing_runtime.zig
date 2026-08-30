//! lin_self_optimizing_runtime.zig — LIN-GPU-011
//! Deterministic empirical profiling, CostModel evolution, adaptive decision hashing,
//! and non-retroactive provenance chaining.

const std = @import("std");
const planner = @import("lin_workload_planner.zig");

pub const CostModel = planner.CostModel;
pub const ExecutionDecision = planner.ExecutionDecision;

pub const TimingSample = struct {
    elements: u64,
    bytes: u64,
    cpu_ns: u64,
    gpu_compute_ns: u64,
    h2d_ns: u64,
    d2h_ns: u64,
};

pub const ProfileSummary = struct {
    sample_count: usize,
    cpu_r2: f64,
    gpu_r2: f64,
    h2d_r2: f64,
    d2h_r2: f64,
    cpu_intercept_ns: f64,
    cpu_ns_per_element: f64,
    gpu_launch_ns: f64,
    gpu_ns_per_element: f64,
    h2d_intercept_ns: f64,
    h2d_ns_per_byte: f64,
    d2h_intercept_ns: f64,
    d2h_ns_per_byte: f64,
};

pub const EvolutionRecord = struct {
    parent_model_hash: [32]u8,
    child_model_hash: [32]u8,
    sample_set_hash: [32]u8,
    version_from: u32,
    version_to: u32,
    minimum_r2: f64,
    achieved_r2: f64,
};

pub const EvolutionResult = struct {
    model: CostModel,
    profile: ProfileSummary,
    record: EvolutionRecord,
};

fn regression(xs: []const f64, ys: []const f64) struct { intercept: f64, slope: f64, r2: f64 } {
    std.debug.assert(xs.len == ys.len);
    std.debug.assert(xs.len >= 2);

    var sx: f64 = 0.0;
    var sy: f64 = 0.0;
    for (xs, ys) |x, y| {
        sx += x;
        sy += y;
    }

    const n = @as(f64, @floatFromInt(xs.len));
    const mx = sx / n;
    const my = sy / n;

    var sxx: f64 = 0.0;
    var sxy: f64 = 0.0;
    var sst: f64 = 0.0;
    for (xs, ys) |x, y| {
        const dx = x - mx;
        const dy = y - my;
        sxx += dx * dx;
        sxy += dx * dy;
        sst += dy * dy;
    }

    const slope = if (sxx == 0.0) 0.0 else sxy / sxx;
    const intercept = my - slope * mx;

    var sse: f64 = 0.0;
    for (xs, ys) |x, y| {
        const residual = y - (intercept + slope * x);
        sse += residual * residual;
    }

    const raw_r2 = if (sst == 0.0) 1.0 else 1.0 - sse / sst;
    return .{
        .intercept = intercept,
        .slope = slope,
        .r2 = std.math.clamp(raw_r2, -1.0, 1.0),
    };
}

pub const SelfOptimizingRuntime = struct {
    pub const minimum_r2: f64 = 0.99;

    pub fn computeSampleSetHash(samples: []const TimingSample) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-011-SAMPLE-SET-V1");
        for (samples) |s| {
            h.update(std.mem.asBytes(&s.elements));
            h.update(std.mem.asBytes(&s.bytes));
            h.update(std.mem.asBytes(&s.cpu_ns));
            h.update(std.mem.asBytes(&s.gpu_compute_ns));
            h.update(std.mem.asBytes(&s.h2d_ns));
            h.update(std.mem.asBytes(&s.d2h_ns));
        }
        var out: [32]u8 = undefined;
        h.final(&out);
        return out;
    }

    pub fn summarize(allocator: std.mem.Allocator, samples: []const TimingSample) !ProfileSummary {
        if (samples.len < 4) return error.InsufficientSamples;

        const xe = try allocator.alloc(f64, samples.len);
        defer allocator.free(xe);
        const xb = try allocator.alloc(f64, samples.len);
        defer allocator.free(xb);
        const cpu = try allocator.alloc(f64, samples.len);
        defer allocator.free(cpu);
        const gpu = try allocator.alloc(f64, samples.len);
        defer allocator.free(gpu);
        const h2d = try allocator.alloc(f64, samples.len);
        defer allocator.free(h2d);
        const d2h = try allocator.alloc(f64, samples.len);
        defer allocator.free(d2h);

        for (samples, 0..) |s, i| {
            xe[i] = @floatFromInt(s.elements);
            xb[i] = @floatFromInt(s.bytes);
            cpu[i] = @floatFromInt(s.cpu_ns);
            gpu[i] = @floatFromInt(s.gpu_compute_ns);
            h2d[i] = @floatFromInt(s.h2d_ns);
            d2h[i] = @floatFromInt(s.d2h_ns);
        }

        const rcpu = regression(xe, cpu);
        const rgpu = regression(xe, gpu);
        const rh2d = regression(xb, h2d);
        const rd2h = regression(xb, d2h);

        return .{
            .sample_count = samples.len,
            .cpu_r2 = rcpu.r2,
            .gpu_r2 = rgpu.r2,
            .h2d_r2 = rh2d.r2,
            .d2h_r2 = rd2h.r2,
            .cpu_intercept_ns = rcpu.intercept,
            .cpu_ns_per_element = rcpu.slope,
            .gpu_launch_ns = @max(0.0, rgpu.intercept),
            .gpu_ns_per_element = @max(0.0, rgpu.slope),
            .h2d_intercept_ns = @max(0.0, rh2d.intercept),
            .h2d_ns_per_byte = @max(0.0, rh2d.slope),
            .d2h_intercept_ns = @max(0.0, rd2h.intercept),
            .d2h_ns_per_byte = @max(0.0, rd2h.slope),
        };
    }

    pub fn evolveCostModel(
        allocator: std.mem.Allocator,
        parent: CostModel,
        samples: []const TimingSample,
    ) !EvolutionResult {
        const p = try summarize(allocator, samples);
        const achieved = @min(p.cpu_r2, @min(p.gpu_r2, @min(p.h2d_r2, p.d2h_r2)));
        if (achieved < minimum_r2)
            return error.ModelFitBelowRequiredR2;

        var child = parent;
        child.version = parent.version + 1;
        child.cpu_intercept_ns = p.cpu_intercept_ns;
        child.cpu_ns_per_element = p.cpu_ns_per_element;
        child.gpu_launch_ns = p.gpu_launch_ns;
        child.gpu_compute_ns_per_element = p.gpu_ns_per_element;
        child.gpu_h2d_ns_per_byte = p.h2d_ns_per_byte;
        child.gpu_d2h_ns_per_byte = p.d2h_ns_per_byte;
        child.fit_quality = achieved;
        child.measurement_count = @intCast(samples.len);

        return .{
            .model = child,
            .profile = p,
            .record = .{
                .parent_model_hash = parent.computeModelHash(),
                .child_model_hash = child.computeModelHash(),
                .sample_set_hash = computeSampleSetHash(samples),
                .version_from = parent.version,
                .version_to = child.version,
                .minimum_r2 = minimum_r2,
                .achieved_r2 = achieved,
            },
        };
    }

    pub fn decisionHash(decision: ExecutionDecision) [32]u8 {
        return decision.computeDecisionHash();
    }

    pub fn semanticResultHash(result: i32) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-011-SEMANTIC-RESULT-V1");
        h.update(std.mem.asBytes(&result));
        var out: [32]u8 = undefined;
        h.final(&out);
        return out;
    }

    /// v2 root is chained to v1. No operation here can mutate or replace v1.
    pub fn computeEvolutionRoot(
        parent_root: [32]u8,
        parent_model_hash: [32]u8,
        child_model_hash: [32]u8,
        sample_set_hash: [32]u8,
        old_decision_hash: [32]u8,
        new_decision_hash: [32]u8,
        semantic_result_hash: [32]u8,
    ) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-011-EVOLUTION-ROOT-V1");
        h.update(&parent_root);
        h.update(&parent_model_hash);
        h.update(&child_model_hash);
        h.update(&sample_set_hash);
        h.update(&old_decision_hash);
        h.update(&new_decision_hash);
        h.update(&semantic_result_hash);
        var out: [32]u8 = undefined;
        h.final(&out);
        return out;
    }

    pub fn crossoverN(model: CostModel, bytes_per_element: f64) f64 {
        const beta_cpu = model.cpu_ns_per_element;
        const beta_gpu = model.gpu_compute_ns_per_element;
        const gpu_fixed = model.gpu_launch_ns +
            model.gpu_h2d_ns_per_byte * bytes_per_element +
            model.gpu_d2h_ns_per_byte * 4.0;
        if (beta_cpu <= beta_gpu) return std.math.inf(f64);
        return gpu_fixed / (beta_cpu - beta_gpu);
    }
};
