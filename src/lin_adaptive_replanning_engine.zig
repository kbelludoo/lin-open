//! lin_adaptive_replanning_engine.zig — Dynamic Adaptive Re-Planning & Semantic Preservation (LIN-LANG-008)
//!
//! Architectural Invariants:
//!   1. Drift detection: Workload contraction (N=1M -> N=128), PCIe throttling, VRAM eviction.
//!   2. Dynamic re-planning: ArgMin(T_CPU, T_GPU) recalculates optimal backend D* without user intervention.
//!   3. Semantic Preservation Invariant: R_{v1} ==_C R_{v2} ==_C R_Oracle bit-exact across re-planning.
//!   4. Non-retroactive Merkle root progression.

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

pub const DriftKind = enum {
    scale_contraction, // N=1M -> N=128
    pcie_bus_throttling, // Bandwidth throttled
    vram_residency_eviction, // VRAM evicted to Host
};

pub const AdaptivePlanTransition = struct {
    drift: DriftKind,
    initial_backend: planner.BackendTarget,
    recalculated_backend: planner.BackendTarget,
    semantic_parity_verified: bool,
    oracle_match: bool,
    t_v1_est_ns: u64,
    t_v2_est_ns: u64,
};

pub const AdaptiveRePlanningEngine = struct {
    pub fn planInitialWorkload(n_elements: usize) planner.ExecutionDecision {
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

    pub fn rePlanUnderDrift(
        drift: DriftKind,
        n_elements: usize,
    ) planner.ExecutionDecision {
        var cost_model = CostModel{};

        var wl = WorkloadDescriptor{
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

        switch (drift) {
            .scale_contraction => {
                // Scale dropped to 128 (N < N*)
                wl.total_elements = 128;
                wl.layout.data_bytes = 128 * @sizeOf(i32);
                wl.reuse_count = 1;
                wl.dependencies.transfer_amortization_eligible = false;
            },
            .pcie_bus_throttling => {
                // Bus latency throttled by 20x
                cost_model.gpu_h2d_ns_per_byte = 3.0;
                cost_model.gpu_d2h_ns_per_byte = 3.0;
                wl.reuse_count = 1;
                wl.dependencies.transfer_amortization_eligible = false;
            },
            .vram_residency_eviction => {
                // Buffer evicted from VRAM to Host RAM with single-shot execution
                wl.input_residency = .host_ram;
                wl.output_residency = .host_ram;
                wl.reuse_count = 1;
                wl.dependencies.transfer_amortization_eligible = false;
            },
        }

        return ExecutionPlanner.plan(wl, cost_model, true);
    }

    pub fn computeAdaptiveLedgerRoot(
        transitions: []const AdaptivePlanTransition,
    ) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-LANG-008-ADAPTIVE-REPLANNING-V1");
        for (transitions) |t| {
            h.update(@tagName(t.drift));
            h.update(@tagName(t.initial_backend));
            h.update(@tagName(t.recalculated_backend));
            h.update(std.mem.asBytes(&t.semantic_parity_verified));
            h.update(std.mem.asBytes(&t.t_v1_est_ns));
            h.update(std.mem.asBytes(&t.t_v2_est_ns));
        }
        var root: [32]u8 = undefined;
        h.final(&root);
        return root;
    }
};
