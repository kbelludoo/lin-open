const std = @import("std");
const mir_vm = @import("lin_mir_vm.zig");

pub const VerifierError = error{
    SsaDuplicateDefinition,
    TypeMismatch,
    MissingTerminator,
    InvalidRegisterIndex,
    InvalidPhiPlacement,
};

pub const MirVerifier = struct {
    pub fn verifyFunction(func: mir_vm.MirFunction) VerifierError!void {
        var defined_regs = [_]bool{false} ** 256;

        // Mark param registers as defined
        for (0..func.params.len) |i| {
            if (i < 256) {
                defined_regs[i] = true;
            }
        }

        for (func.blocks) |block| {
            if (block.instructions.len == 0) {
                return VerifierError.MissingTerminator;
            }

            var has_terminator = false;
            for (block.instructions, 0..) |inst, idx| {
                // Verify SSA definition rule (except for ret which does not define a new register)
                if (inst.opcode != .ret_op) {
                    if (inst.dst >= 256) return VerifierError.InvalidRegisterIndex;
                    // In strict SSA, dst register should not be redefined
                    if (defined_regs[inst.dst] and inst.opcode != .param) {
                        return VerifierError.SsaDuplicateDefinition;
                    }
                    defined_regs[inst.dst] = true;
                }

                // Verify operand definitions
                if (inst.opcode != .const_val and inst.opcode != .param) {
                    if (inst.lhs >= 256 or !defined_regs[inst.lhs]) {
                        return VerifierError.InvalidRegisterIndex;
                    }
                    if (inst.opcode != .ret_op and inst.opcode != .select_op) {
                        if (inst.rhs >= 256 or !defined_regs[inst.rhs]) {
                            return VerifierError.InvalidRegisterIndex;
                        }
                    }
                }

                // Check terminator
                if (inst.opcode == .ret_op) {
                    has_terminator = true;
                    if (idx != block.instructions.len - 1) {
                        // ret must be the last instruction in the block
                        return VerifierError.MissingTerminator;
                    }
                }
            }

            if (!has_terminator) {
                return VerifierError.MissingTerminator;
            }
        }
    }
};
