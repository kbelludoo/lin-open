const std = @import("std");

pub const JitEngine = struct {
    allocator: std.mem.Allocator,

    pub fn init(allocator: std.mem.Allocator) JitEngine {
        return .{ .allocator = allocator };
    }

    /// Allocates an executable memory page using mmap
    pub fn allocateExecutablePage(size: usize) ![]align(std.mem.page_size) u8 {
        const page_size = std.mem.page_size;
        const alloc_size = std.mem.alignForward(usize, size, page_size);
        
        const ptr = try std.posix.mmap(
            null,
            alloc_size,
            std.posix.PROT.READ | std.posix.PROT.WRITE,
            .{ .TYPE = .PRIVATE, .ANONYMOUS = true },
            -1,
            0,
        );
        return ptr;
    }

    /// Makes the memory page executable and non-writable (W^X security)
    pub fn makeExecutable(page: []align(std.mem.page_size) u8) !void {
        try std.posix.mprotect(page, std.posix.PROT.READ | std.posix.PROT.EXEC);
    }

    /// Releases the executable memory page
    pub fn freePage(page: []align(std.mem.page_size) u8) void {
        std.posix.munmap(page);
    }
};

/// Compiles a simple x86_64 addition function in memory: f(a, b) = a + b
/// System V AMD64 ABI: arg0 in rdi, arg1 in rsi, return in rax
/// Bytecode:
///   48 89 f8    -> mov %rdi, %rax
///   48 01 f0    -> add %rsi, %rax
///   c3          -> ret
pub fn emitAddJit() !struct { page: []align(std.mem.page_size) u8, fn_ptr: *const fn (i64, i64) callconv(.C) i64 } {
    const page = try JitEngine.allocateExecutablePage(4096);
    
    // Write x86_64 opcodes
    page[0] = 0x48;
    page[1] = 0x89;
    page[2] = 0xf8; // mov %rdi, %rax

    page[3] = 0x48;
    page[4] = 0x01;
    page[5] = 0xf0; // add %rsi, %rax

    page[6] = 0xc3; // ret

    try JitEngine.makeExecutable(page);

    const func = @as(*const fn (i64, i64) callconv(.C) i64, @ptrCast(page.ptr));
    return .{ .page = page, .fn_ptr = func };
}

/// Compiles an x86_64 bitwise rotate left function in memory: f(x, s) = rotl64(x, s)
pub fn emitRotl64Jit() !struct { page: []align(std.mem.page_size) u8, fn_ptr: *const fn (u64, u8) callconv(.C) u64 } {
    const page = try JitEngine.allocateExecutablePage(4096);

    // mov %rdi, %rax
    page[0] = 0x48;
    page[1] = 0x89;
    page[2] = 0xf8;

    // mov %rsi, %rcx (shift count in cl)
    page[3] = 0x48;
    page[4] = 0x89;
    page[5] = 0xf1;

    // rol %cl, %rax
    page[6] = 0x48;
    page[7] = 0xd3;
    page[8] = 0xc0;

    // ret
    page[9] = 0xc3;

    try JitEngine.makeExecutable(page);

    const func = @as(*const fn (u64, u8) callconv(.C) u64, @ptrCast(page.ptr));
    return .{ .page = page, .fn_ptr = func };
}
