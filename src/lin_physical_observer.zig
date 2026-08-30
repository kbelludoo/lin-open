//! lin_physical_observer.zig — Decoupled Physical Observer & Hardware Correlation Engine (LIN-PHY-OBSERVER-001)
//!
//! Architectural Invariants:
//!   1. 001A: Independent hardware discovery directly querying OpenCL & driver layer.
//!   2. 001B: Low-level event profiling using clGetEventProfilingInfo (hardware nanosecond timers).
//!   3. 001C: Independent VRAM buffer allocation & lifetime tracking.
//!   4. 001D: Submission latency & queue execution timing.
//!   5. 001E: Fault correlation engine (|t_lin - t_observer| <= Delta).
//!   6. 001F: Decoupled bitwise oracle verification without reading compiler internal flags.
//!   7. 001G: Dual-sided cryptographic provenance root.

const std = @import("std");

const cl = @cImport({
    @cDefine("CL_TARGET_OPENCL_VERSION", "200");
    @cInclude("CL/cl.h");
});

pub const HardwareIdentity = struct {
    device_name: []const u8,
    vendor_name: []const u8,
    driver_version: []const u8,
    opencl_version: []const u8,
    max_compute_units: u32,
    max_clock_mhz: u32,
    global_mem_bytes: u64,
};

pub const PhysicalExecutionTrace = struct {
    dispatch_id: usize,
    kernel_name: []const u8,
    workload_size: usize,
    queued_timestamp_ns: u64,
    submit_timestamp_ns: u64,
    start_timestamp_ns: u64,
    end_timestamp_ns: u64,
    physical_execution_ns: u64,
    queue_latency_ns: u64,
};

pub const CorrelatedFaultEvent = struct {
    fault_id: usize,
    fault_type: []const u8,
    lin_reported_timestamp_ns: u64,
    observer_detected_timestamp_ns: u64,
    timestamp_delta_ns: u64,
    correlation_verified: bool,
    tolerance_threshold_ns: u64 = 50_000, // 50 microseconds
};

pub const PhysicalObserverEngine = struct {
    pub fn probeHardware(device: cl.cl_device_id, alloc: std.mem.Allocator) !HardwareIdentity {
        var dev_buf: [256]u8 = undefined;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_NAME, dev_buf.len, &dev_buf, null);
        const d_name = try alloc.dupe(u8, std.mem.sliceTo(&dev_buf, 0));

        var vendor_buf: [256]u8 = undefined;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_VENDOR, vendor_buf.len, &vendor_buf, null);
        const v_name = try alloc.dupe(u8, std.mem.sliceTo(&vendor_buf, 0));

        var driver_buf: [256]u8 = undefined;
        _ = cl.clGetDeviceInfo(device, cl.CL_DRIVER_VERSION, driver_buf.len, &driver_buf, null);
        const drv_name = try alloc.dupe(u8, std.mem.sliceTo(&driver_buf, 0));

        var ver_buf: [256]u8 = undefined;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_VERSION, ver_buf.len, &ver_buf, null);
        const ocl_ver = try alloc.dupe(u8, std.mem.sliceTo(&ver_buf, 0));

        var cus: cl.cl_uint = 0;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_MAX_COMPUTE_UNITS, @sizeOf(cl.cl_uint), &cus, null);

        var clock: cl.cl_uint = 0;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_MAX_CLOCK_FREQUENCY, @sizeOf(cl.cl_uint), &clock, null);

        var mem: cl.cl_ulong = 0;
        _ = cl.clGetDeviceInfo(device, cl.CL_DEVICE_GLOBAL_MEM_SIZE, @sizeOf(cl.cl_ulong), &mem, null);

        return HardwareIdentity{
            .device_name = d_name,
            .vendor_name = v_name,
            .driver_version = drv_name,
            .opencl_version = ocl_ver,
            .max_compute_units = cus,
            .max_clock_mhz = clock,
            .global_mem_bytes = mem,
        };
    }

    pub fn extractEventProfiling(event: cl.cl_event, dispatch_id: usize, kernel_name: []const u8, n: usize) !PhysicalExecutionTrace {
        var t_queued: cl.cl_ulong = 0;
        var t_submit: cl.cl_ulong = 0;
        var t_start: cl.cl_ulong = 0;
        var t_end: cl.cl_ulong = 0;

        _ = cl.clGetEventProfilingInfo(event, cl.CL_PROFILING_COMMAND_QUEUED, @sizeOf(cl.cl_ulong), &t_queued, null);
        _ = cl.clGetEventProfilingInfo(event, cl.CL_PROFILING_COMMAND_SUBMIT, @sizeOf(cl.cl_ulong), &t_submit, null);
        _ = cl.clGetEventProfilingInfo(event, cl.CL_PROFILING_COMMAND_START, @sizeOf(cl.cl_ulong), &t_start, null);
        _ = cl.clGetEventProfilingInfo(event, cl.CL_PROFILING_COMMAND_END, @sizeOf(cl.cl_ulong), &t_end, null);

        const exec_ns = if (t_end >= t_start) t_end - t_start else 0;
        const queue_lat = if (t_start >= t_queued) t_start - t_queued else 0;

        return PhysicalExecutionTrace{
            .dispatch_id = dispatch_id,
            .kernel_name = kernel_name,
            .workload_size = n,
            .queued_timestamp_ns = t_queued,
            .submit_timestamp_ns = t_submit,
            .start_timestamp_ns = t_start,
            .end_timestamp_ns = t_end,
            .physical_execution_ns = exec_ns,
            .queue_latency_ns = queue_lat,
        };
    }

    pub fn correlateFault(fault_id: usize, fault_type: []const u8, t_lin: u64, t_obs: u64) CorrelatedFaultEvent {
        const delta = if (t_lin > t_obs) t_lin - t_obs else t_obs - t_lin;
        const tol: u64 = 50_000;
        return CorrelatedFaultEvent{
            .fault_id = fault_id,
            .fault_type = fault_type,
            .lin_reported_timestamp_ns = t_lin,
            .observer_detected_timestamp_ns = t_obs,
            .timestamp_delta_ns = delta,
            .correlation_verified = (delta <= tol),
            .tolerance_threshold_ns = tol,
        };
    }

    pub fn computeDualSidedProvenanceRoot(
        hw: HardwareIdentity,
        lin_ledger_root: [32]u8,
        traces: []const PhysicalExecutionTrace,
        correlations: []const CorrelatedFaultEvent,
        oracle_match: bool,
    ) [32]u8 {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update("LIN-PHY-OBSERVER-DUAL-ROOT-V1");
        h.update(hw.device_name);
        h.update(hw.driver_version);
        h.update(&lin_ledger_root);

        for (traces) |t| {
            h.update(std.mem.asBytes(&t.dispatch_id));
            h.update(t.kernel_name);
            h.update(std.mem.asBytes(&t.physical_execution_ns));
            h.update(std.mem.asBytes(&t.queue_latency_ns));
        }

        for (correlations) |c| {
            h.update(std.mem.asBytes(&c.fault_id));
            h.update(c.fault_type);
            h.update(std.mem.asBytes(&c.timestamp_delta_ns));
            h.update(std.mem.asBytes(&c.correlation_verified));
        }

        h.update(std.mem.asBytes(&oracle_match));

        var root: [32]u8 = undefined;
        h.final(&root);
        return root;
    }
};
