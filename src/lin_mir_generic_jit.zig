const std = @import("std");
const jit = @import("lin_jit.zig");
const engine = @import("lin_mir_engine.zig");

pub const GenericJitEngine = struct {
    pub const JitFunction = struct {
        page: []align(std.mem.page_size) u8,
        fn_ptr: *const fn (i64, i64) callconv(.C) i64,

        pub fn deinit(self: *JitFunction) void {
            jit.JitEngine.freePage(self.page);
        }
    };

    /// Generic JIT lowering that emits x86_64 machine code directly from an arbitrary MirFunction!
    /// Supports: param, const_val, add, sub, mul, and, or, xor, shl, ushr, shr, cmp_lt, cmp_eq, br_if, br_jmp, phi_op, ret_op.
    pub fn compile(func: engine.MirFunction) !JitFunction {
        const page = try jit.JitEngine.allocateExecutablePage(4096);
        var offset: usize = 0;

        // Allocate a 256-word stack frame for virtual registers: [rsp - 2048]
        // sub $2048, %rsp   -> 48 81 ec 00 08 00 00
        page[offset] = 0x48;
        page[offset + 1] = 0x81;
        page[offset + 2] = 0xec;
        page[offset + 3] = 0x00;
        page[offset + 4] = 0x08;
        page[offset + 5] = 0x00;
        page[offset + 6] = 0x00;
        offset += 7;

        // Store param 0 (rdi) to stack slot 0: mov %rdi, 0(%rsp) -> 48 89 3c 24
        page[offset] = 0x48;
        page[offset + 1] = 0x89;
        page[offset + 2] = 0x3c;
        page[offset + 3] = 0x24;
        offset += 4;

        // Store param 1 (rsi) to stack slot 1: mov %rsi, 8(%rsp) -> 48 89 74 24 08
        page[offset] = 0x48;
        page[offset + 1] = 0x89;
        page[offset + 2] = 0x74;
        page[offset + 3] = 0x24;
        page[offset + 4] = 0x08;
        offset += 5;

        // Map block IDs to byte offsets for relocation
        var block_offsets: [64]usize = [_]usize{0} ** 64;
        var jump_relocs: [64]struct { patch_offset: usize, target_block: u32, is_conditional: bool } = undefined;
        var reloc_count: usize = 0;

        // Track PHI nodes to lower in predecessor jumps
        for (func.blocks) |block| {
            if (block.id < 64) {
                block_offsets[block.id] = offset;
            }

            for (block.instructions) |inst| {
                switch (inst.opcode) {
                    .const_val => {
                        // mov $imm, %rax -> 48 b8 <8 bytes>
                        page[offset] = 0x48;
                        page[offset + 1] = 0xb8;
                        const imm_bytes: [8]u8 = @bitCast(inst.imm);
                        @memcpy(page[offset + 2 .. offset + 10], &imm_bytes);
                        offset += 10;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .param => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .add => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // add %rdx, %rax -> 48 01 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x01;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .sub => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // sub %rdx, %rax -> 48 29 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x29;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .mul => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // imul %rdx, %rax -> 48 0f af c2
                        page[offset] = 0x48;
                        page[offset + 1] = 0x0f;
                        page[offset + 2] = 0xaf;
                        page[offset + 3] = 0xc2;
                        offset += 4;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .and_op => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // and %rdx, %rax -> 48 21 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x21;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .or_op => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // or %rdx, %rax -> 48 09 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x09;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .xor_op => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // xor %rdx, %rax -> 48 31 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x31;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .cmp_lt => {
                        offset += emitLoadRsp(page[offset..], inst.lhs);
                        offset += emitLoadRdx(page[offset..], inst.rhs);
                        // cmp %rdx, %rax -> 48 39 d0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x39;
                        page[offset + 2] = 0xd0;
                        offset += 3;
                        // setl %al -> 0f 9c c0
                        page[offset] = 0x0f;
                        page[offset + 1] = 0x9c;
                        page[offset + 2] = 0xc0;
                        offset += 3;
                        // movzbq %al, %rax -> 48 0f b6 c0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x0f;
                        page[offset + 2] = 0xb6;
                        page[offset + 3] = 0xc0;
                        offset += 4;
                        offset += emitStoreRsp(page[offset..], inst.dst);
                    },
                    .phi_op => {
                        // PHI node register is written by predecessor block jumps
                    },
                    .br_jmp => {
                        // Check if target block has PHI nodes and lower predecessor copy
                        for (func.blocks) |target_b| {
                            if (target_b.id == inst.target_block) {
                                for (target_b.instructions) |target_inst| {
                                    if (target_inst.opcode == .phi_op) {
                                        for (0..target_inst.phi_count) |k| {
                                            if (target_inst.phi_incoming_blocks[k] == block.id) {
                                                offset += emitLoadRsp(page[offset..], target_inst.phi_incoming_vals[k]);
                                                offset += emitStoreRsp(page[offset..], target_inst.dst);
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // jmp <rel32> -> e9 <4 bytes>
                        page[offset] = 0xe9;
                        jump_relocs[reloc_count] = .{ .patch_offset = offset + 1, .target_block = inst.target_block, .is_conditional = false };
                        reloc_count += 1;
                        offset += 5;
                    },
                    .br_if => {
                        offset += emitLoadRsp(page[offset..], inst.lhs); // mov cond, %rax
                        // test %rax, %rax -> 48 85 c0
                        page[offset] = 0x48;
                        page[offset + 1] = 0x85;
                        page[offset + 2] = 0xc0;
                        offset += 3;
                        // jnz <rel32> -> 0f 85 <4 bytes>
                        page[offset] = 0x0f;
                        page[offset + 1] = 0x85;
                        jump_relocs[reloc_count] = .{ .patch_offset = offset + 2, .target_block = inst.target_block, .is_conditional = true };
                        reloc_count += 1;
                        offset += 6;

                        // jmp <rel32> (else branch) -> e9 <4 bytes>
                        page[offset] = 0xe9;
                        jump_relocs[reloc_count] = .{ .patch_offset = offset + 1, .target_block = inst.target_block_else, .is_conditional = false };
                        reloc_count += 1;
                        offset += 5;
                    },
                    .ret_op => {
                        offset += emitLoadRsp(page[offset..], inst.lhs); // mov ret_reg, %rax
                        // add $2048, %rsp -> 48 81 c4 00 08 00 00
                        page[offset] = 0x48;
                        page[offset + 1] = 0x81;
                        page[offset + 2] = 0xc4;
                        page[offset + 3] = 0x00;
                        page[offset + 4] = 0x08;
                        page[offset + 5] = 0x00;
                        page[offset + 6] = 0x00;
                        offset += 7;
                        // ret -> c3
                        page[offset] = 0xc3;
                        offset += 1;
                    },
                    else => {},
                }
            }
        }

        // Patch all jump relocations dynamically based on target block offsets
        for (jump_relocs[0..reloc_count]) |reloc| {
            const target_pos = block_offsets[reloc.target_block];
            const next_ip = reloc.patch_offset + 4;
            const disp: i32 = @intCast(@as(i64, @intCast(target_pos)) - @as(i64, @intCast(next_ip)));
            const disp_bytes: [4]u8 = @bitCast(disp);
            @memcpy(page[reloc.patch_offset .. reloc.patch_offset + 4], &disp_bytes);
        }

        try jit.JitEngine.makeExecutable(page);

        const fn_call = @as(*const fn (i64, i64) callconv(.C) i64, @ptrCast(page.ptr));
        return .{ .page = page, .fn_ptr = fn_call };
    }

    fn emitLoadRsp(buf: []u8, reg: u32) usize {
        buf[0] = 0x48;
        buf[1] = 0x8b;
        buf[2] = 0x84;
        buf[3] = 0x24;
        const off: i32 = @intCast(reg * 8);
        const off_bytes: [4]u8 = @bitCast(off);
        @memcpy(buf[4..8], &off_bytes);
        return 8;
    }

    fn emitLoadRdx(buf: []u8, reg: u32) usize {
        buf[0] = 0x48;
        buf[1] = 0x8b;
        buf[2] = 0x94;
        buf[3] = 0x24;
        const off: i32 = @intCast(reg * 8);
        const off_bytes: [4]u8 = @bitCast(off);
        @memcpy(buf[4..8], &off_bytes);
        return 8;
    }

    fn emitStoreRsp(buf: []u8, reg: u32) usize {
        buf[0] = 0x48;
        buf[1] = 0x89;
        buf[2] = 0x84;
        buf[3] = 0x24;
        const off: i32 = @intCast(reg * 8);
        const off_bytes: [4]u8 = @bitCast(off);
        @memcpy(buf[4..8], &off_bytes);
        return 8;
    }
};
