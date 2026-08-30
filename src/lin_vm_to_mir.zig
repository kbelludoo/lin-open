/// lin_vm_to_mir.zig — Stack-machine → SSA MIR Compiler (LIN-GPU-004)
///
/// Converts a VmFn (LIN stack bytecode, produced by vmBuild from .lin source)
/// into a MirFunction (SSA form, consumed by MirToOpenCLLowerer → GPU).
///
/// This is the bridge that closes the frontend→GPU chain:
///
///   .lin source
///      │
///   vmBuild()        ← existing LIN frontend
///      │
///   VmFn (stack IR)
///      │
///   VmToMirCompiler  ← this file
///      │
///   MirFunction (SSA)
///      │
///   MirToOpenCLLowerer
///      │
///   OpenCL C → GPU
///
/// Scope: single-basic-block functions with scalar int parameters.
/// Restriction: functions without loops/backward-jumps (parallel_map kernels).

const std = @import("std");

// These types live in lin.zig — imported by the caller which passes them in.
// We use comptime duck-typing to avoid a circular import.

pub const VmToMirError = error{
    TooManyRegisters,
    StackUnderflow,
    UnsupportedOpcode,
    CallsNotSupported,
    BranchesNotSupported,
    OutOfMemory,
};

/// Compile a VmFn stack bytecode into MirInst[].
/// Returns an owned slice of MirInst (caller must free with allocator).
///
/// Types:
///   VmOp  — the VmOp enum from lin.zig  (passed as comptime type)
///   VmIns — the VmIns struct from lin.zig (passed as comptime type)
///
/// MirOpcode and MirInst come from lin_mir_engine.zig.
pub fn compileVmFnToMir(
    comptime VmOp: type,
    comptime VmIns: type,
    MirOpcode: type,
    MirInst: type,
    allocator: std.mem.Allocator,
    code: []const VmIns,
    nparams: usize,
) VmToMirError![]MirInst {
    // Virtual register allocator
    var next_reg: u32 = 0;
    var out = std.ArrayList(MirInst).init(allocator);

    // Stack of virtual registers (simulates the VM's value stack in SSA space)
    var stk: [256]u32 = undefined;
    var sp: usize = 0;

    // Local variable slots → last SSA register holding their value
    var locals: [64]u32 = undefined;
    @memset(&locals, 0);

    // Emit parameter loads first: each param[i] is local[i] = param vreg
    for (0..nparams) |i| {
        const dst = next_reg;
        next_reg += 1;
        try out.append(MirInst{
            .opcode = @field(MirOpcode, "param"),
            .ty     = @field(@import("lin_mir_engine.zig").MirType, "i64"),
            .dst    = dst,
            .imm    = @as(i64, @intCast(i)),
        });
        locals[i] = dst;
    }

    for (code) |ins| {
        switch (ins.op) {
            @field(VmOp, "push_const") => {
                const dst = next_reg; next_reg += 1;
                try out.append(.{
                    .opcode = @field(MirOpcode, "const_val"),
                    .ty     = @field(@import("lin_mir_engine.zig").MirType, "i64"),
                    .dst    = dst,
                    .imm    = ins.a,
                });
                if (sp >= stk.len) return VmToMirError.TooManyRegisters;
                stk[sp] = dst;
                sp += 1;
            },
            @field(VmOp, "load_local") => {
                const li: usize = @intCast(ins.a);
                if (sp >= stk.len) return VmToMirError.TooManyRegisters;
                stk[sp] = locals[li];
                sp += 1;
            },
            @field(VmOp, "store_local") => {
                if (sp == 0) return VmToMirError.StackUnderflow;
                sp -= 1;
                const li: usize = @intCast(ins.a);
                locals[li] = stk[sp];
            },
            @field(VmOp, "pop") => {
                if (sp == 0) return VmToMirError.StackUnderflow;
                sp -= 1;
            },
            @field(VmOp, "neg") => {
                if (sp == 0) return VmToMirError.StackUnderflow;
                // neg x  ≡  0 - x
                const zero = next_reg; next_reg += 1;
                try out.append(.{
                    .opcode = @field(MirOpcode, "const_val"),
                    .ty     = @field(@import("lin_mir_engine.zig").MirType, "i64"),
                    .dst    = zero,
                    .imm    = 0,
                });
                const dst = next_reg; next_reg += 1;
                try out.append(.{
                    .opcode = @field(MirOpcode, "sub"),
                    .ty     = @field(@import("lin_mir_engine.zig").MirType, "i64"),
                    .dst    = dst,
                    .lhs    = zero,
                    .rhs    = stk[sp - 1],
                });
                stk[sp - 1] = dst;
            },
            @field(VmOp, "ret") => {
                if (sp == 0) return VmToMirError.StackUnderflow;
                try out.append(.{
                    .opcode = @field(MirOpcode, "ret_op"),
                    .ty     = @field(@import("lin_mir_engine.zig").MirType, "i64"),
                    .lhs    = stk[sp - 1],
                });
                sp -= 1;
                // A single-block parallel_map kernel finishes at its first return!
                break;
            },
            // Binary ops: pop two, push result
            @field(VmOp, "add"),
            @field(VmOp, "sub"),
            @field(VmOp, "mul"),
            @field(VmOp, "bit_and"),
            @field(VmOp, "bit_or"),
            @field(VmOp, "bit_xor"),
            @field(VmOp, "shl"),
            @field(VmOp, "shr"),
            @field(VmOp, "ushr"),
            @field(VmOp, "cmp_eq"),
            @field(VmOp, "cmp_ne"),
            @field(VmOp, "cmp_lt"),
            @field(VmOp, "cmp_gt"),
            @field(VmOp, "cmp_le"),
            @field(VmOp, "cmp_ge"),
            => {
                if (sp < 2) return VmToMirError.StackUnderflow;
                const lhs = stk[sp - 2];
                const rhs = stk[sp - 1];
                sp -= 2;
                const dst = next_reg; next_reg += 1;
                const MirType = @import("lin_mir_engine.zig").MirType;
                const mir_op: MirOpcode = switch (ins.op) {
                    @field(VmOp, "add")    => @field(MirOpcode, "add"),
                    @field(VmOp, "sub")    => @field(MirOpcode, "sub"),
                    @field(VmOp, "mul")    => @field(MirOpcode, "mul"),
                    @field(VmOp, "bit_and")=> @field(MirOpcode, "and_op"),
                    @field(VmOp, "bit_or") => @field(MirOpcode, "or_op"),
                    @field(VmOp, "bit_xor")=> @field(MirOpcode, "xor_op"),
                    @field(VmOp, "shl")    => @field(MirOpcode, "shl_op"),
                    @field(VmOp, "shr")    => @field(MirOpcode, "shr_op"),
                    @field(VmOp, "ushr")   => @field(MirOpcode, "ushr_op"),
                    @field(VmOp, "cmp_eq") => @field(MirOpcode, "cmp_eq"),
                    @field(VmOp, "cmp_ne") => @field(MirOpcode, "cmp_eq"), // cmp_ne via cmp_eq+not below
                    @field(VmOp, "cmp_lt") => @field(MirOpcode, "cmp_lt"),
                    @field(VmOp, "cmp_gt") => @field(MirOpcode, "cmp_lt"), // swap args
                    @field(VmOp, "cmp_le") => @field(MirOpcode, "cmp_lt"), // swap+not
                    @field(VmOp, "cmp_ge") => @field(MirOpcode, "cmp_lt"), // not
                    else => unreachable,
                };
                // For gt/le/ge/ne, we need fixup
                var actual_lhs = lhs;
                var actual_rhs = rhs;
                if (ins.op == @field(VmOp, "cmp_gt") or ins.op == @field(VmOp, "cmp_le")) {
                    actual_lhs = rhs;
                    actual_rhs = lhs;
                }
                try out.append(.{
                    .opcode = mir_op,
                    .ty     = MirType.i64,
                    .dst    = dst,
                    .lhs    = actual_lhs,
                    .rhs    = actual_rhs,
                });
                var result_reg = dst;
                // Negate for ne/le
                if (ins.op == @field(VmOp, "cmp_ne") or ins.op == @field(VmOp, "cmp_le")) {
                    const not_dst = next_reg; next_reg += 1;
                    const one = next_reg; next_reg += 1;
                    try out.append(.{
                        .opcode = @field(MirOpcode, "const_val"),
                        .ty     = MirType.i64,
                        .dst    = one,
                        .imm    = 1,
                    });
                    // not(x) = 1 - x  (for boolean 0/1)
                    try out.append(.{
                        .opcode = @field(MirOpcode, "sub"),
                        .ty     = MirType.i64,
                        .dst    = not_dst,
                        .lhs    = one,
                        .rhs    = dst,
                    });
                    result_reg = not_dst;
                }
                if (sp >= stk.len) return VmToMirError.TooManyRegisters;
                stk[sp] = result_reg;
                sp += 1;
            },
            // Conditional branches: for simple if-else (cmp_lt → select pattern)
            // We convert jump_if_false + single-block to a select_op where possible.
            // For complex CFG, we bail out.
            @field(VmOp, "jump_if_false") => {
                // Pattern: ... cond ... jump_if_false L ... value_true ... jump L2 ... value_false
                // We don't implement general CFG — bail with UnsupportedOpcode for GPU lowering.
                // Simple straight-line select patterns are handled via K3 (abs) in a different way.
                return VmToMirError.BranchesNotSupported;
            },
            @field(VmOp, "call") => {
                return VmToMirError.CallsNotSupported;
            },
            else => {
                return VmToMirError.UnsupportedOpcode;
            },
        }
    }

    return try out.toOwnedSlice();
}
