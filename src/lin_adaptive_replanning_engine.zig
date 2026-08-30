//! lin_adaptive_replanning_engine.zig — Dynamic Adaptive Re-Planning & Non-Retroactive Chaining (LIN-LANG-008)
//!
//! Architectural Invariants:
//!   1. Mandatory observable plan shift: Plan_{v1} != Plan_{v2} for all 3 drift scenarios.
//!   2. Explicit drift mode classification: Physical Measurement vs Controlled Cost/Residency Injection.
//!   3. Zero Semantic Drift Invariant: R_{v1} ==_C R_{v2} ==_C R_Oracle bit-exact.
//!   4. Non-Retroactive Merkle Chaining: Root_{v2} = H(Root_{v1} || DriftDelta || Plan_{v2} || Execution_{v2}).

const std = @import("std");
const ir = @import("lin_gpu_ir.zig");
const lowerer = @import("lin_mir_to_gpu_ir.zig");
const emitter = @import("lin_gpu_ir_to_opencl.zig");
const oracle = @import("lin_gpu_execution_oracle.zig");
const planner = @import("lin_workload_planner.zig");
const verifier = @import("lin_heterogeneous_verifier.zig");

const GpuModule = ir.GpuModule;
const MirToGpuIrLowerer = lowerer.MirToGpuIrLowerer;
const GpuIrToOpenClEmitter = emitter.GpuIrToOpenClEmitter;
const UniversalGpuOracle = oracle.UniversalGpuOracle;
const WorkloadDescriptor = planner.WorkloadDescriptor;
const CostModel = planner.CostModel;
const ExecutionPlanner = planner.ExecutionPlanner;
const HeterogeneousVerifier = verifier.HeterogeneousVerifier;

pub const DriftMechanism = enum {
    physical_scale_shift,
    controlled_cost_injection,
    injected_residency_eviction,
};

pub const DriftScenarioRecord = struct {
    id: usize,
    name: []const u8,
    mechanism: DriftMechanism,
    plan_v1_backend: planner.BackendTarget,
    plan_v2_backend: planner.BackendTarget,
    decision_changed: bool,
    r_v1: i32,
    r_v2: i32,
    r_oracle: i32,
    semantic_preservation_ok: bool,
    cost_v1_ns: u64,
    cost_v2_ns: u64,
};

pub const AdaptiveRePlanningEngine = struct {
    pub fn planBaseline(n_elements: usize) planner.ExecutionDecision {
        const cost_model = CostModel{};
        const wl = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n_elements,
            .layout = .{ .data_bytes = n_elements * @sizeOf(i32) },
            .reuse_count = 50,
            .dependencies = .{ .transfer_amortization_eligible = true },
            .input_residency = .host_ram,
            .output_residency = .gpu_vram,
        };
        return ExecutionPlanner.plan(wl, cost_model, true);
    }

    pub fn planDriftScenario1(n_elements: usize) planner.ExecutionDecision {
        _ = n_elements;
        const cost_model = CostModel{};
        // Scale collapse to N=128 (N < N*)
        const wl = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = 128,
            .layout = .{ .data_bytes = 128 * @sizeOf(i32) },
            .reuse_count = 1,
            .dependencies = .{ .transfer_amortization_eligible = false },
            .input_residency = .host_ram,
            .output_residency = .host_ram,
        };
        return ExecutionPlanner.plan(wl, cost_model, true);
    }

    pub fn planDriftScenario2(n_elements: usize) planner.ExecutionDecision {
        // PCIe Throttling injection (cost per byte spiked)
        var cost_model = CostModel{};
        cost_model.gpu_h2d_ns_per_byte = 3.0;
        cost_model.gpu_d2h_ns_per_byte = 3.0;

        const wl = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n_elements,
            .layout = .{ .data_bytes = n_elements * @sizeOf(i32) },
            .reuse_count = 1,
            .dependencies = .{ .transfer_amortization_eligible = false },
            .input_residency = .host_ram,
            .output_residency = .host_ram,
        };
        return ExecutionPlanner.plan(wl, cost_model, true);
    }

    pub fn planDriftScenario3(n_elements: usize) planner.ExecutionDecision {
        const cost_model = CostModel{};
        // Injected residency eviction from VRAM to Host RAM with single-shot execution
        const wl = WorkloadDescriptor{
            .op = .reduce,
            .elem_type = .i32,
            .accum_type = .i32,
            .reduction_op = .sum,
            .total_elements = n_elements,
            .layout = .{ .data_bytes = n_elements * @sizeOf(i32) },
            .reuse_count = 1,
            .dependencies = .{ .transfer_amortization_eligible = false },
            .input_residency = .host_ram,
            .output_residency = .host_ram,
        };
        return ExecutionPlanner.plan(wl, cost_model, true);
    }

    pub fn computeRootV1(initial_plan: planner.ExecutionDecision, initial_result: i32) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-LANG-008-ROOT-V1");
        h.update(@tagName(initial_plan.backend));
        h.update(std.mem.asBytes(&initial_result));
        var root: [32]u8 = undefined;
        h.final(&root);
        return root;
    }

    pub fn computeRootV2NonRetroactive(
        root_v1: [32]u8,
        scenarios: []const DriftScenarioRecord,
    ) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-LANG-008-ROOT-V2-NON-RETROACTIVE");
        h.update(&root_v1);
        for (scenarios) |s| {
            h.update(@tagName(s.mechanism));
            h.update(@tagName(s.plan_v1_backend));
            h.update(@tagName(s.plan_v2_backend));
            h.update(std.mem.asBytes(&s.decision_changed));
            h.update(std.mem.asBytes(&s.r_v2));
        }
        var root: [32]u8 = undefined;
        h.final(&root);
        return root;
    }
};
