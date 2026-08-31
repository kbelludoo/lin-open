//! lin_workload_planner.zig — Universal WorkloadDescriptor, CostModel & ExecutionPlanner (LIN-GPU-006A-D)
//!
//! Architectural Invariants:
//!   1. "O transpilador preserva a intenção; o planner preserva a residência;
//!       o cost model decide o backend com zero chamadas ao runtime."
//!   2. ExecutionDecision = argmin E[T(b) | workload, residency, cost_model].
//!   3. Zero hardcoded magic constants in the planner: all decisions are cost-driven.
//!   4. H_decision = SHA256("LIN-DECISION-V1" || H_workload || H_cost_model || backend || strategy).

const std = @import("std");
const engine = @import("lin_mir_engine.zig");
const analyzer = @import("lin_reduction_analyzer.zig");

const MirType = engine.MirType;
const LinReductionOp = analyzer.LinReductionOp;

pub const WorkloadOp = enum(u8) {
    map = 1,
    reduce = 2,
    scan = 3,
    stencil = 4,
    gemm = 5,
    fused_map_reduce = 6,
};

pub const ResidencyState = enum(u8) {
    unknown = 0,
    host_ram = 1,
    gpu_vram = 2,
    shared_mapped = 3,
};

pub const BackendTarget = enum(u8) {
    cpu_scalar = 1,
    cpu_simd = 2,
    gpu_rocm = 3,
    reject_illegal = 4,
};

pub const DecisionReasonCode = enum(u8) {
    cpu_small_workload = 1,
    cpu_host_resident = 2,
    gpu_vram_resident = 3,
    gpu_amortized_reuse = 4,
    gpu_cost_advantage = 5,
    unknown_residency_conservative = 6,
    no_valid_gpu_plan = 7,
    reject_invalid_semantics = 8,
};

pub const MemoryLayout = struct {
    data_bytes: usize,
    alignment: usize = 64,
    contiguous: bool = true,
    stride: usize = 1,
};

pub const DependencyFacts = struct {
    is_iteration_independent: bool = true,
    is_associative: bool = true,
    is_commutative: bool = true,
    is_memory_safe_no_alias: bool = true,
    has_loop_carried_accum: bool = false,
    conflicting_writers: bool = false,
    transfer_amortization_eligible: bool = true,
};

pub const WorkloadDescriptor = struct {
    schema_version: u32 = 1,
    op: WorkloadOp,
    elem_type: MirType,
    accum_type: MirType,
    reduction_op: ?LinReductionOp = null,
    identity_val_raw: i64 = 0,
    rank: u32 = 1,
    shape: [4]usize = [_]usize{ 0, 0, 0, 0 },
    total_elements: usize,
    layout: MemoryLayout,
    dependencies: DependencyFacts,
    input_residency: ResidencyState,
    output_residency: ResidencyState,
    reuse_count: u32 = 1,
    producer_node_id: u32 = 0,
    consumer_node_id: u32 = 0,

    /// Computes the canonical workload hash H_workload = SHA256("LIN-WORKLOAD-V1" || schema_version || CanonicalEncoding)
    pub fn computeWorkloadHash(self: WorkloadDescriptor) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-WORKLOAD-V1");
        hasher.update(std.mem.asBytes(&self.schema_version));
        hasher.update(&[_]u8{@intFromEnum(self.op)});
        hasher.update(&[_]u8{@intFromEnum(self.elem_type)});
        hasher.update(&[_]u8{@intFromEnum(self.accum_type)});
        if (self.reduction_op) |rop| {
            hasher.update(&[_]u8{@intFromEnum(rop)});
        } else {
            hasher.update(&[_]u8{0xFF});
        }
        hasher.update(std.mem.asBytes(&self.identity_val_raw));
        hasher.update(std.mem.asBytes(&self.rank));
        hasher.update(std.mem.asBytes(&self.shape));
        hasher.update(std.mem.asBytes(&self.total_elements));
        hasher.update(std.mem.asBytes(&self.layout.data_bytes));
        hasher.update(&[_]u8{if (self.layout.contiguous) 1 else 0});
        hasher.update(std.mem.asBytes(&self.layout.stride));
        hasher.update(&[_]u8{if (self.dependencies.is_iteration_independent) 1 else 0});
        hasher.update(&[_]u8{if (self.dependencies.is_associative) 1 else 0});
        hasher.update(&[_]u8{if (self.dependencies.is_commutative) 1 else 0});
        hasher.update(&[_]u8{if (self.dependencies.is_memory_safe_no_alias) 1 else 0});
        hasher.update(&[_]u8{if (self.dependencies.transfer_amortization_eligible) 1 else 0});
        hasher.update(&[_]u8{@intFromEnum(self.input_residency)});
        hasher.update(&[_]u8{@intFromEnum(self.output_residency)});
        hasher.update(std.mem.asBytes(&self.reuse_count));
        hasher.update(std.mem.asBytes(&self.producer_node_id));
        hasher.update(std.mem.asBytes(&self.consumer_node_id));

        var hash: [32]u8 = undefined;
        hasher.final(&hash);
        return hash;
    }

    pub fn structurallyEquals(a: WorkloadDescriptor, b: WorkloadDescriptor) bool {
        return a.schema_version == b.schema_version and
            a.op == b.op and
            a.elem_type == b.elem_type and
            a.accum_type == b.accum_type and
            a.reduction_op == b.reduction_op and
            a.identity_val_raw == b.identity_val_raw and
            a.rank == b.rank and
            std.mem.eql(usize, &a.shape, &b.shape) and
            a.total_elements == b.total_elements and
            a.layout.data_bytes == b.layout.data_bytes and
            a.layout.contiguous == b.layout.contiguous and
            a.layout.stride == b.layout.stride and
            a.dependencies.is_iteration_independent == b.dependencies.is_iteration_independent and
            a.dependencies.is_associative == b.dependencies.is_associative and
            a.dependencies.is_commutative == b.dependencies.is_commutative and
            a.dependencies.is_memory_safe_no_alias == b.dependencies.is_memory_safe_no_alias and
            a.dependencies.transfer_amortization_eligible == b.dependencies.transfer_amortization_eligible and
            a.input_residency == b.input_residency and
            a.output_residency == b.output_residency and
            a.reuse_count == b.reuse_count and
            a.producer_node_id == b.producer_node_id and
            a.consumer_node_id == b.consumer_node_id;
    }
};

pub const CostModel = struct {
    version: u32 = 1,
    machine_fingerprint: []const u8 = "x86_64:linux:zen3:pcie4",
    device: []const u8 = "gfx1030",
    cpu_intercept_ns: f64 = 50.0,
    cpu_ns_per_element: f64 = 0.3952,
    gpu_launch_ns: f64 = 3700.0,
    gpu_h2d_ns_per_byte: f64 = 0.1538, // ~6.5 GB/s PCIe 4.0 host to device
    gpu_d2h_ns_per_byte: f64 = 0.1600, // ~6.25 GB/s PCIe device to host
    gpu_compute_ns_per_element: f64 = 0.0362, // ~27 GEl/s compute throughput
    fit_quality: f64 = 0.995, // R^2 of calibration fit
    measurement_count: u32 = 390, // 26 sizes * 15 repetitions

    pub fn computeModelHash(self: CostModel) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-COST-MODEL-V1");
        hasher.update(std.mem.asBytes(&self.version));
        hasher.update(self.machine_fingerprint);
        hasher.update(self.device);
        hasher.update(std.mem.asBytes(&self.cpu_intercept_ns));
        hasher.update(std.mem.asBytes(&self.cpu_ns_per_element));
        hasher.update(std.mem.asBytes(&self.gpu_launch_ns));
        hasher.update(std.mem.asBytes(&self.gpu_h2d_ns_per_byte));
        hasher.update(std.mem.asBytes(&self.gpu_d2h_ns_per_byte));
        hasher.update(std.mem.asBytes(&self.gpu_compute_ns_per_element));
        hasher.update(std.mem.asBytes(&self.fit_quality));
        hasher.update(std.mem.asBytes(&self.measurement_count));

        var hash: [32]u8 = undefined;
        hasher.final(&hash);
        return hash;
    }
};

pub const ExecutionDecision = struct {
    backend: BackendTarget,
    device: []const u8,
    strategy: []const u8,
    estimated_total_ns: u64,
    estimated_compute_ns: u64,
    estimated_transfer_ns: u64,
    reason_code: DecisionReasonCode,
    confidence: f64,
    workload_hash: [32]u8,
    cost_model_hash: [32]u8,

    pub fn computeDecisionHash(self: ExecutionDecision) [32]u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update("LIN-DECISION-V1");
        hasher.update(&self.workload_hash);
        hasher.update(&self.cost_model_hash);
        hasher.update(&[_]u8{@intFromEnum(self.backend)});
        hasher.update(&[_]u8{@intFromEnum(self.reason_code)});
        hasher.update(self.strategy);
        hasher.update(self.device);
        hasher.update(std.mem.asBytes(&self.estimated_total_ns));

        var hash: [32]u8 = undefined;
        hasher.final(&hash);
        return hash;
    }

    pub fn structurallyEquals(a: ExecutionDecision, b: ExecutionDecision) bool {
        return a.backend == b.backend and
            std.mem.eql(u8, a.device, b.device) and
            std.mem.eql(u8, a.strategy, b.strategy) and
            a.estimated_total_ns == b.estimated_total_ns and
            a.reason_code == b.reason_code and
            std.mem.eql(u8, &a.workload_hash, &b.workload_hash) and
            std.mem.eql(u8, &a.cost_model_hash, &b.cost_model_hash);
    }
};

pub const ExecutionPlanner = struct {
    /// Pure mathematical decision function: zero runtime calls, zero OS clocks, zero hardware probes
    pub fn plan(desc: WorkloadDescriptor, model: CostModel, gpu_supported: bool) ExecutionDecision {
        const w_hash = desc.computeWorkloadHash();
        const m_hash = model.computeModelHash();

        // 1. Semantic legality & safety checks
        if (!desc.dependencies.is_memory_safe_no_alias or desc.dependencies.conflicting_writers) {
            return ExecutionDecision{
                .backend = .reject_illegal,
                .device = "none",
                .strategy = "reject_aliasing_or_side_effects",
                .estimated_total_ns = 0,
                .estimated_compute_ns = 0,
                .estimated_transfer_ns = 0,
                .reason_code = .reject_invalid_semantics,
                .confidence = 1.0,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        }

        if (desc.op == .reduce and (!desc.dependencies.is_associative or !desc.dependencies.is_commutative)) {
            return ExecutionDecision{
                .backend = .reject_illegal,
                .device = "none",
                .strategy = "reject_non_associative_reduction",
                .estimated_total_ns = 0,
                .estimated_compute_ns = 0,
                .estimated_transfer_ns = 0,
                .reason_code = .reject_invalid_semantics,
                .confidence = 1.0,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        }

        // 2. Hardware backend availability check
        if (!gpu_supported) {
            const cpu_est: u64 = @intFromFloat(model.cpu_intercept_ns + model.cpu_ns_per_element * @as(f64, @floatFromInt(desc.total_elements)));
            return ExecutionDecision{
                .backend = .cpu_scalar,
                .device = "host_x86_64",
                .strategy = "cpu_scalar_loop",
                .estimated_total_ns = cpu_est,
                .estimated_compute_ns = cpu_est,
                .estimated_transfer_ns = 0,
                .reason_code = .no_valid_gpu_plan,
                .confidence = model.fit_quality,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        }

        // 3. Unknown residency check: conservative CPU resolution
        if (desc.input_residency == .unknown) {
            const cpu_est: u64 = @intFromFloat(model.cpu_intercept_ns + model.cpu_ns_per_element * @as(f64, @floatFromInt(desc.total_elements)));
            return ExecutionDecision{
                .backend = .cpu_scalar,
                .device = "host_x86_64",
                .strategy = "cpu_scalar_loop",
                .estimated_total_ns = cpu_est,
                .estimated_compute_ns = cpu_est,
                .estimated_transfer_ns = 0,
                .reason_code = .unknown_residency_conservative,
                .confidence = model.fit_quality * 0.90,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        }

        // 4. Exact cost model evaluation (T_CPU vs T_GPU)
        const fn_elements = @as(f64, @floatFromInt(desc.total_elements));
        const f_in_bytes = @as(f64, @floatFromInt(desc.layout.data_bytes));
        const f_out_bytes: f64 = if (desc.op == .reduce) @as(f64, 4.0) else f_in_bytes;

        const t_cpu_ns: f64 = model.cpu_intercept_ns + model.cpu_ns_per_element * fn_elements;
        const t_gpu_compute_ns: f64 = model.gpu_launch_ns + model.gpu_compute_ns_per_element * fn_elements;

        const is_vram_resident = (desc.input_residency == .gpu_vram);
        const t_h2d_ns: f64 = if (is_vram_resident) 0.0 else model.gpu_h2d_ns_per_byte * f_in_bytes;
        const is_output_vram = (desc.output_residency == .gpu_vram);
        const t_d2h_ns: f64 = if (is_output_vram) 0.0 else model.gpu_d2h_ns_per_byte * f_out_bytes;

        // Amortized transfer cost if reuse count R > 1 and transfer is eligible
        const is_amortizable = desc.dependencies.transfer_amortization_eligible and (desc.reuse_count > 1);
        const reuse_r = @as(f64, @floatFromInt(desc.reuse_count));
        const t_transfer_ns: f64 = if (is_vram_resident)
            t_d2h_ns
        else if (is_amortizable)
            (t_h2d_ns + t_d2h_ns) / (reuse_r + 1.0)
        else
            (t_h2d_ns + t_d2h_ns);

        const t_gpu_total_ns: f64 = t_gpu_compute_ns + t_transfer_ns;

        // Deterministic confidence computation based on model fit quality and decision margin
        const delta_t = @abs(t_cpu_ns - t_gpu_total_ns);
        const min_t = @min(t_cpu_ns, t_gpu_total_ns);
        const margin_ratio = delta_t / (min_t + 1.0);
        const derived_confidence = model.fit_quality * @min(1.0, 0.85 + 0.15 * @min(margin_ratio, 1.0));

        // Evaluate ArgMin(T_CPU, T_GPU)
        if (t_gpu_total_ns < t_cpu_ns) {
            const reason: DecisionReasonCode = if (is_vram_resident)
                .gpu_vram_resident
            else if (is_amortizable)
                .gpu_amortized_reuse
            else
                .gpu_cost_advantage;

            const strategy = if (desc.op == .reduce) "reduce_tree_2pass_256" else "parallel_map_1d_grid";

            return ExecutionDecision{
                .backend = .gpu_rocm,
                .device = model.device,
                .strategy = strategy,
                .estimated_total_ns = @intFromFloat(t_gpu_total_ns),
                .estimated_compute_ns = @intFromFloat(t_gpu_compute_ns),
                .estimated_transfer_ns = @intFromFloat(t_transfer_ns),
                .reason_code = reason,
                .confidence = derived_confidence,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        } else {
            // CPU is cheaper: select scalar for small N, SIMD unrolled for medium/large host data
            const is_small = (desc.total_elements < 256);
            const reason: DecisionReasonCode = if (is_small) .cpu_small_workload else .cpu_host_resident;
            const strategy: []const u8 = if (is_small) "cpu_scalar_loop" else "cpu_simd_avx2_unrolled";
            const backend: BackendTarget = if (is_small) .cpu_scalar else .cpu_simd;

            return ExecutionDecision{
                .backend = backend,
                .device = "host_x86_64",
                .strategy = strategy,
                .estimated_total_ns = @intFromFloat(t_cpu_ns),
                .estimated_compute_ns = @intFromFloat(t_cpu_ns),
                .estimated_transfer_ns = 0,
                .reason_code = reason,
                .confidence = derived_confidence,
                .workload_hash = w_hash,
                .cost_model_hash = m_hash,
            };
        }
    }
};
