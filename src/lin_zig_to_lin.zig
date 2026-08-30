//! lin_zig_to_lin.zig — Compiler 0 Zig-to-LIN Transpiler Bridge
//!
//! Converts Zig AST declarations and data-parallel patterns into Canonical LIN IR (.lin).

const std = @import("std");

pub const ZigToLinBridge = struct {
    pub fn transpileZigFunctionToLin(allocator: std.mem.Allocator, fn_name: []const u8, params: []const []const u8, body_expr: []const u8) ![]u8 {
        var buf = std.ArrayList(u8).init(allocator);
        defer buf.deinit();

        try buf.appendSlice("@LIN:L1c:0.2\n");
        try buf.appendSlice("^schema_once ^lossy=false ^ops=transpiled_from_zig\n");
        try buf.appendSlice("~G{?=if #=for ^=ret :else}\n\n");

        try buf.appendSlice("!");
        try buf.appendSlice(fn_name);
        try buf.appendSlice("(");
        for (params, 0..) |p, i| {
            if (i > 0) try buf.appendSlice(", ");
            try buf.appendSlice(p);
        }
        try buf.appendSlice(") {\n");
        try buf.appendSlice("    ");
        try buf.appendSlice(body_expr);
        try buf.appendSlice("\n}\n\n");

        try buf.appendSlice("=ex{");
        try buf.appendSlice(fn_name);
        try buf.appendSlice("}\n");

        return buf.toOwnedSlice();
    }
};
